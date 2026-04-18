import base64
import logging
import time
from datetime import timedelta
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

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


def get_available_host(start_datetime, duration_minutes, exclude_lesson_pk=None):
    """
    Returns the first room email from ZOOM_ROOM_EMAILS that has no overlapping
    live lesson at the given time slot.

    Falls back to "me" if ZOOM_ROOM_EMAILS is not configured (single account mode).
    Raises ValueError if all rooms are busy.
    """
    room_emails = getattr(settings, "ZOOM_ROOM_EMAILS", [])
    if not room_emails:
        return "me"

    end_datetime = start_datetime + timedelta(minutes=duration_minutes)

    from courses.models import Lesson
    candidates = Lesson.objects.filter(
        content_type="live",
        zoom_host_email__isnull=False,
        scheduled_at__lt=end_datetime,
    )
    if exclude_lesson_pk:
        candidates = candidates.exclude(pk=exclude_lesson_pk)

    busy_emails = set()
    for lesson in candidates:
        lesson_end = lesson.scheduled_at + timedelta(minutes=lesson.duration_in_minutes or 60)
        if lesson_end > start_datetime:
            busy_emails.add(lesson.zoom_host_email)

    for email in room_emails:
        if email not in busy_emails:
            return email

    raise ValueError(
        f"All {len(room_emails)} Zoom room(s) are occupied at "
        f"{start_datetime.strftime('%Y-%m-%d %H:%M')} UTC. "
        "Please reschedule or purchase additional licenses."
    )


def _strip_zoom_token(url):
    """Remove the tk= auth token from a Zoom join URL so it's not pre-authenticated."""
    parsed = urlparse(url)
    params = {k: v for k, v in parse_qs(parsed.query).items() if k != "tk"}
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


(topic, start_datetime, duration_minutes, agenda="", host_email=None, exclude_lesson_pk=None):
    """
    Creates a Zoom scheduled meeting.

    Args:
        topic: Meeting title string.
        start_datetime: Python datetime object (UTC-aware or naive UTC).
        duration_minutes: Duration in minutes.
        agenda: Optional description.
        host_email: Specific room email to use. If None, auto-picks from pool.
        exclude_lesson_pk: Lesson PK to exclude from the conflict check (used when rescheduling).

    Returns:
        dict with keys: meeting_id, join_url, start_url, host_email
    """
    if host_email is None:
        host_email = get_available_host(start_datetime, duration_minutes, exclude_lesson_pk=exclude_lesson_pk)

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
        f"https://api.zoom.us/v2/users/{host_email}/meetings",
        json=payload,
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "meeting_id": str(data["id"]),
        "join_url": _strip_zoom_token(data["join_url"]),
        "start_url": data["start_url"],
        "host_email": host_email,
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
