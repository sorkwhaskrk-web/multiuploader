import http.client
import json
import threading
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from shorts_distributor import runner, web_worker
from shorts_distributor.web import AppError, Dashboard, ProjectLock, make_server, stop_process_tree
from shorts_distributor.web_settings import (
    build_snapshot, read_settings, save_settings, validate_settings, validate_snapshot, write_json,
)

ID = "abcdefghijk"


def fixture(root):
    save_settings({"YOUTUBE_HANDLE": "@example-channel", "TARGET_PLATFORMS": "instagram,tiktok"}, root)
    media = root / "data" / "downloads" / (ID + ".mp4")
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fictitious-test-media")
    return {
        "dry_run": True, "exit_code": 0, "target_platforms": ["instagram", "tiktok"],
        "batch_oldest_first": [{"youtube_id": ID, "title": "Example", "title_text": "Example",
            "file": str(media), "codec": "h264", "post_text": "Exact\n#example", "timestamp": 1,
            "allowed_platforms": ["instagram", "tiktok"], "disclosures": {}, "policy_names": []}],
        "cells": [{"youtube_id": ID, "platform": p, "status": "planned"} for p in ("instagram", "tiktok")],
    }


class SettingsTest(TestCase):
    def test_local_save_round_trip_preserves_private_unknown_values_and_comments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("# private local comment\nOTHER_OPTION=fictional\n", encoding="utf-8")
            values = save_settings({"YOUTUBE_HANDLE": "@example", "FACEBOOK_PAGE_NAME": "Creator's \\ test ${LITERAL}"}, root)
            self.assertEqual(read_settings(root), values)
            self.assertIn("OTHER_OPTION=fictional", (root / ".env").read_text(encoding="utf-8"))
            self.assertNotIn("OTHER_OPTION", read_settings(root))

    def test_rejects_env_newline_injection_and_unknown_keys(self):
        with TemporaryDirectory() as tmp:
            for payload in ({"YOUTUBE_HANDLE":"@a\nPASSWORD=x"}, {"TOKEN":"fictional"}):
                with self.assertRaises(ValueError):
                    save_settings(payload, Path(tmp))
            self.assertFalse((Path(tmp) / ".env").exists())

    def test_rejects_wrong_domains_and_file_paths(self):
        with TemporaryDirectory() as tmp:
            for payload in (
                {"LINKEDIN_RECENT_ACTIVITY_URL":"https://linkedin.com.attacker.invalid/profile"},
                {"YOUTUBE_HANDLE":"https://example.invalid/@example"},
                {"CONTENT_POLICIES_FILE":"../outside.json"},
                {"TARGET_PLATFORMS":"unsupported"},
                {"SHORTS_UPLOAD_LIMIT":"0"},
            ):
                with self.assertRaises(ValueError):
                    validate_settings(payload, Path(tmp))

    def test_empty_settings_do_not_infer_accounts_or_targets(self):
        with TemporaryDirectory() as tmp:
            values = read_settings(Path(tmp))
            self.assertEqual(values["TARGET_PLATFORMS"], "")
            self.assertEqual(values["YOUTUBE_HANDLE"], "")


