"""Validation shared by submission writes and rendered external links."""

import unicodedata
from urllib.parse import urlsplit


URL_FIELDS = ('repo_url', 'demo_video_url', 'live_url')


def validate_external_url(field_name, value):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValueError(f'{field_name}: must be a URL string.')
    value = value.strip()
    if not value:
        return ''
    if len(value) > 1024:
        raise ValueError(f'{field_name}: must be at most 1024 characters.')
    if any(char.isspace() or unicodedata.category(char).startswith('C') for char in value):
        raise ValueError(f'{field_name}: whitespace and control characters are not allowed.')
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f'{field_name}: must be an absolute HTTP or HTTPS URL.') from exc
    if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
        raise ValueError(f'{field_name}: must be an absolute HTTP or HTTPS URL.')
    return value


def safe_link(value):
    """Return a renderable external URL only when its scheme and host are safe."""
    try:
        return validate_external_url('url', value)
    except (TypeError, ValueError):
        return ''
