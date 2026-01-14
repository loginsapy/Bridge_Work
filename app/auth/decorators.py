from functools import wraps
from flask import abort, session, flash, redirect, url_for


def _get_user_from_session():
    # Avoid circular import at module import time
    try:
        from ..models import User
        from .. import db
    except Exception:
        return None
    try:
        uid = session.get('_user_id')
    except RuntimeError:
        # No request/session context available
        return None
    if not uid:
        return None
    try:
        # Use db.session.get() to get a session-bound instance
        return db.session.get(User, int(uid))
    except Exception:
        return None


def admin_only(func):
    """Decorator to require Admin role only"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        if not user.role or user.role.name != 'Admin':
            flash('Solo los administradores pueden acceder a esta sección.', 'danger')
            return redirect(url_for('main.dashboard'))
        return func(*args, **kwargs)
    return wrapper


def pmp_or_admin_required(func):
    """Decorator to require PMP or Admin role"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        if not user.role or user.role.name not in ('Admin', 'PMP'):
            flash('No tienes permisos para acceder a esta sección.', 'danger')
            return redirect(url_for('main.dashboard'))
        return func(*args, **kwargs)
    return wrapper


def internal_required(func):
    """Decorator to require internal users (Admin, PMP, Participante)"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        if not getattr(user, 'is_internal', False):
            flash('Solo usuarios internos pueden acceder a esta sección.', 'danger')
            return redirect(url_for('main.dashboard'))
        return func(*args, **kwargs)
    return wrapper


def client_required(func):
    """Decorator for client access - any authenticated user"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _get_user_from_session()
        if not user:
            abort(401)
        return func(*args, **kwargs)
    return wrapper


def get_user_role_name(user):
    """Helper to safely get user role name"""
    if user and user.role:
        return user.role.name
    return None


def can_access_project(user, project):
    """Check if user can access a specific project based on role"""
    if not user or not project:
        return False
    
    role_name = get_user_role_name(user)
    
    # Admin and PMP can access all projects
    if role_name in ('Admin', 'PMP'):
        return True
    
    # Participante can access projects they are members of
    if role_name == 'Participante':
        return user in project.members or user.id == project.manager_id
    
    # Cliente can access projects they are associated with
    if role_name == 'Cliente':
        return user in project.clients or user.id == project.client_id
    
    return False


def can_access_task(user, task):
    """Check if user can access a specific task based on role"""
    if not user or not task:
        return False
    
    role_name = get_user_role_name(user)
    
    # Admin and PMP can access all tasks
    if role_name in ('Admin', 'PMP'):
        return True
    
    # Participante can access tasks assigned to them
    if role_name == 'Participante':
        if task.assignee_id == user.id:
            return True
        # Also check if they are members of the project
        if task.project and user in task.project.members:
            return True
        return False
    
    # Cliente can access tasks in their projects
    if role_name == 'Cliente':
        if task.project:
            return user in task.project.clients or user.id == task.project.client_id
        return False
    
    return False