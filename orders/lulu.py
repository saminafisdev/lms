"""
Lulu Print-on-Demand API client.

Lulu handles printing and international shipping of physical books.
Docs: https://developers.lulu.com/
"""

import logging
import time
import threading

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Thread-safe token cache: {"access_token": str, "expires_at": float}
_token_cache: dict = {}
_token_lock = threading.Lock()


def _get_auth_url():
    base = settings.LULU_API_URL.rstrip("/")
    return f"{base}/auth/realms/glasstree/protocol/openid-connect/token"


def get_access_token() -> str:
    """
    Fetch a Lulu OAuth2 Bearer token using client credentials.
    Cached in memory until 60 seconds before expiry.
    """
    with _token_lock:
        now = time.time()
        if _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > now + 60:
            return _token_cache["access_token"]

        resp = requests.post(
            _get_auth_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": settings.LULU_CLIENT_KEY,
                "client_secret": settings.LULU_CLIENT_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 3600)
        return _token_cache["access_token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }


def create_print_job(
    *,
    title: str,
    interior_pdf_url: str,
    cover_image_url: str,
    pod_package_id: str,
    quantity: int,
    contact_email: str,
    shipping_address: dict,
    shipping_level: str = "MAIL",
) -> dict:
    """
    Create a Lulu print job.

    shipping_address must contain:
        name, street1, city, country_code, postcode, phone_number, email
    Optional: street2, state_code

    Returns the full Lulu print job response dict (includes id, status, etc.).
    Raises requests.HTTPError on failure.
    """
    url = f"{settings.LULU_API_URL.rstrip('/')}/print-jobs/"

    payload = {
        "contact_email": contact_email,
        "line_items": [
            {
                "title": title,
                "quantity": quantity,
                "pod_package_id": pod_package_id,
                "interior": {"source_url": interior_pdf_url},
                "cover": {"source_url": cover_image_url},
            }
        ],
        "shipping_address": shipping_address,
        "shipping_level": shipping_level,
    }

    resp = requests.post(url, json=payload, headers=_headers(), timeout=30)

    if not resp.ok:
        logger.error(
            "Lulu create_print_job failed: %s — %s", resp.status_code, resp.text
        )
        resp.raise_for_status()

    result = resp.json()
    logger.info("Lulu print job created: id=%s status=%s", result.get("id"), result.get("status"))
    return result


def get_print_job(print_job_id: str) -> dict:
    """Fetch the current status of a Lulu print job."""
    url = f"{settings.LULU_API_URL.rstrip('/')}/print-jobs/{print_job_id}/"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_print_specs() -> list:
    """
    Return a reference list of common Lulu pod_package_id codes.

    Lulu does not expose an API endpoint for this — the id is a fixed-format
    code encoding: trim size + color + quality + binding + paper weight + laminate.

    Format: {width}X{height}{color}{quality}{binding}{paper_weight}{laminate}
    Docs: https://developers.lulu.com/pages/docs/misc/pod-package-id
    """
    return [
        # ── Paperback / Perfect Bind — Standard ─────────────────────────────
        {"id": "0600X0900BWSTDPB060UW444MXX", "description": "6×9\" B&W Standard Paperback (60# uncoated)"},
        {"id": "0600X0900FCSTDPB060UW444MXX", "description": "6×9\" Full Color Standard Paperback (60# uncoated)"},
        {"id": "0600X0900BWSTDPB080CW444MXX", "description": "6×9\" B&W Standard Paperback (80# coated white)"},
        {"id": "0550X0850BWSTDPB060UW444MXX", "description": "5.5×8.5\" B&W Standard Paperback (60# uncoated)"},
        {"id": "0550X0850FCSTDPB060UW444MXX", "description": "5.5×8.5\" Full Color Standard Paperback (60# uncoated)"},
        {"id": "0825X1075BWSTDPB060UW444MXX", "description": "8.25×10.75\" B&W Standard Paperback (60# uncoated)"},
        {"id": "0825X1075FCSTDPB060UW444MXX", "description": "8.25×10.75\" Full Color Standard Paperback (60# uncoated)"},
        {"id": "0827X1169BWSTDPB060UW444MXX", "description": "A4 (8.27×11.69\") B&W Standard Paperback (60# uncoated)"},
        {"id": "0827X1169FCSTDPB060UW444MXX", "description": "A4 (8.27×11.69\") Full Color Standard Paperback (60# uncoated)"},
        {"id": "0850X1100BWSTDPB060UW444MXX", "description": "8.5×11\" B&W Standard Paperback (60# uncoated)"},
        {"id": "0850X1100FCSTDPB060UW444MXX", "description": "8.5×11\" Full Color Standard Paperback (60# uncoated)"},
        # ── Paperback / Perfect Bind — Premium (for high ink coverage PDFs) ──
        {"id": "0600X0900FCPREPB060UW444MXX", "description": "6×9\" Full Color Premium Paperback (60# uncoated)"},
        {"id": "0550X0850FCPREPB060UW444MXX", "description": "5.5×8.5\" Full Color Premium Paperback (60# uncoated)"},
        {"id": "0825X1075FCPREPB060UW444MXX", "description": "8.25×10.75\" Full Color Premium Paperback (60# uncoated)"},
        {"id": "0827X1169FCPREPB060UW444MXX", "description": "A4 (8.27×11.69\") Full Color Premium Paperback (60# uncoated)"},
        {"id": "0850X1100FCPREPB060UW444MXX", "description": "8.5×11\" Full Color Premium Paperback (60# uncoated)"},
        # ── Hardcover / Case Laminate — Standard ────────────────────────────
        {"id": "0600X0900BWSTDHC060UW444MXX", "description": "6×9\" B&W Hardcover (60# uncoated)"},
        {"id": "0600X0900FCSTDHC060UW444MXX", "description": "6×9\" Full Color Hardcover (60# uncoated)"},
        {"id": "0550X0850BWSTDHC060UW444MXX", "description": "5.5×8.5\" B&W Hardcover (60# uncoated)"},
        {"id": "0550X0850FCSTDHC060UW444MXX", "description": "5.5×8.5\" Full Color Hardcover (60# uncoated)"},
        {"id": "0850X1100BWSTDHC060UW444MXX", "description": "8.5×11\" B&W Hardcover (60# uncoated)"},
        {"id": "0850X1100FCSTDHC060UW444MXX", "description": "8.5×11\" Full Color Hardcover (60# uncoated)"},
        # ── Hardcover — Premium ──────────────────────────────────────────────
        {"id": "0600X0900FCPREHC060UW444MXX", "description": "6×9\" Full Color Premium Hardcover (60# uncoated)"},
        {"id": "0850X1100FCPREHC060UW444MXX", "description": "8.5×11\" Full Color Premium Hardcover (60# uncoated)"},
        # ── Saddle Stitch (booklet / magazine, 2–80 pages) ──────────────────
        {"id": "0600X0900BWSTDSS060UW444MXX", "description": "6×9\" B&W Saddle Stitch (60# uncoated)"},
        {"id": "0850X1100BWSTDSS060UW444MXX", "description": "8.5×11\" B&W Saddle Stitch (60# uncoated)"},
        {"id": "0850X1100FCSTDSS060UW444MXX", "description": "8.5×11\" Full Color Saddle Stitch (60# uncoated)"},
        {"id": "0850X1100FCPRESS060UW444MXX",  "description": "8.5×11\" Full Color Premium Saddle Stitch (60# uncoated)"},
    ]
