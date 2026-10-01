"""Validated, creator-local dashboard settings and snapshot fingerprints."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

from .platforms import SUPPORTED_PLATFORM_IDS

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "YOUTUBE_HANDLE": "", "TARGET_PLATFORMS": "", "POST_TEXT_MODE": "caption",
    "SHORTS_UPLOAD_LIMIT": "2", "SHORTS_LOOKBACK_LIMIT": "50",
    "SHORTS_SKIP_ADS": "true", "YOUTUBE_METADATA_LANG": "ko",
    "PROFILE_STRATEGY": "per-platform", "INSTAGRAM_HANDLE": "",
    "THREADS_HANDLE": "", "TIKTOK_HANDLE": "", "LINKEDIN_RECENT_ACTIVITY_URL": "",
    "FACEBOOK_VIDEOS_URL": "", "FACEBOOK_PAGE_NAME": "", "NAVER_CHANNEL_SLUG": "",
    "NAVER_CLIP_URL": "", "NAVER_CATEGORY_1": "", "NAVER_CATEGORY_2": "",
    "CONTENT_POLICIES_FILE": "",
}
URL_DOMAINS = {
    "LINKEDIN_RECENT_ACTIVITY_URL": "linkedin.com",
    "FACEBOOK_VIDEOS_URL": "facebook.com",
    "NAVER_CLIP_URL": "naver.com",
}


def read_settings(root: Path = ROOT) -> dict[str, str]:
    values = dotenv_values(root / ".env", interpolate=False)
    return {key: values.get(key) or default for key, default in DEFAULTS.items()}


def validate_settings(payload: dict, root: Path = ROOT) -> dict[str, str]:
    if set(payload) - set(DEFAULTS):
        raise ValueError("지원하지 않는 설정 항목입니다.")
    values = read_settings(root)
    for key, value in payload.items():
        if not isinstance(value, str) or len(value) > 2000 or any(c in value for c in "\r\n\0"):
            raise ValueError(f"{key}: 한 줄의 텍스트를 입력하세요.")
        values[key] = value.strip()
    source = values["YOUTUBE_HANDLE"]
    if source:
        if source.startswith("https://"):
            parsed = urlparse(source)
            if parsed.hostname not in {"youtube.com", "www.youtube.com"} or not parsed.path.strip("/") or parsed.username:
                raise ValueError("YouTube 채널 주소 또는 @핸들을 입력하세요.")
        elif not re.fullmatch(r"@?[^\s/?#:=]+", source):
            raise ValueError("YouTube 채널 주소 또는 @핸들을 입력하세요.")
        if "your-youtube" in source:
            raise ValueError("예제 대신 본인 YouTube 채널을 입력하세요.")
    targets = list(dict.fromkeys(values["TARGET_PLATFORMS"].split(",")))
    if any(p and p not in SUPPORTED_PLATFORM_IDS for p in targets):
        raise ValueError("지원하는 플랫폼을 선택하세요.")
    values["TARGET_PLATFORMS"] = ",".join(p for p in targets if p)
    for key, choices in {
        "POST_TEXT_MODE": {"title", "caption"}, "PROFILE_STRATEGY": {"shared", "per-platform"},
        "SHORTS_SKIP_ADS": {"true", "false"},
    }.items():
        if values[key] not in choices:
            raise ValueError(f"{key}: 잘못된 선택입니다.")
    for key, maximum in {"SHORTS_UPLOAD_LIMIT": 20, "SHORTS_LOOKBACK_LIMIT": 200}.items():
        if not values[key].isdigit() or not 1 <= int(values[key]) <= maximum:
            raise ValueError(f"{key}: 1~{maximum} 범위의 숫자를 입력하세요.")
    for key in ("INSTAGRAM_HANDLE", "THREADS_HANDLE", "TIKTOK_HANDLE"):
        value = values[key].lstrip("@")
        if value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError(f"{key}: URL 대신 계정 핸들을 입력하세요.")
        if value.startswith("your_"):
            raise ValueError(f"{key}: 예제 대신 본인 계정을 입력하세요.")
        values[key] = value
    for key, domain in URL_DOMAINS.items():
        if not values[key]:
            continue
        parsed = urlparse(values[key])
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or not (host == domain or host.endswith("." + domain)):
            raise ValueError(f"{key}: {domain}의 HTTPS 주소를 입력하세요.")
    if values["CONTENT_POLICIES_FILE"]:
        policy = (root / values["CONTENT_POLICIES_FILE"]).resolve()
        if not policy.is_relative_to(root.resolve()) or policy.suffix != ".json" or not policy.is_file():
            raise ValueError("콘텐츠 정책은 프로젝트 안에 존재하는 JSON 파일이어야 합니다.")
        values["CONTENT_POLICIES_FILE"] = policy.relative_to(root.resolve()).as_posix()
    return values


def save_settings(payload: dict, root: Path = ROOT) -> dict[str, str]:
    values = validate_settings(payload, root)
    path = root / ".env"
    # Preserve other creator settings and comments; only replace dashboard keys.
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [line for line in lines if not re.match(
        r"^\s*(?:export\s+)?(" + "|".join(DEFAULTS) + r")\s*=", line
    )]
    for key, value in values.items():
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"{key}='{escaped}'")
    temporary = root / ".env.web-tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return values


def config_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    env_path = root / ".env"
    digest.update(env_path.read_bytes() if env_path.exists() else b"")
    policy_raw = dotenv_values(env_path, interpolate=False).get("CONTENT_POLICIES_FILE")
    if policy_raw:
        policy = (root / policy_raw).resolve()
        if not policy.is_relative_to(root.resolve()):
            raise ValueError("콘텐츠 정책 파일은 프로젝트 안에 두세요.")
        digest.update(policy.read_bytes())
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build_snapshot(report: dict, root: Path = ROOT) -> dict:
    if not report.get("dry_run") or report.get("exit_code") != 0:
        raise ValueError("미리보기가 정상 완료되지 않았습니다.")
    batch = report.get("batch_oldest_first", [])
    if not batch or not any(c["status"] == "planned" for c in report.get("cells", [])):
        raise ValueError("새로 게시할 영상이 없습니다.")
    if any(c["status"] not in {"planned", "already", "skipped-policy"} for c in report["cells"]):
        raise ValueError("문제가 있는 셀을 먼저 해결하세요.")
    prepared = []
    hashes = {}
    for item in batch:
        path = Path(item["file"]).resolve()
        if not path.is_relative_to((root / "data" / "downloads").resolve()) or not path.is_file():
            raise ValueError("프로젝트 다운로드 폴더의 영상이 필요합니다.")
        hashes[str(path)] = file_hash(path)
        prepared.append({
            **item, "file_path": str(path), "upload_file_path": str(path),
            "codec_note": item["codec"], "title_text": item.get("title_text", item["title"]),
        })
    return {
        "config_hash": config_fingerprint(root), "media_hashes": hashes,
        "prepared": prepared, "platforms": report["target_platforms"],
        "video_ids": [p["youtube_id"] for p in prepared],
    }


def validate_snapshot(snapshot: dict, root: Path = ROOT) -> None:
    if snapshot["config_hash"] != config_fingerprint(root):
        raise ValueError("설정이나 콘텐츠 정책이 변경됐습니다. 미리보기를 다시 만드세요.")
    for raw, expected in snapshot["media_hashes"].items():
        path = Path(raw).resolve()
        if not path.is_relative_to((root / "data" / "downloads").resolve()):
            raise ValueError("잘못된 영상 경로입니다.")
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError("영상 파일이 변경됐습니다. 미리보기를 다시 만드세요.")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
