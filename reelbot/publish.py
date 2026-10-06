"""Step 6: publish a finished reel.mp4 to a Facebook Page via the Graph API Reels endpoint."""
import time
from pathlib import Path

import requests

from reelbot.config import env


def build_description(script: dict, cfg: dict) -> str:
    parts = [script["caption"].strip(), " ".join(script["hashtags"])]
    disclosure = cfg["publish"].get("ai_disclosure")
    if disclosure:
        parts.append(disclosure)
    return "\n\n".join(p for p in parts if p)


def _check(resp: requests.Response) -> dict:
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Facebook API error ({resp.status_code}): {data.get('error', resp.text)}")
    return data


def publish_reel(cfg: dict, video_path: Path, description: str, timeout_s: int = 600) -> str:
    page_id, token = env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    ver = cfg["publish"]["graph_version"]
    endpoint = f"https://graph.facebook.com/{ver}/{page_id}/video_reels"

    # 1) start an upload session
    start = _check(requests.post(endpoint, data={"upload_phase": "start", "access_token": token}, timeout=60))
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or f"https://rupload.facebook.com/video-upload/{ver}/{video_id}"

    # 2) upload the binary
    size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        _check(requests.post(
            upload_url,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
            data=f, timeout=600,
        ))

    # 3) publish
    _check(requests.post(endpoint, data={
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
        "description": description, "access_token": token,
    }, timeout=60))

    # 4) wait for processing
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = _check(requests.get(
            f"https://graph.facebook.com/{ver}/{video_id}",
            params={"fields": "status", "access_token": token}, timeout=30,
        )).get("status", {})
        state = status.get("video_status")
        if state in {"ready", "published"} or status.get("publishing_phase", {}).get("status") == "complete":
            return video_id
        if state == "error":
            raise RuntimeError(f"Facebook failed to process the video: {status}")
        time.sleep(10)
    print(f"Still processing after {timeout_s}s; check the Page later (video id {video_id}).")
    return video_id
