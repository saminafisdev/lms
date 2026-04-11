import base64
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_token_cache = {"access_token": None, "expires_at": 0}


def _get_access_token():
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    credentials = base64.b64encode(
        f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode()
    ).decode()

    response = requests.post(
        "https://zoom.us/oauth/token",
        params={
            "grant_type": "account_credentials",
            "account_id": settings.ZOOM_ACCOUNT_ID,
        },
        headers={"Authorization": f"Basic {credentials}"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)

    return _token_cache["access_token"]


def _headers():
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
    }


def create_meeting(topic, start_datetime, duration_minutes, agenda=""):
    """
    Creates a Zoom scheduled meeting.

    Args:
        topic: Meeting title string.
        start_datetime: Python datetime object (UTC-aware or naive UTC).
        duration_minutes: Duration in minutes.
        agenda: Optional description.

    Returns:
        dict with keys: meeting_id, join_url, start_url
    """
    # "me" resolves to the account owner for Server-to-Server OAuth
    payload = {
        "topic": topic,
        "type": 2,  # Scheduled
        "start_time": start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration": duration_minutes,
        "timezone": "UTC",
        "agenda": agenda,
        "settings": {
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
            "waiting_room": True,
            "mute_upon_entry": True,
        },
    }

    response = requests.post(
        "https://api.zoom.us/v2/users/me/meetings",
        json=payload,
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "meeting_id": str(data["id"]),
        "join_url": data["join_url"],
        "start_url": data["start_url"],
    }


def delete_meeting(meeting_id):
    """Cancels a Zoom meeting. Silently ignores already-deleted meetings."""
    response = requests.delete(
        f"https://api.zoom.us/v2/meetings/{meeting_id}",
        headers=_headers(),
        timeout=10,
    )
    if response.status_code not in (204, 404):
        response.raise_for_status()
