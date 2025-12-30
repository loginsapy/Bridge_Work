from flask import jsonify, request, abort
from . import api_bp
from .. import db
from ..models import Project, Task, TimeEntry
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime
from marshmallow import ValidationError
from .schemas import ProjectSchema, TaskSchema, TimeEntrySchema
from flask_login import current_user
from ..auth.decorators import internal_required, client_required

# Simple serializers

def project_to_dict(p: Project):
    return {
        "id": p.id,
        "name": p.name,
        "client_id": p.client_id,
        "manager_id": p.manager_id,
        "status": p.status,
        "project_type": p.project_type,
        "metadata_json": p.metadata_json,
        "budget_hours": float(p.budget_hours) if p.budget_hours is not None else None,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
    }


def task_to_dict(t: Task):
    return {
        "id": t.id,
        "project_id": t.project_id,
        "parent_task_id": t.parent_task_id,
        "title": t.title,
        "description": t.description,
        "assigned_to_id": t.assigned_to_id,
        "assigned_client_id": t.assigned_client_id,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "is_external_visible": t.is_external_visible,
        "estimated_hours": float(t.estimated_hours) if t.estimated_hours is not None else None,
    }


def timeentry_to_dict(te: TimeEntry):
    return {
        "id": te.id,
        "task_id": te.task_id,
        "user_id": te.user_id,
        "date": te.date.isoformat() if te.date else None,
        "hours": float(te.hours) if te.hours is not None else None,
        "description": te.description,
        "is_billable": te.is_billable,
        "created_at": te.created_at.isoformat() if te.created_at else None,
    }


# Helpers to parse dates/datetimes from ISO strings

def parse_date(val):
    if val is None:
        return None
    if isinstance(val, str):
        return date.fromisoformat(val)
    return val


def parse_datetime(val):
    if val is None:
        return None
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


# Projects endpoints
@api_bp.route("/projects", methods=["GET"])
def list_projects():
    # Pagination and optional filters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    q = Project.query
    if 'status' in request.args:
        q = q.filter(Project.status == request.args['status'])
    if 'manager_id' in request.args:
        try:
            mid = int(request.args['manager_id'])
            q = q.filter(Project.manager_id == mid)
        except ValueError:
            return jsonify({"error": "invalid manager_id"}), 400

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "items": [project_to_dict(p) for p in items],
        "meta": {"total": total, "page": page, "per_page": per_page},
    })


@api_bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    p = Project.query.get_or_404(project_id)
    return jsonify(project_to_dict(p))


@api_bp.route("/projects", methods=["POST"])
@internal_required
def create_project():
    data = request.get_json() or {}
    schema = ProjectSchema()
    try:
        validated = schema.load(data)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    p = Project(
        name=validated.get("name"),
        client_id=validated.get("client_id"),
        manager_id=validated.get("manager_id"),
        status=validated.get("status", "PLANNING"),
        project_type=validated.get("project_type", "APP_DEVELOPMENT"),
        metadata_json=validated.get("metadata_json"),
        budget_hours=validated.get("budget_hours"),
        start_date=validated.get("start_date"),
        end_date=validated.get("end_date"),
    )
    try:
        db.session.add(p)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(project_to_dict(p)), 201


@api_bp.route("/projects/<int:project_id>", methods=["PUT", "PATCH"])
@internal_required
def update_project(project_id):
    p = Project.query.get_or_404(project_id)
    data = request.get_json() or {}
    schema = ProjectSchema()
    try:
        validated = schema.load(data, partial=True)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    for key, value in validated.items():
        setattr(p, key, value)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(project_to_dict(p))


@api_bp.route("/projects/<int:project_id>", methods=["DELETE"])
@internal_required
def delete_project(project_id):
    p = Project.query.get_or_404(project_id)
    try:
        db.session.delete(p)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify({"deleted": project_id}), 200


# Tasks endpoints
@api_bp.route("/tasks", methods=["GET"])
def list_tasks():
    # Pagination and filters for tasks
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    q = Task.query
    if 'project_id' in request.args:
        try:
            pid = int(request.args['project_id'])
            q = q.filter(Task.project_id == pid)
        except ValueError:
            return jsonify({"error": "invalid project_id"}), 400
    if 'assigned_to_id' in request.args:
        try:
            aid = int(request.args['assigned_to_id'])
            q = q.filter(Task.assigned_to_id == aid)
        except ValueError:
            return jsonify({"error": "invalid assigned_to_id"}), 400
    if 'status' in request.args:
        q = q.filter(Task.status == request.args['status'])

    # Visibility filter: unless user is internal, return only externally visible tasks
    from flask import session as _session
    user = None
    if _session.get('_user_id'):
        from ..models import User
        try:
            user = User.query.get(int(_session.get('_user_id')))
        except Exception:
            user = None
    if not (user and getattr(user, 'is_internal', False)):
        # If unauthenticated, only public external tasks
        if user is None:
            q = q.filter(Task.is_external_visible == True)
        else:
            # Logged-in non-internal (client): only show tasks in client's projects that are either external-visible or assigned to the client
            from ..models import Project
            client_project_ids = Project.query.with_entities(Project.id).filter(Project.clients.contains(user)).subquery()
            q = q.filter(Task.project_id.in_(client_project_ids)).filter(
                (Task.is_external_visible == True) | (Task.assigned_client_id == user.id)
            )

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "items": [task_to_dict(t) for t in items],
        "meta": {"total": total, "page": page, "per_page": per_page},
    })