class SnapshotTest(TestCase):
    def test_detects_changed_media(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = fixture(root)
            snapshot = build_snapshot(report, root)
            validate_snapshot(snapshot, root)
            Path(report["batch_oldest_first"][0]["file"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "영상 파일"):
                validate_snapshot(snapshot, root)

    def test_detects_changed_settings_and_policy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = fixture(root)
            policy = root / "policy.json"; policy.write_text('{}', encoding="utf-8")
            save_settings({"CONTENT_POLICIES_FILE":"policy.json"}, root)
            snapshot = build_snapshot(report, root)
            policy.write_text('{"version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "설정이나 콘텐츠 정책"):
                validate_snapshot(snapshot, root)
            snapshot = build_snapshot(report, root)
            save_settings({"POST_TEXT_MODE":"title"}, root)
            with self.assertRaises(ValueError):
                validate_snapshot(snapshot, root)

    def test_rejects_failed_empty_and_all_completed_previews(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = fixture(root)
            report["exit_code"] = 3
            with self.assertRaises(ValueError): build_snapshot(report, root)
            report["exit_code"] = 0
            for cell in report["cells"]: cell["status"] = "already"
            with self.assertRaises(ValueError): build_snapshot(report, root)

    def test_media_outside_downloads_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = fixture(root)
            outside = root / "other.mp4"; outside.write_bytes(b"example")
            report["batch_oldest_first"][0]["file"] = str(outside)
            with self.assertRaises(ValueError): build_snapshot(report, root)


class DashboardTest(TestCase):
    def test_publish_disabled_at_server_even_with_crafted_request(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            app = Dashboard(root)
            with self.assertRaises(AppError) as caught:
                app.start({"action":"publish", "confirm":"게시", "preview_id":"a" * 32})
            self.assertEqual(caught.exception.status, 403)
            self.assertIsNone(app.process)

    def test_job_validation_blocks_shell_injection_and_empty_selection(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root); app = Dashboard(root)
            for request in (
                {"action":"shell"}, {"action":"login", "platform":"instagram;echo x"},
                {"action":"preview", "video_ids":[], "platforms":["instagram"]},
                {"action":"preview", "video_ids":["bad;cmd"], "platforms":["instagram"]},
                {"action":"preview", "video_ids":[ID], "platforms":["facebook"]},
            ):
                with self.assertRaises(AppError): app.start(request)

    def test_settings_locked_during_jobs(self):
        with TemporaryDirectory() as tmp:
            app = Dashboard(Path(tmp)); app.active = {"id":"a" * 32}
            with self.assertRaises(AppError): app.save({"YOUTUBE_HANDLE":"@example"})

    def test_duplicate_attempts_stay_blocked_across_restarts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); report = fixture(root); app = Dashboard(root, allow_publish=True)
            preview = app.jobs_dir / ("a" * 32)
            write_json(preview / "meta.json", {"id":preview.name, "action":"preview", "status":"succeeded"})
            write_json(preview / "result.json", report)
            snapshot = build_snapshot(report, root); write_json(preview / "snapshot.json", snapshot)
            params, _, _ = app._publish_params({"preview_id":preview.name, "confirm":"게시"})
            write_json(app.jobs_dir / ("b" * 32) / "request.json", {"action":"publish", "params":params})
            restarted = Dashboard(root, allow_publish=True)
            with self.assertRaisesRegex(AppError, "이전 게시 시도"):
                restarted._publish_params({"preview_id":preview.name, "confirm":"게시"})

    def test_read_only_history_does_not_create_database(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); app=Dashboard(root)
            self.assertEqual(app.history(), [])
            self.assertFalse((root / "data" / "state.db").exists())

    def test_project_lock_prevents_two_dashboards(self):
        with TemporaryDirectory() as tmp:
            first = ProjectLock(Path(tmp))
            try:
                with self.assertRaises(AppError): ProjectLock(Path(tmp))
            finally: first.close()
            second = ProjectLock(Path(tmp)); second.close()

    def test_windows_cancel_targets_only_owned_process_tree(self):
        process=Mock(pid=456789); process.poll.side_effect=[None, 0]
        with patch("shorts_distributor.web.os.name", "nt"), patch("shorts_distributor.web.subprocess.run", return_value=SimpleNamespace(returncode=0)) as command:
            stop_process_tree(process)
        self.assertEqual(command.call_args.args[0], ["taskkill", "/PID", "456789", "/T", "/F"])
        process.wait.assert_called_once()


class HttpTest(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.app=Dashboard(self.root); self.server=make_server(self.app, 0)
        self.thread=threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port, timeout=5)
        body=json.dumps(payload) if payload is not None else None
        connection.request(method,path,body,headers or {})
        response=connection.getresponse(); value=response.read(); status=response.status
        connection.close(); return status,value

    def test_index_assets_and_protected_api(self):
        status,html=self.request("GET","/")
        self.assertEqual(status,200); self.assertIn(self.app.token.encode(),html)
        self.assertEqual(self.request("GET","/app.js")[0],200)
        self.assertEqual(self.request("GET","/api/settings")[0],403)
        status,data=self.request("GET","/api/settings",headers={"X-App-Token":self.app.token})
        self.assertEqual(status,200); self.assertFalse(json.loads(data)["allow_publish"])

    def test_wrong_host_origin_and_cross_site_are_blocked(self):
        for headers in ({"Host":"evil.invalid"},{"Origin":"https://evil.invalid"},{"Sec-Fetch-Site":"cross-site"}):
            self.assertEqual(self.request("GET","/",headers=headers)[0],403)

    def test_settings_require_token_and_json(self):
        payload={"YOUTUBE_HANDLE":"@example", "TARGET_PLATFORMS":"instagram"}
        self.assertEqual(self.request("POST","/api/settings",payload,headers={"Content-Type":"application/json"})[0],403)
        headers={"X-App-Token":self.app.token,"Content-Type":"application/json"}
        status,_=self.request("POST","/api/settings",payload,headers)
        self.assertEqual(status,200); self.assertEqual(read_settings(self.root)["YOUTUBE_HANDLE"],"@example")

    def test_arbitrary_files_are_never_served(self):
        for path in ("/.env","/data/state.db","/../.env","/api/jobs/../../.env"):
            self.assertEqual(self.request("GET",path,headers={"X-App-Token":self.app.token})[0],404)


class PreparedRunnerTest(TestCase):
    def test_reviewed_snapshot_keeps_exact_text_and_chronological_order(self):
        items=[{"youtube_id":ID,"title":"New","title_text":"New","file_path":"example.mp4","post_text":"Exact\n#text","upload_date":"20260902","timestamp":2},
               {"youtube_id":"lmnopqrstuv","title":"Old","title_text":"Old","file_path":"example.mp4","post_text":"Other","upload_date":"20260901","timestamp":1}]
        cfg=SimpleNamespace(target_platforms=["instagram"],profile_strategy="shared",youtube_handle="@example")
        with patch.object(runner,"_new_run_dir",return_value=("test",Path("example"))), patch.object(runner,"sweep_pending",return_value=[]), patch.object(runner,"prepare_video") as download, patch.object(runner,"ensure_h264") as codec, patch.object(runner.state,"is_uploaded",return_value=False), patch.object(runner,"get_uploader",return_value=Mock()), patch.object(runner,"platform_context",return_value=nullcontext(Mock())), patch.object(runner,"_run_lane_in_ctx") as lane, patch.object(runner,"_write_report"):
            report=runner.run_batch(cfg,video_ids=[p["youtube_id"] for p in items],prepared_videos=items)
        download.assert_not_called();codec.assert_not_called()
        self.assertEqual([p["youtube_id"] for p in report["batch_oldest_first"]],["lmnopqrstuv",ID])
        self.assertEqual(lane.call_args.args[4][ID]["post_text"],"Exact\n#text")

    def test_snapshot_ids_must_match_selected_ids(self):
        with self.assertRaises(ValueError):
            runner.run_batch(Mock(),video_ids=[ID],prepared_videos=[{"youtube_id":"lmnopqrstuv"}])

    def test_dry_run_preparation_failure_is_not_success(self):
        cfg=SimpleNamespace(target_platforms=["instagram"],youtube_handle="@example")
        with patch.object(runner,"_new_run_dir",return_value=("test",Path("example"))), patch.object(runner,"prepare_video",side_effect=RuntimeError("download failed")), patch.object(runner,"_write_report"):
            report=runner.run_batch(cfg,video_ids=[ID],dry_run=True)
        self.assertEqual(report["exit_code"],3);self.assertEqual(report["cells"][0]["status"],"failed")

    def test_worker_publishes_frozen_prepared_inputs(self):
        snapshot={"platforms":["instagram"],"video_ids":[ID],"prepared":[{"youtube_id":ID}]}
        with patch.object(web_worker,"load_dotenv"),patch.object(web_worker.Config,"load",return_value=Mock()),patch.object(web_worker,"validate_snapshot"),patch.object(web_worker.runner,"doctor",return_value={"tools":{"ffmpeg":True},"platforms":[{"platform":"instagram","session":"ok","missing_env":[]}]}),patch.object(web_worker.runner,"run_batch",return_value={"exit_code":0}) as run:
            _,code=web_worker.execute("publish",{"snapshot":snapshot},Path("example"))
        self.assertEqual(code,0); self.assertEqual(run.call_args.kwargs["prepared_videos"],snapshot["prepared"])

    def test_worker_blocks_publish_when_all_accounts_are_unavailable(self):
        snapshot={"platforms":["instagram"],"video_ids":[ID],"prepared":[]}
        with patch.object(web_worker,"load_dotenv"),patch.object(web_worker.Config,"load",return_value=Mock()),patch.object(web_worker,"validate_snapshot"),patch.object(web_worker.runner,"doctor",return_value={"tools":{"ffmpeg":True},"platforms":[{"platform":"instagram","session":"no-login","missing_env":[]}]}),patch.object(web_worker.runner,"run_batch") as run:
            with self.assertRaisesRegex(ValueError,"게시 가능한 플랫폼"):
                web_worker.execute("publish",{"snapshot":snapshot},Path("example"))
        run.assert_not_called()
