import os


def is_safe_db_uri(uri: str) -> bool:
    """Return True if the URI points to a local/test DB (localhost or 127.0.0.1).

    Remote URIs (production PostgreSQL) return False.
    """
    if not uri:
        return False
    u = uri.lower()
    if 'localhost' in u or '127.0.0.1' in u:
        return True
    return False


def require_confirmation(env_var: str, message: str) -> bool:
    """Return True only when the given env var equals 'YES'."""
    return os.environ.get(env_var, '').lower() in ('yes', 'true', '1')