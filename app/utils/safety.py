import os


def is_safe_db_uri(uri: str) -> bool:
    """Return True if the URI looks like a local/test DB we can safely drop.

    Safe URIs:
    - sqlite (in-memory or file)
    - postgres/mysql on localhost or 127.0.0.1

    Otherwise return False.
    """
    if not uri:
        return False
    u = uri.lower()
    # sqlite is always local
    if u.startswith('sqlite'):
        return True
    # localhost or 127.0.0.1 is acceptable
    if 'localhost' in u or '127.0.0.1' in u:
        return True
    return False


def require_confirmation(env_var: str, message: str) -> bool:
    """Return True only when the given env var equals 'YES'."""
    return os.environ.get(env_var, '').lower() in ('yes', 'true', '1')