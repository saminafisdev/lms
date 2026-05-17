# config/validators.py
import bleach

# Recommended: allow most safe tags/attrs for admin blog content
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union({
    'p', 'span', 'div', 'img', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'pre', 'code',
    'blockquote', 'ul', 'ol', 'li', 'br', 'hr', 'sup', 'sub', 'u', 's', 'mark', 'small', 'b', 'i', 'strong', 'em'
})
ALLOWED_ATTRIBUTES = {
    '*': ['style', 'class', 'id', 'title'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'style', 'class'],
    'td': ['colspan', 'rowspan', 'style', 'class'],
    'th': ['colspan', 'rowspan', 'style', 'class'],
}
ALLOWED_STYLES = [
    'color', 'background-color', 'font-weight', 'font-style', 'text-decoration', 'font-size',
    'width', 'height', 'border', 'border-collapse', 'padding', 'margin', 'text-align',
    'vertical-align', 'float', 'display', 'max-width', 'min-width', 'max-height', 'min-height',
]
def sanitize_html(value):
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        styles=ALLOWED_STYLES,
        strip=True
    )