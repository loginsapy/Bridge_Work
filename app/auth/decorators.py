from functools import wraps
from flask import abort, session


def _get_user_from_session():
    # Avoid circular import at module import time
    try:
        from ..models import User
    except Exception:
        return None
    uid = session.get('_user_id')
    if not uid:
        return None
    try:
        return User.query.get(int(uid))
    except Exception:
        return None


def internal_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        if not getattr(user, 'is_internal', False):
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def client_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        return func(*args, **kwargs)

    return wrapper