@api_bp.route("/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    t = Task.query.get_or_404(task_id)
    # Visibility: external users should only see tasks with is_external_visible=True
    from flask import session as _session
    user = None
    if _session.get('_user_id'):
        from ..models import User
        try:
            user = User.query.get(int(_session.get('_user_id')))
        except Exception:
            user = None
    if not (user and getattr(user, 'is_internal', False)):
        # Unauthenticated users: only external visible tasks
        if user is None:
            if not t.is_external_visible:
                abort(403)
        else:
            # Logged-in non-internal (client): allow if task is external-visible within a project the user belongs to, or if the task is assigned to the client
            allowed = False
            if t.is_external_visible and user in t.project.clients:
                allowed = True
            if t.assigned_client_id == getattr(user, 'id', None):
                allowed = True
            if not allowed:
                abort(403)
    return jsonify(task_to_dict(t))


@api_bp.route("/tasks", methods=["POST"])
@internal_required
def create_task():
    data = request.get_json() or {}
    schema = TaskSchema()
    try:
        validated = schema.load(data)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    t = Task(
        project_id=validated.get("project_id"),
        parent_task_id=validated.get("parent_task_id"),
        title=validated.get("title"),
        description=validated.get("description"),
        assigned_to_id=validated.get("assigned_to_id"),
        status=validated.get("status", "BACKLOG"),
        priority=validated.get("priority", "MEDIUM"),
        due_date=validated.get("due_date"),
        is_external_visible=validated.get("is_external_visible", False),
        estimated_hours=validated.get("estimated_hours"),
    )
    try:
        db.session.add(t)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(task_to_dict(t)), 201


@api_bp.route("/tasks/<int:task_id>", methods=["PUT", "PATCH"])
def update_task(task_id):
    t = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    # Validate status transition wrt predecessors
    if 'status' in data and data['status'] in ('DONE', 'COMPLETED'):
        incomplete = [p for p in t.predecessors if p.status not in ('DONE', 'COMPLETED')]
        if incomplete:
            return jsonify({
                'error': 'Cannot complete task while predecessors are incomplete',
                'incomplete_predecessors': [{'id': p.id, 'title': p.title} for p in incomplete]
            }), 400
        # Also prevent completing if any descendant (successor chain) is incomplete
        incomplete_desc = [d for d in t.descendants() if d.status not in ('DONE', 'COMPLETED')]
        if incomplete_desc:
            return jsonify({
                'error': 'Cannot complete task while descendants are incomplete',
                'incomplete_descendants': [{'id': d.id, 'title': d.title} for d in incomplete_desc]
            }), 400

    for field in ["project_id", "parent_task_id", "title", "description", "assigned_to_id", "assigned_client_id", "status", "priority", "due_date", "is_external_visible", "estimated_hours"]:
        if field in data:
            if field == "due_date":
                setattr(t, field, parse_datetime(data[field]))
            else:
                setattr(t, field, data[field])
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(task_to_dict(t))


@api_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    t = Task.query.get_or_404(task_id)
    try:
        db.session.delete(t)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify({"deleted": task_id}), 200


# TimeEntries endpoints
@api_bp.route("/time_entries", methods=["GET"])
def list_time_entries():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    q = TimeEntry.query
    if 'task_id' in request.args:
        try:
            tid = int(request.args['task_id'])
            q = q.filter(TimeEntry.task_id == tid)
        except ValueError:
            return jsonify({"error": "invalid task_id"}), 400
    if 'user_id' in request.args:
        try:
            uid = int(request.args['user_id'])
            q = q.filter(TimeEntry.user_id == uid)
        except ValueError:
            return jsonify({"error": "invalid user_id"}), 400

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "items": [timeentry_to_dict(te) for te in items],
        "meta": {"total": total, "page": page, "per_page": per_page},
    })


@api_bp.route("/time_entries/<int:entry_id>", methods=["GET"])
def get_time_entry(entry_id):
    te = TimeEntry.query.get_or_404(entry_id)
    return jsonify(timeentry_to_dict(te))


@api_bp.route("/time_entries", methods=["POST"])
def create_time_entry():
    data = request.get_json() or {}
    schema = TimeEntrySchema()
    try:
        validated = schema.load(data)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    te = TimeEntry(
        task_id=validated.get("task_id"),
        user_id=validated.get("user_id"),
        date=validated.get("date"),
        hours=validated.get("hours"),
        description=validated.get("description"),
        is_billable=validated.get("is_billable", True),
    )
    try:
        db.session.add(te)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(timeentry_to_dict(te)), 201


@api_bp.route("/time_entries/<int:entry_id>", methods=["PUT", "PATCH"])
def update_time_entry(entry_id):
    te = TimeEntry.query.get_or_404(entry_id)
    data = request.get_json() or {}
    schema = TimeEntrySchema()
    try:
        validated = schema.load(data, partial=True)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    for key, value in validated.items():
        setattr(te, key, value)
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(timeentry_to_dict(te))


@api_bp.route("/time_entries/<int:entry_id>", methods=["DELETE"])
def delete_time_entry(entry_id):
    te = TimeEntry.query.get_or_404(entry_id)
    try:
        db.session.delete(te)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify({"deleted": entry_id}), 200
