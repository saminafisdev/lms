import hashlib
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BUNNY_STREAM_BASE = "https://video.bunnycdn.com/library"
BUNNY_TUS_ENDPOINT = "https://video.bunnycdn.com/tusupload"


def _headers():
    return {
        "AccessKey": settings.BUNNY_STREAM_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def create_video(title: str) -> dict:
    """
    Create a video entry in Bunny Stream and return the video_id.
    Returns: {video_id}
    """
    library_id = settings.BUNNY_STREAM_LIBRARY_ID
    url = f"{BUNNY_STREAM_BASE}/{library_id}/videos"
    resp = requests.post(url, json={"title": title}, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {"video_id": data["guid"]}


def generate_tus_credentials(video_id: str, title: str, expires_in: int = 86400) -> dict:
    """
    Generate presigned TUS upload credentials for direct browser-to-Bunny upload.
    The API key is never exposed to the frontend — only the HMAC signature is returned.

    Returns: {tus_endpoint, video_id, library_id, expiration_time, signature, title}
    """
    library_id = str(settings.BUNNY_STREAM_LIBRARY_ID)
    api_key = settings.BUNNY_STREAM_API_KEY
    expiration_time = int(time.time()) + expires_in

    signature_string = f"{library_id}{api_key}{expiration_time}{video_id}"
    signature = hashlib.sha256(signature_string.encode()).hexdigest()

    return {
        "tus_endpoint": BUNNY_TUS_ENDPOINT,
        "video_id": video_id,
        "library_id": library_id,
        "expiration_time": expiration_time,
        "signature": signature,
        "title": title,
    }


def get_video(video_id: str) -> dict:
    """
    Get video details from Bunny Stream.
    Returns: {video_id, status, thumbnail_url, embed_url, hls_url}
    status: 0=created, 1=uploaded, 2=processing, 3=transcoding, 4=finished, 5=error, 6=upload_failed
    """
    library_id = settings.BUNNY_STREAM_LIBRARY_ID
    url = f"{BUNNY_STREAM_BASE}/{library_id}/videos/{video_id}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cdn_hostname = data.get("cdnHostname") or data.get("storageZone", "")
    video_url_base = f"https://{cdn_hostname}/{video_id}" if cdn_hostname else None
    return {
        "video_id": video_id,
        "status": data.get("status", 0),
        "status_label": _status_label(data.get("status", 0)),
        "thumbnail_url": f"{video_url_base}/thumbnail.jpg" if video_url_base else None,
        "embed_url": f"https://iframe.mediadelivery.net/embed/{library_id}/{video_id}",
        "hls_url": f"{video_url_base}/playlist.m3u8" if video_url_base else None,
        "duration_seconds": data.get("length", 0),
        "raw_status": data.get("status", 0),
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
    labels = {0: "created", 1: "uploaded", 2: "processing", 3: "transcoding", 4: "ready", 5: "error", 6: "upload_failed"}
    return labels.get(status_code, "unknown")
