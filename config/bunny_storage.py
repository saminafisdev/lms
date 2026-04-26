import hashlib
import base64
import time

from django.conf import settings


def generate_bunny_signed_url(file_name: str, expiry_seconds: int = 7200) -> str:
    """
    Generate a Bunny.net token-authenticated signed URL for a stored file.

    Args:
        file_name: The file path as stored in the model FileField,
                   e.g. 'books/digital/mybook.pdf'
        expiry_seconds: How long the URL is valid (default 2 hours)

    Returns:
        A signed CDN URL:
        https://books.example.com/books/digital/mybook.pdf?token=ABC&expires=1714123456

    Prerequisites:
        - BUNNY_BOOKS_CDN_HOSTNAME: separate pull zone with Token Auth enabled (e.g. https://books.example.com)
        - BUNNY_TOKEN_KEY: Token Authentication key from that pull zone's Security settings
        - Token Authentication enabled only on the books pull zone (not the main CDN)
    """
    cdn_base = (settings.BUNNY_BOOKS_CDN_HOSTNAME or settings.BUNNY_CDN_HOSTNAME).rstrip("/")
    token_key = settings.BUNNY_TOKEN_KEY
    expiry = int(time.time()) + expiry_seconds

    file_path = "/" + file_name.lstrip("/")

    # Bunny token formula: base64(SHA256(token_key + file_path + expiry))
    raw = token_key + file_path + str(expiry)
    token_hash = base64.b64encode(
        hashlib.sha256(raw.encode()).digest()
    ).decode()

    # Bunny expects URL-safe base64 without padding
    token_hash = token_hash.replace("+", "-").replace("/", "_").replace("=", "")

    return f"{cdn_base}{file_path}?token={token_hash}&expires={expiry}"
