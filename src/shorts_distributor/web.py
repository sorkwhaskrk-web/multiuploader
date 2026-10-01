"""Loopback-only dashboard. No additional web framework is required."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .platforms import SUPPORTED_PLATFORM_IDS
from .web_settings import DEFAULTS, ROOT, read_settings, save_settings, validate_snapshot, write_json

ASSETS = Path(__file__).parent / "web_assets"
ACTIONS = {"doctor", "discover", "preview", "login", "verify", "publish"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ProjectLock:
    """OS-owned lock: only one dashboard may use this project's profiles."""

    def __init__(self, root: Path):
        path = root / "data" / "web" / "dashboard.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a+b")
        self.handle.write(b"0")
        self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise AppError("이 프로젝트의 웹앱이 이미 실행 중입니다.", 409)

    def close(self) -> None:
        self.handle.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stop_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15,
        )
        if result.returncode and process.poll() is None:
            raise AppError("작업 프로세스 종료를 확인하지 못했습니다.", 500)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise AppError("작업 종료 시간이 초과됐습니다.", 500) from exc


class Dashboard:
    def __init__(self, root: Path = ROOT, *, allow_publish: bool = False):
        self.root = root
        self.jobs_dir = root / "data" / "web" / "jobs"
        self.allow_publish = allow_publish
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.active: dict | None = None
        self.process: subprocess.Popen | None = None
        self.closing = False

    def settings(self) -> dict:
        return {"values": read_settings(self.root), "platforms": list(SUPPORTED_PLATFORM_IDS),
                "allow_publish": self.allow_publish}

    def save(self, payload: dict) -> dict:
        with self.lock:
            self._idle()
            return {"values": save_settings(payload, self.root)}

    def _idle(self) -> None:
        if self.closing:
            raise AppError("앱이 종료 중입니다.", 409)
        if self.active is not None:
            raise AppError("진행 중인 작업을 완료하거나 중단한 후 다시 시도하세요.", 409)

    def _directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise AppError("잘못된 작업 ID입니다.", 404)
        directory = self.jobs_dir / job_id
        if not (directory / "meta.json").is_file():
            raise AppError("작업을 찾을 수 없습니다.", 404)
        return directory

    def job(self, job_id: str, *, details: bool = True) -> dict:
        with self.lock:
            directory = self._directory(job_id)
            meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            if meta["status"] in {"running", "stopping"} and not (self.active and self.active["id"] == job_id):
                meta["status"] = "interrupted"
                meta["message"] = "이전 실행이 중단됐습니다. 결과를 확인하세요."
            meta["preview_ready"] = (directory / "snapshot.json").is_file() and not meta.get("consumed") and meta["status"] == "succeeded"
            if details:
                result = directory / "result.json"
                meta["result"] = json.loads(result.read_text(encoding="utf-8")) if result.is_file() else None
                log = directory / "output.log"
                if log.is_file():
                    with log.open("rb") as handle:
                        handle.seek(max(0, log.stat().st_size - 32000))
                        meta["log"] = handle.read().decode("utf-8", errors="replace")
                else:
                    meta["log"] = ""
            return meta

    def jobs(self) -> list[dict]:
        with self.lock:
            if not self.jobs_dir.exists():
                return []
            paths = sorted(self.jobs_dir.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            return [self.job(p.parent.name, details=False) for p in paths[:30]]

    def history(self) -> list[dict]:
        path = self.root / "data" / "state.db"
        if not path.is_file():
            return []
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            columns = {r[1] for r in connection.execute("PRAGMA table_info(uploads)")}
            if not columns:
                return []
            rows = connection.execute("SELECT * FROM uploads ORDER BY uploaded_at DESC LIMIT 100")
            return [dict(row) for row in rows]

    def _publish_params(self, payload: dict) -> tuple[dict, dict, Path]:
        if not self.allow_publish:
            raise AppError("현재는 준비 모드입니다. 게시 모드로 앱을 다시 시작하세요.", 403)
        if payload.get("confirm") != "게시":
            raise AppError("미리보기 확인 후 '게시'를 입력하세요.")
        directory = self._directory(payload.get("preview_id", ""))
        preview = self.job(directory.name)
        if preview["action"] != "preview" or not preview["preview_ready"]:
            raise AppError("사용 가능한 미리보기가 없습니다. 다시 준비하세요.", 409)
        snapshot = json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
        validate_snapshot(snapshot, self.root)
        # Attempts remain on disk across restarts, including interrupted jobs.
        # Ambiguous cells have no automatic retry path in the dashboard.
        for old in self.jobs_dir.glob("*/request.json"):
            request = json.loads(old.read_text(encoding="utf-8"))
            if request["action"] != "publish":
                continue
            old_snapshot = request["params"]["snapshot"]
            old_cells = {(v, p) for v in old_snapshot["video_ids"] for p in old_snapshot["platforms"]}
            planned = {(c["youtube_id"], c["platform"]) for c in preview["result"]["cells"] if c["status"] == "planned"}
            if old_cells & planned:
                raise AppError("이 영상·플랫폼에는 이전 게시 시도가 있습니다. 직접 검증 후 CLI로 복구하세요.", 409)
        return {"snapshot": snapshot}, preview, directory

    def start(self, payload: dict) -> dict:
        action = payload.get("action")
        if action not in ACTIONS:
            raise AppError("지원하지 않는 작업입니다.")
        with self.lock:
            self._idle()
            settings = read_settings(self.root)
            params = {}
            consumed = None
            if action in {"discover", "preview", "publish"}:
                if not settings["YOUTUBE_HANDLE"] or "your-youtube" in settings["YOUTUBE_HANDLE"]:
                    raise AppError("먼저 YouTube 채널을 설정하고 저장하세요.")
                if not settings["TARGET_PLATFORMS"]:
                    raise AppError("먼저 대상 플랫폼을 선택하고 저장하세요.")
            if action == "login":
                platform = payload.get("platform")
                if platform not in SUPPORTED_PLATFORM_IDS:
                    raise AppError("지원하는 플랫폼을 선택하세요.")
                if platform not in settings["TARGET_PLATFORMS"].split(","):
                    raise AppError("설정에서 해당 플랫폼을 선택하고 저장하세요.")
                params = {"platform": platform}
            if action == "preview":
                ids = payload.get("video_ids")
                platforms = payload.get("platforms")
                if not isinstance(ids, list) or not 1 <= len(ids) <= 20 or any(not isinstance(v, str) or not VIDEO_ID.fullmatch(v) for v in ids):
                    raise AppError("영상 ID를 1~20개 선택하세요. ID는 11자리입니다.")
                if not isinstance(platforms, list) or not platforms or any(p not in settings["TARGET_PLATFORMS"].split(",") for p in platforms):
                    raise AppError("저장된 대상 플랫폼을 선택하세요.")
                params = {"video_ids": list(dict.fromkeys(ids)), "platforms": list(dict.fromkeys(platforms))}
            if action == "publish":
                params, preview, directory = self._publish_params(payload)
                consumed = (preview, directory)
            job_id = uuid.uuid4().hex
            directory = self.jobs_dir / job_id
            directory.mkdir(parents=True)
            meta = {"id": job_id, "action": action, "status": "running", "created_at": utc_now(), "exit_code": None}
            write_json(directory / "request.json", {"action": action, "params": params})
            write_json(directory / "meta.json", meta)
            env = os.environ.copy()
            # Creator configuration comes only from this project's .env.
            for key in set(DEFAULTS) | {"PLATFORMS", "SHORTS_SELECTION_MODE", "AD_MARKERS_EXTRA", "SHARED_PROFILE_DIR", "CHROME_CHANNEL", "UPLOADER_HEADLESS", "UPLOADER_SLOWMO_MS", "NAVER_DASHBOARD_URL"}:
                env.pop(key, None)
            env.update({"PYTHONPATH": str(self.root / "src"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
            if consumed:
                preview, preview_dir = consumed
                preview["consumed"] = True
                for key in ("log", "result", "preview_ready"):
                    preview.pop(key, None)
                write_json(preview_dir / "meta.json", preview)
            try:
                with (directory / "output.log").open("wb") as output:
                    process = subprocess.Popen(
                        [sys.executable, "-u", "-m", "shorts_distributor.web_worker", str(directory)],
                        cwd=self.root, env=env, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        start_new_session=os.name != "nt",
                    )
            except OSError as exc:
                meta.update(status="failed", message=str(exc), finished_at=utc_now())
                write_json(directory / "meta.json", meta)
                raise AppError(f"작업 실행 실패: {exc}", 500) from exc
            self.active, self.process = meta, process
            threading.Thread(target=self._watch, args=(meta, process, directory), daemon=True).start()
            return self.job(job_id)

    def _watch(self, meta: dict, process: subprocess.Popen, directory: Path) -> None:
        code = process.wait()
        with self.lock:
            if meta["status"] == "stopping":
                status = "cancelled"
            else:
                status = "succeeded" if code == 0 else "attention" if code == 3 else "failed"
            meta.update(status=status, exit_code=code, finished_at=utc_now())
            write_json(directory / "meta.json", meta)
            if process.stdin:
                process.stdin.close()
            self.active, self.process = None, None

    def finish_login(self, job_id: str) -> dict:
        with self.lock:
            if not self.active or self.active["id"] != job_id or self.active["action"] != "login" or not self.process:
                raise AppError("진행 중인 로그인 작업이 없습니다.", 409)
            try:
                self.process.stdin.write(b"\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise AppError("로그인 창 상태를 다시 확인하세요.", 409) from exc
            return {"ok": True}

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            if not self.active or self.active["id"] != job_id or not self.process:
                raise AppError("진행 중인 작업이 아닙니다.", 409)
            self.active["status"] = "stopping"
            write_json(self.jobs_dir / job_id / "meta.json", self.active)
            process = self.process
        stop_process_tree(process)
        return {"ok": True}

    def close(self) -> None:
        with self.lock:
            self.closing = True
            active = self.active
        if active:
            self.cancel(active["id"])


def make_server(app: Dashboard, port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log token headers, creator values, or request bodies.

        def _send(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, value: object, status: int = 200) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _authorize(self, api: bool) -> None:
            port = self.server.server_port
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                raise AppError("로컬 주소로 접속하세요.", 403)
            if self.headers.get("Origin") not in {None, f"http://{host}"}:
                raise AppError("다른 웹사이트의 요청은 허용하지 않습니다.", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise AppError("로컬 앱에서 요청하세요.", 403)
            if api and not secrets.compare_digest(self.headers.get("X-App-Token", ""), app.token):
                raise AppError("앱 페이지를 새로고침하세요.", 403)

        def do_GET(self):
            try:
                path = urlparse(self.path).path
                self._authorize(path.startswith("/api/"))
                if path in {"/", "/index.html"}:
                    html = (ASSETS / "index.html").read_text(encoding="utf-8").replace("__APP_TOKEN__", app.token)
                    self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                elif path in {"/app.js", "/style.css"}:
                    mime = "text/javascript" if path.endswith(".js") else "text/css"
                    self._send(200, (ASSETS / path[1:]).read_bytes(), mime + "; charset=utf-8")
                elif path == "/api/settings":
                    self._json(app.settings())
                elif path == "/api/jobs":
                    self._json(app.jobs())
                elif path.startswith("/api/jobs/"):
                    self._json(app.job(path.split("/")[-1]))
                elif path == "/api/history":
                    self._json(app.history())
                else:
                    self._json({"error": "찾을 수 없는 페이지입니다."}, 404)
            except AppError as exc:
                self._json({"error": str(exc)}, exc.status)
            except Exception:
                self._json({"error": "데이터를 읽지 못했습니다. 로컬 파일 상태를 확인하세요."}, 500)

        def do_POST(self):
            try:
                self._authorize(True)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise AppError("JSON 요청이 필요합니다.", 415)
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32000:
                    raise AppError("요청 크기가 잘못됐습니다.", 413)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise AppError("잘못된 요청입니다.")
                if self.path == "/api/settings":
                    self._json(app.save(payload))
                elif self.path == "/api/jobs":
                    self._json(app.start(payload), 202)
                elif self.path == "/api/login-complete":
                    self._json(app.finish_login(payload.get("job_id", "")))
                elif self.path == "/api/cancel":
                    self._json(app.cancel(payload.get("job_id", "")))
                else:
                    raise AppError("지원하지 않는 요청입니다.", 404)
            except AppError as exc:
                self._json({"error": str(exc)}, exc.status)
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, 400)
            except Exception:
                self._json({"error": "작업을 처리하지 못했습니다. 로그를 확인하세요."}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="멀티업로더 로컬 웹앱")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="기본 브라우저 열기")
    parser.add_argument("--allow-publish", action="store_true", help="검토한 영상의 게시 버튼 활성화")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("포트는 1~65535 범위여야 합니다.")
    app = Dashboard(allow_publish=args.allow_publish)
    try:
        project_lock = ProjectLock(ROOT)
    except AppError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        server = make_server(app, args.port)
    except OSError as exc:
        project_lock.close()
        print(f"앱 실행 실패: {exc}. 다른 포트를 지정하세요.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"멀티업로더: {url} ({'게시' if args.allow_publish else '준비'} 모드)", flush=True)
    print("종료: Ctrl+C", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            app.close()
        finally:
            server.server_close()
            project_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
