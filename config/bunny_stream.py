import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BUNNY_STREAM_BASE = "https://video.bunnycdn.com/library"


def _headers():
    return {
        "AccessKey": settings.BUNNY_STREAM_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def create_video(title: str) -> dict:
    """
    Create a video entry in Bunny Stream and return upload credentials.
    Returns: {video_id, upload_url}
    """
    library_id = settings.BUNNY_STREAM_LIBRARY_ID
    url = f"{BUNNY_STREAM_BASE}/{library_id}/videos"
    resp = requests.post(url, json={"title": title}, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    video_id = data["guid"]
    upload_url = f"{BUNNY_STREAM_BASE}/{library_id}/videos/{video_id}"
    return {"video_id": video_id, "upload_url": upload_url}


def get_video(video_id: str) -> dict:
    """
    Get video details from Bunny Stream.
    Returns: {video_id, status, thumbnail_url, embed_url, hls_url}
    status: 0=queued, 1=processing, 2=encoding, 3=finished, 4=error, 5=upload_failed
    """
    library_id = settings.BUNNY_STREAM_LIBRARY_ID
    url = f"{BUNNY_STREAM_BASE}/{library_id}/videos/{video_id}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cdn_hostname = data.get("cdnHostname", "")
    return {
        "video_id": video_id,
        "status": data.get("status", 0),
        "status_label": _status_label(data.get("status", 0)),
        "thumbnail_url": f"https://{cdn_hostname}/{video_id}/thumbnail.jpg" if cdn_hostname else None,
        "embed_url": f"https://iframe.mediadelivery.net/embed/{library_id}/{video_id}",
        "hls_url": f"https://{cdn_hostname}/{video_id}/playlist.m3u8" if cdn_hostname else None,
        "duration_seconds": data.get("length", 0),
    }


def delete_video(video_id: str) -> bool:
    """Delete a video from Bunny Stream. Returns True on success."""
    library_id = settings.BUNNY_STREAM_LIBRARY_ID
    url = f"{BUNNY_STREAM_BASE}/{library_id}/videos/{video_id}"
    try:
        resp = requests.delete(url, headers=_headers(), timeout=15)
        return resp.status_code in (200, 204, 404)
    except Exception as e:
        logger.error(f"Failed to delete Bunny video {video_id}: {e}")
        return False


def _status_label(status_code: int) -> str:
    labels = {0: "queued", 1: "processing", 2: "encoding", 3: "ready", 4: "error", 5: "upload_failed"}
    return labels.get(status_code, "unknown")
