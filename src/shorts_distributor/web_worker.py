"""Isolated dashboard job. One process owns Playwright and its children."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import runner
from .config import Config, PROJECT_ROOT
from .web_settings import build_snapshot, validate_snapshot, write_json


def execute(action: str, params: dict, directory: Path) -> tuple[object, int]:
    load_dotenv(PROJECT_ROOT / ".env", override=True, interpolate=False)
    cfg = Config.load()
    if action == "doctor":
        result = runner.doctor(cfg)
        return result, 0 if result["ok"] else 3
    if action == "discover":
        result = runner.plan_batch(cfg, upload_limit="all", selection_mode="all")
        return result, 0
    if action == "login":
        result = runner.login(cfg, params["platform"])
        return {"platform": params["platform"], "logged_in": result}, 0 if result else 3
    if action == "verify":
        result = runner.verify_uploads(cfg, pending=True)
        return result, 0 if all(r["verify_status"] in {"verified", "waiting"} for r in result) else 3
    if action == "preview":
        result = runner.run_batch(cfg, platforms=params["platforms"], video_ids=params["video_ids"], dry_run=True)
        if result["exit_code"] == 0:
            try:
                write_json(directory / "snapshot.json", build_snapshot(result))
            except ValueError as exc:
                result["preview_note"] = str(exc)
        return result, result["exit_code"]
    if action == "publish":
        snapshot = params["snapshot"]
        validate_snapshot(snapshot)
        preflight = runner.doctor(cfg)
        if not all(preflight["tools"].values()):
            raise ValueError("ffmpeg/ffprobe/yt-dlp를 먼저 준비하세요.")
        if not any(p["session"] == "ok" and not p["missing_env"] for p in preflight["platforms"] if p["platform"] in snapshot["platforms"]):
            raise ValueError("게시 가능한 플랫폼 연결이 없습니다. 환경 점검 후 로그인하세요.")
        result = runner.run_batch(
            cfg, platforms=snapshot["platforms"], video_ids=snapshot["video_ids"],
            prepared_videos=snapshot["prepared"],
        )
        result["preflight"] = preflight
        return result, result["exit_code"]
    raise ValueError("알 수 없는 작업입니다.")


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    if not directory.is_relative_to((PROJECT_ROOT / "data" / "web" / "jobs").resolve()):
        raise ValueError("Invalid job directory")
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    try:
        result, code = execute(request["action"], request["params"], directory)
        write_json(directory / "result.json", result)
        return code
    except Exception as exc:
        write_json(directory / "result.json", {"error": str(exc)})
        print(f"작업 실패: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
