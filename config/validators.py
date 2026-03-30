# config/validators.py
import bleach

ALLOWED_TAGS = [
    'p', 'strong', 'em', 'u', 'h1', 'h2', 'h3',
    'ul', 'ol', 'li', 'a', 'blockquote', 'code', 'pre'
]
ALLOWED_ATTRIBUTES = {'a': ['href', 'title', 'target']}

def sanitize_html(value):
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)