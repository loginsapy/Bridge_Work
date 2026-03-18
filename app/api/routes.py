from flask import jsonify, request, abort, current_app
from . import api_bp
from .. import db, limiter
from ..models import Project, Task, TimeEntry, User, TaskAttachment
from ..models import AuditLog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from datetime import date, datetime
from marshmallow import ValidationError
from .schemas import ProjectSchema, TaskSchema, TimeEntrySchema
from flask_login import current_user, login_required
from ..auth.decorators import internal_required, client_required
import os
import mimetypes
from werkzeug.utils import secure_filename

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
        "assignees": [u.id for u in (t.assignees or [])],
        "assignees_info": [{"id": u.id, "name": (u.first_name or u.email.split('@')[0])} for u in (t.assignees or [])],
        "assigned_client_id": t.assigned_client_id,
        "status": t.status,
        "priority": t.priority,
        "start_date": t.start_date.isoformat() if t.start_date else None,
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
        try:
            return date.fromisoformat(val)
        except ValueError:
            raise ValueError(f'Formato de fecha inválido: {val!r}. Use YYYY-MM-DD.')
    return val


def parse_datetime(val):
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            raise ValueError(f'Formato de fecha/hora inválido: {val!r}. Use ISO 8601.')
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
@limiter.limit("30/minute")
def create_project():
    from flask_login import current_user
    # Prevent participants from creating projects via API
    if current_user.role and current_user.role.name == 'Participante':
        return jsonify({"error": "No tienes permiso para crear proyectos."}), 403

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
        current_app.logger.exception('Error creating project: %s', e)
        abort(500, description='Error interno del servidor')
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
        current_app.logger.exception('Error updating project %s: %s', project_id, e)
        abort(500, description='Error interno del servidor')
    return jsonify(project_to_dict(p))


@api_bp.route("/projects/<int:project_id>", methods=["DELETE"])
@internal_required
def delete_project(project_id):
    p = Project.query.get_or_404(project_id)
    # Cascade delete tasks and related records to avoid FK constraint errors
    tasks = Task.query.filter(Task.project_id == p.id).all()
    try:
        for t in tasks:
            # delete time entries
            TimeEntry.query.filter(TimeEntry.task_id == t.id).delete(synchronize_session='evaluate')
            # delete attachments records and try to remove files
            atts = TaskAttachment.query.filter(TaskAttachment.task_id == t.id).all()
            for a in atts:
                try:
                    task_folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', ''), f'task_{t.id}')
                    if task_folder and os.path.exists(os.path.join(task_folder, a.stored_filename)):
                        os.remove(os.path.join(task_folder, a.stored_filename))
                except Exception:
                    current_app.logger.exception('Failed to remove attachment file for %s', a.id)
            TaskAttachment.query.filter(TaskAttachment.task_id == t.id).delete(synchronize_session='evaluate')

            # audit task deletion
            audit = AuditLog(
                user_id=getattr(current_user, 'id', None) or 0,
                action='DELETE',
                entity_type='task',
                entity_id=t.id,
                changes={'task_title': t.title}
            )
            db.session.add(audit)

            db.session.delete(t)

        db.session.delete(p)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception('Error deleting project %s: %s', project_id, e)
        abort(500, description='Error interno del servidor')
    return jsonify({"deleted": project_id}), 200


@api_bp.route("/projects/<int:project_id>/wip-limits", methods=["PATCH"])
@internal_required
def update_wip_limits(project_id):
    """Update WIP limits for a project's Kanban columns (PMP/Admin only)."""
    if not (current_user.role and current_user.role.name in ('PMP', 'Admin')):
        abort(403)
    project = Project.query.get_or_404(project_id)
    data = request.get_json(silent=True) or {}
    limits = data.get('wip_limits', {})
    # Validate: values must be positive int or null
    clean = {}
    for col in ('BACKLOG', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED'):
        v = limits.get(col)
        if v is not None:
            try:
                v = int(v)
                if v < 1:
                    return jsonify({'error': f'WIP limit for {col} must be >= 1'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': f'Invalid WIP limit for {col}'}), 400
        clean[col] = v
    meta = project.metadata_json or {}
    old_limits = (meta.get('wip_limits') or {}).copy() if isinstance(meta.get('wip_limits'), dict) else {}
    meta['wip_limits'] = clean
    project.metadata_json = meta
    try:
        if old_limits != clean:
            audit = AuditLog(
                user_id=getattr(current_user, 'id', None),
                action='UPDATE',
                entity_type='Project',
                entity_id=project.id,
                changes={
                    'wip_limits': {
                        'old': old_limits,
                        'new': clean,
                    }
                }
            )
            db.session.add(audit)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Failed to save WIP limits for project %s', project_id)
        abort(500, description='Error interno del servidor')
    return jsonify({'wip_limits': clean})


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
    if 'assignee_id' in request.args:
        try:
            aid = int(request.args['assignee_id'])
            q = q.filter((Task.assigned_to_id == aid) | (Task.assignees.any(User.id == aid)))
        except ValueError:
            return jsonify({"error": "invalid assignee_id"}), 400
    if 'status' in request.args:
        status = request.args['status']
        if status == 'DONE':
            status = 'COMPLETED'
        q = q.filter(Task.status == status)

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
@limiter.limit("60/minute")
def create_task():
    from flask_login import current_user
    # Prevent participants from creating tasks via API
    if current_user.role and current_user.role.name == 'Participante':
        return jsonify({"error": "No tienes permiso para crear tareas."}), 403

    data = request.get_json() or {}
    schema = TaskSchema()
    try:
        validated = schema.load(data)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    from flask_login import current_user

    # Prevent non-PMP/Admin users from setting dates
    if (validated.get('start_date') or validated.get('due_date')):
        if not (getattr(current_user, 'is_authenticated', False) and current_user.is_internal and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
            return jsonify({'error': 'No tienes permiso para establecer fechas'}), 403

    # Validar coherencia de fechas
    start_date = validated.get('start_date')
    due_date = validated.get('due_date')
    is_valid, error_msg = Task.validate_dates(start_date, due_date)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    t = Task(
        project_id=validated.get("project_id"),
        parent_task_id=validated.get("parent_task_id"),
        title=validated.get("title"),
        description=validated.get("description"),
        assigned_to_id=validated.get("assigned_to_id"),
        status=validated.get("status", "BACKLOG"),
        priority=validated.get("priority", "MEDIUM"),
        start_date=validated.get("start_date"),
        due_date=validated.get("due_date"),
        is_external_visible=validated.get("is_external_visible", False),
        estimated_hours=validated.get("estimated_hours"),
    )
    try:
        db.session.add(t)
        db.session.flush()  # Get task ID

        # Assign position at the end of the list
        max_position = db.session.query(db.func.max(Task.position)).filter(Task.project_id == t.project_id).scalar()
        t.position = (max_position + 1) if max_position is not None else 0

        # Validate and assign predecessors (with cycle detection)
        if validated.get('predecessors'):
            predecessor_ids = [int(pid) for pid in validated.get('predecessors')]
            try:
                t.validate_predecessor_ids(predecessor_ids)
            except ValueError as e:
                db.session.rollback()
                return jsonify({'error': str(e)}), 400
            t.predecessors = Task.query.filter(Task.id.in_(predecessor_ids)).all()

        db.session.commit()
        # If API provided multiple assignees, assign them after creation
        if validated.get('assignees'):
            users = User.query.filter(User.id.in_(validated.get('assignees'))).all()
            t.assignees = users
            db.session.commit()

        # Audit CREATE after task is fully persisted (including assignees).
        try:
            audit = AuditLog(
                user_id=getattr(current_user, 'id', None),
                action='CREATE',
                entity_type='Task',
                entity_id=t.id,
                changes={
                    'title': t.title,
                    'status': t.status,
                    'priority': t.priority,
                    'project_id': t.project_id,
                    'assignees': sorted([u.id for u in (t.assignees or [])]),
                    'start_date': t.start_date.isoformat() if t.start_date else None,
                    'due_date': t.due_date.isoformat() if t.due_date else None,
                }
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to write audit CREATE for task %s', t.id)
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')

    # Dispatch webhook task.created (non-blocking)
    try:
        from app.services import webhook_service
        project = Project.query.get(t.project_id) if t.project_id else None
        actor = current_user if getattr(current_user, 'is_authenticated', False) else None
        webhook_service.dispatch('task.created', {
            'task_id': t.id,
            'task_title': t.title,
            'project_id': t.project_id,
            'project_name': project.name if project else None,
            'user_name': actor.name if actor else None,
            'new_status': t.status,
        })
    except Exception:
        current_app.logger.exception('Error dispatching webhook for created task %s', t.id)

    return jsonify(task_to_dict(t)), 201


@api_bp.route("/tasks/bulk", methods=["PATCH"])
@login_required
def bulk_update_tasks():
    """Apply a single field change to multiple tasks at once.

    Body: { "task_ids": [1,2,3], "field": "status"|"priority"|"assignees", "value": ... }
    Returns: { "updated": [ids], "skipped": [ids], "errors": [...] }
    """
    data = request.get_json(force=True, silent=True) or {}
    task_ids = data.get('task_ids', [])
    field    = data.get('field', '')
    value    = data.get('value')

    if not task_ids or not field:
        return jsonify({'error': 'task_ids y field son requeridos'}), 400

    allowed_fields = {'status', 'priority', 'assignees'}
    if field not in allowed_fields:
        return jsonify({'error': f'Campo no permitido: {field}'}), 400

    user_role = current_user.role.name if current_user.role else None

    updated = []
    skipped = []
    errors  = []

    for tid in task_ids:
        try:
            t = Task.query.get(tid)
            if not t:
                skipped.append(tid)
                continue

            # Permission check
            can_edit = user_role in ('PMP', 'Admin') or t.assigned_to_id == current_user.id
            if not can_edit:
                skipped.append(tid)
                continue

            if field == 'status':
                if value not in ('BACKLOG', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED'):
                    errors.append({'id': tid, 'error': f'Estado inválido: {value}'})
                    continue
                t.status = value
                if value == 'COMPLETED':
                    from datetime import datetime as _dt
                    t.completed_at = _dt.now()

            elif field == 'priority':
                if value not in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'):
                    errors.append({'id': tid, 'error': f'Prioridad inválida: {value}'})
                    continue
                t.priority = value

            elif field == 'assignees':
                # value is a list of user IDs
                ids = [int(i) for i in (value or [])]
                from ..models import User as _User
                new_assignees = _User.query.filter(_User.id.in_(ids)).all()
                t.assignees = new_assignees
                if new_assignees:
                    t.assigned_to_id = new_assignees[0].id

            updated.append(tid)
        except Exception as e:
            errors.append({'id': tid, 'error': str(e)})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

    return jsonify({'updated': updated, 'skipped': skipped, 'errors': errors})


@api_bp.route("/tasks/bulk", methods=["DELETE"])
@login_required
def bulk_delete_tasks():
    """Delete multiple tasks and log each deletion to AuditLog.

    Body: { "task_ids": [1,2,3] }
    Returns: { "deleted": [ids], "skipped": [ids], "errors": [...] }
    """
    data = request.get_json(force=True, silent=True) or {}
    task_ids = data.get('task_ids', [])

    if not task_ids:
        return jsonify({'error': 'task_ids es requerido'}), 400

    # Only PMP and Admin can bulk-delete
    user_role = current_user.role.name if current_user.role else None
    if not (current_user.is_internal and user_role in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden eliminar tareas'}), 403

    deleted = []
    skipped = []
    errors  = []

    for tid in task_ids:
        try:
            t = Task.query.get(tid)
            if not t:
                skipped.append(tid)
                continue

            audit = AuditLog(
                user_id=current_user.id,
                action='DELETE',
                entity_type='Task',
                entity_id=t.id,
                changes={
                    'message': f"Tarea '{t.title}' eliminada en lote por {current_user.email}",
                    'task_title': t.title,
                    'project_id': t.project_id,
                    'bulk': True,
                }
            )
            db.session.add(audit)
            db.session.delete(t)
            deleted.append(tid)
        except Exception as e:
            errors.append({'id': tid, 'error': str(e)})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

    return jsonify({'deleted': deleted, 'skipped': skipped, 'errors': errors})


@api_bp.route("/tasks/<int:task_id>", methods=["PUT", "PATCH"])
def update_task(task_id):
    t = Task.query.get_or_404(task_id)
    data = request.get_json() or {}

    def _serialize(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, set):
            return sorted(list(value))
        return value

    def _field_value(task_obj, field_name):
        if field_name == 'assignees':
            return sorted([u.id for u in (task_obj.assignees or [])])
        if field_name == 'predecessors':
            return sorted([p.id for p in (task_obj.predecessors or [])])
        return getattr(task_obj, field_name, None)
    
    # Role-based restrictions: participants and clients may only change 'status' via API
    from flask_login import current_user
    is_pmp_admin = (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name in ('PMP','Admin'))
    is_participant = (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name == 'Participante')
    is_client = not getattr(current_user, 'is_internal', True)

    is_assigned_participant = bool(
        is_participant and (
            t.assigned_to_id == getattr(current_user, 'id', None) or
            (getattr(t, 'assignees', None) and any(u.id == getattr(current_user, 'id', None) for u in t.assignees))
        )
    )

    if is_participant and not is_assigned_participant:
        return jsonify({'error': 'Solo puedes cambiar estado de tareas asignadas a ti.'}), 403

    if is_participant:
        allowed_keys = {'status'}
        extra = set([k for k in data.keys() if k not in allowed_keys])
        if extra:
            return jsonify({'error': 'No tienes permiso para modificar campos además de status'}), 403
    elif is_client:
        # Clients may set approval_status on tasks assigned to them
        allowed_keys = {'status', 'approval_status', 'approval_notes'}
        if 'approval_status' in data and t.assigned_client_id != getattr(current_user, 'id', None):
            return jsonify({'error': 'Solo puedes aprobar/rechazar tareas asignadas a ti'}), 403
        extra = set([k for k in data.keys() if k not in allowed_keys])
        if extra:
            return jsonify({'error': 'No tienes permiso para modificar esos campos'}), 403

    # Validate status transition using can_advance_status (normalize legacy values)
    if 'status' in data:
        from app.models import Task as TaskModel
        status_val = TaskModel.normalize_status(data['status'])
        can_advance, error_msg, blockers = t.can_advance_status(status_val)
        if not can_advance:
            return jsonify({
                'error': error_msg,
                **(blockers or {})
            }), 400

    # Validar coherencia de fechas antes de actualizar
    if 'start_date' in data or 'due_date' in data:
        try:
            new_start = parse_datetime(data['start_date']) if 'start_date' in data else t.start_date
            new_due = parse_datetime(data['due_date']) if 'due_date' in data else t.due_date
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        is_valid, error_msg = Task.validate_dates(new_start, new_due)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

    # Capture old values to detect changes
    old_status = t.status
    old_assigned_to = t.assigned_to_id
    old_assigned_client = t.assigned_client_id
    old_assignees = set([u.id for u in t.assignees]) if getattr(t, 'assignees', None) else set()

    audit_fields = set(data.keys())
    # Assignees and predecessors are managed outside the generic field loop.
    audit_fields.update({'assignees', 'predecessors'} & set(data.keys()))
    old_values = {k: _serialize(_field_value(t, k)) for k in audit_fields}

    # Handle approval fields
    if 'approval_status' in data:
        valid_statuses = {'PENDING', 'APPROVED', 'REJECTED'}
        if data['approval_status'] not in valid_statuses:
            return jsonify({'error': f'approval_status must be one of {valid_statuses}'}), 400
        t.approval_status = data['approval_status']
        if data['approval_status'] in ('APPROVED', 'REJECTED'):
            t.approved_by_id = getattr(current_user, 'id', None)
            t.approved_at = datetime.now()
        if 'approval_notes' in data:
            t.approval_notes = data.get('approval_notes', '')

    for field in ["project_id", "parent_task_id", "title", "description", "assigned_to_id", "assigned_client_id", "status", "priority", "start_date", "due_date", "is_external_visible", "estimated_hours"]:
        if field in data:
            if field in ["start_date", "due_date"]:
                # Only PMP/Admin users may modify date fields
                from flask_login import current_user
                if not (getattr(current_user, 'is_authenticated', False) and current_user.is_internal and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
                    return jsonify({'error': 'No tienes permiso para modificar fechas'}), 403
                try:
                    setattr(t, field, parse_datetime(data[field]))
                except ValueError as e:
                    return jsonify({'error': str(e)}), 400
            else:
                if field == 'status':
                    # Normalize and set canonical status
                    t.set_status(data[field])
                else:
                    setattr(t, field, data[field])

    # Handle 'predecessors' (list of task ids) with cycle detection
    if 'predecessors' in data:
        try:
            predecessor_ids = [int(pid) for pid in (data.get('predecessors') or [])]
        except Exception:
            return jsonify({'error': 'predecessors must be a list of task ids'}), 400
        try:
            t.validate_predecessor_ids(predecessor_ids)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        t.predecessors = Task.query.filter(Task.id.in_(predecessor_ids)).all()

    # Handle 'assignees' (list of user ids) explicitly
    if 'assignees' in data:
        try:
            new_ids = set([int(x) for x in (data.get('assignees') or [])])
        except Exception:
            return jsonify({'error': 'assignees must be a list of user ids'}), 400
        users = User.query.filter(User.id.in_(list(new_ids))).all()
        t.assignees = users
        # Maintain backward compatibility: set assigned_to_id to first assignee or clear it
        if users:
            try:
                t.assigned_to_id = users[0].id
            except Exception:
                t.assigned_to_id = None
        else:
            t.assigned_to_id = None

    try:
        # Capture final values and build audit diff before commit.
        new_values = {k: _serialize(_field_value(t, k)) for k in audit_fields}
        changes = {}
        for key in sorted(audit_fields):
            if old_values.get(key) != new_values.get(key):
                changes[key] = {
                    'old': old_values.get(key),
                    'new': new_values.get(key)
                }

        if changes:
            audit = AuditLog(
                user_id=getattr(current_user, 'id', None),
                action='UPDATE',
                entity_type='Task',
                entity_id=t.id,
                changes=changes
            )
            db.session.add(audit)

        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')

    # After commit: notify on assignment changes (for API updates)
    try:
        from flask_login import current_user
        from app.services.notifications import NotificationService
        from app.models import SystemSettings

        send_email_setting = SystemSettings.get('notify_task_assigned', 'true')
        send_email = send_email_setting == 'true' or send_email_setting == True

        # assigned_to change
        new_assigned_to = t.assigned_to_id
        if 'assigned_to_id' in data and new_assigned_to and new_assigned_to != old_assigned_to:
            NotificationService.notify_task_assigned(task=t, assigned_by_user=current_user if getattr(current_user, 'is_authenticated', False) else None, send_email=send_email, notify_client=False)

        # assigned_client change
        new_assigned_client = t.assigned_client_id
        if 'assigned_client_id' in data and new_assigned_client and new_assigned_client != old_assigned_client:
            NotificationService.notify_task_assigned(task=t, assigned_by_user=current_user if getattr(current_user, 'is_authenticated', False) else None, send_email=send_email, notify_client=True)

        # assignees change: notify newly added assigned users
        new_assignees = set([u.id for u in t.assignees]) if getattr(t, 'assignees', None) else set()
        added = new_assignees - old_assignees
        if added:
            # Build email_context
            project = Project.query.get(t.project_id) if t.project_id else None
            for uid in added:
                try:
                    NotificationService.notify(
                        user_id=uid,
                        title='Nueva tarea asignada',
                        message=f"Se te ha asignado la tarea '{t.title}'{(' en el proyecto '+project.name) if project else ''}",
                        notification_type=NotificationService.TASK_ASSIGNED,
                        related_entity_type='task',
                        related_entity_id=t.id,
                        send_email=send_email,
                        email_context={'task': t, 'project': project, 'assigned_by': current_user}
                    )
                except Exception:
                    current_app.logger.exception('Failed to notify new assignee %s for task %s', uid, t.id)

    except Exception as e:
        # Log and ignore notification errors to keep API update successful
        current_app.logger.exception('Error while sending assignment notifications: %s', e)

    # Dispatch webhooks (non-blocking)
    try:
        from app.services import webhook_service
        project = Project.query.get(t.project_id) if t.project_id else None
        actor = current_user if getattr(current_user, 'is_authenticated', False) else None
        webhook_data = {
            'task_id': t.id,
            'task_title': t.title,
            'project_id': t.project_id,
            'project_name': project.name if project else None,
            'user_name': actor.name if actor else None,
        }
        if 'status' in data and t.status != old_status:
            webhook_data['old_status'] = old_status
            webhook_data['new_status'] = t.status
            if t.status == 'COMPLETED':
                webhook_service.dispatch('task.completed', webhook_data)
            else:
                webhook_service.dispatch('task.status_changed', webhook_data)
        new_assignees_after = set([u.id for u in t.assignees]) if getattr(t, 'assignees', None) else set()
        if new_assignees_after - old_assignees:
            webhook_service.dispatch('task.assigned', webhook_data)
    except Exception:
        current_app.logger.exception('Error dispatching webhooks for task %s', task_id)

    return jsonify(task_to_dict(t))


@api_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    t = Task.query.get_or_404(task_id)
    from flask_login import current_user
    # Solo PMP y Admin pueden borrar
    if not (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden borrar tareas'}), 403
    try:
        # Auditoría antes de borrar
        from app.models import AuditLog
        # AuditLog fields: entity_type, entity_id, action, user_id, changes
        audit = AuditLog(
            user_id=getattr(current_user, 'id', None),
            action='DELETE',
            entity_type='Task',
            entity_id=t.id,
            changes={
                'message': f"Tarea '{t.title}' eliminada por {getattr(current_user, 'email', 'sistema')}",
                'task_title': t.title
            }
        )
        db.session.add(audit)
        db.session.delete(t)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')
    return jsonify({"deleted": task_id}), 200


# ── Task Predecessors (dependencies) ─────────────────────────────────────────

@api_bp.route("/tasks/<int:task_id>/predecessors", methods=["GET"])
@login_required
def get_task_predecessors(task_id):
    task = Task.query.get_or_404(task_id)
    return jsonify({
        'task_id': task.id,
        'predecessors': [{'id': p.id, 'title': p.title, 'status': p.status} for p in task.predecessors]
    })


@api_bp.route("/tasks/<int:task_id>/predecessors", methods=["POST"])
@login_required
def add_task_predecessor(task_id):
    from flask_login import current_user
    if not (current_user.is_internal and current_user.role and current_user.role.name in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden gestionar dependencias'}), 403
    data = request.get_json(force=True, silent=True) or {}
    pred_id = data.get('predecessor_id')
    if not pred_id:
        return jsonify({'error': 'predecessor_id requerido'}), 400
    task = Task.query.get_or_404(task_id)
    pred = Task.query.get_or_404(pred_id)
    if pred.project_id != task.project_id:
        return jsonify({'error': 'La tarea predecesora debe ser del mismo proyecto'}), 400
    if pred in task.predecessors:
        return jsonify({'error': 'Ya existe esa dependencia'}), 409
    if task.id == pred.id:
        return jsonify({'error': 'Una tarea no puede ser su propio predecesor'}), 400
    # Cycle check
    try:
        existing_ids = [p.id for p in task.predecessors]
        task.validate_predecessor_ids(existing_ids + [pred.id])
    except ValueError as e:
        return jsonify({'error': str(e)}), 409
    task.predecessors.append(pred)
    db.session.commit()
    return jsonify({'ok': True, 'predecessor': {'id': pred.id, 'title': pred.title, 'status': pred.status}}), 201


@api_bp.route("/tasks/<int:task_id>/predecessors/<int:pred_id>", methods=["DELETE"])
@login_required
def remove_task_predecessor(task_id, pred_id):
    from flask_login import current_user
    if not (current_user.is_internal and current_user.role and current_user.role.name in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden gestionar dependencias'}), 403
    task = Task.query.get_or_404(task_id)
    pred = Task.query.get(pred_id)
    if pred and pred in task.predecessors:
        task.predecessors.remove(pred)
        db.session.commit()
    return jsonify({'ok': True})


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

    # Validar que la tarea no tiene predecesoras incompletas
    task_id = validated.get("task_id")
    if task_id:
        task = Task.query.get(task_id)
        if task:
            incomplete_preds = task.incomplete_predecessors()
            if incomplete_preds:
                pred_names = ', '.join([p.title for p in incomplete_preds[:3]])
                return jsonify({
                    "error": f"No se puede registrar tiempo. La tarea tiene predecesoras incompletas: {pred_names}",
                    "blocked_by": [{"id": p.id, "title": p.title} for p in incomplete_preds]
                }), 400

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
        # Notify project manager or PMP users about new time entry
        try:
            from app.services.notifications import NotificationService
            project = Task.query.get(te.task_id).project if te.task_id else None
            notified = False
            if project and project.manager_id and project.manager_id != te.user_id:
                NotificationService.notify(
                    user_id=project.manager_id,
                    title='Nuevo registro de tiempo',
                    message=f"{te.user_id} registró {te.hours}h en la tarea '{Task.query.get(te.task_id).title}'",
                    notification_type=NotificationService.GENERAL,
                    related_entity_type='task',
                    related_entity_id=te.task_id,
                    send_email=True
                )
                notified = True
            if not notified:
                # fallback: notify all active PMP users (excluding the actor)
                from app.models import User, Role
                pmps = User.query.join(Role).filter(Role.name == 'PMP', User.is_active == True).all()
                for u in pmps:
                    if u.id == te.user_id:
                        continue
                    try:
                        NotificationService.notify(
                            user_id=u.id,
                            title='Nuevo registro de tiempo',
                            message=f"{te.user_id} registró {te.hours}h en la tarea '{Task.query.get(te.task_id).title}'",
                            notification_type=NotificationService.GENERAL,
                            related_entity_type='task',
                            related_entity_id=te.task_id,
                            send_email=True
                        )
                    except Exception:
                        current_app.logger.exception('Failed to notify PMP %s about time entry %s', u.id, te.id)
        except Exception:
            current_app.logger.exception('Failed to send time entry notifications')

        # Audit creation of time entry
        try:
            audit = AuditLog(
                user_id=te.user_id if te.user_id is not None else 0,
                action='CREATE',
                entity_type='time_entry',
                entity_id=te.id,
                changes={
                    'task_id': te.task_id,
                    'hours': float(te.hours) if te.hours is not None else None,
                    'description': te.description
                }
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            current_app.logger.exception('Failed to write AuditLog for time entry create')
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')
    return jsonify(timeentry_to_dict(te)), 201


@api_bp.route("/time_entries/<int:entry_id>", methods=["PUT", "PATCH"])
def update_time_entry(entry_id):
    te = TimeEntry.query.get_or_404(entry_id)
    from flask_login import current_user
    # Only PMP or Admin may update time entries via API
    if not (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden modificar registros de tiempo'}), 403
    data = request.get_json() or {}
    schema = TimeEntrySchema()
    try:
        validated = schema.load(data, partial=True)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    # Capture old values for audit
    old_values = {
        'task_id': te.task_id,
        'hours': float(te.hours) if te.hours is not None else None,
        'description': te.description,
        'is_billable': bool(te.is_billable)
    }
    for key, value in validated.items():
        setattr(te, key, value)
    try:
        db.session.commit()
        # Audit update
        try:
            audit = AuditLog(
                user_id=getattr(current_user, 'id', 0),
                action='UPDATE',
                entity_type='time_entry',
                entity_id=te.id,
                changes={'old': old_values, 'new': validated}
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            current_app.logger.exception('Failed to write AuditLog for time entry update')
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')
    return jsonify(timeentry_to_dict(te))


@api_bp.route("/time_entries/<int:entry_id>", methods=["DELETE"])
def delete_time_entry(entry_id):
    te = TimeEntry.query.get_or_404(entry_id)
    from flask_login import current_user
    # Only PMP or Admin may delete time entries via API
    if not (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
        return jsonify({'error': 'Solo PMP o Admin pueden eliminar registros de tiempo'}), 403
    try:
        # Audit before delete
        try:
            audit = AuditLog(
                user_id=getattr(current_user, 'id', 0),
                action='DELETE',
                entity_type='time_entry',
                entity_id=te.id,
                changes={
                    'task_id': te.task_id,
                    'hours': float(te.hours) if te.hours is not None else None,
                    'description': te.description
                }
            )
            db.session.add(audit)
            db.session.flush()
        except Exception:
            current_app.logger.exception('Failed to write AuditLog for time entry delete')

        db.session.delete(te)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')
    return jsonify({"deleted": entry_id}), 200


@api_bp.route("/attachments/<int:attachment_id>", methods=["DELETE"])
def delete_attachment(attachment_id):
    """Delete a task attachment"""
    if not current_user.is_authenticated:
        abort(401)
    
    attachment = TaskAttachment.query.get_or_404(attachment_id)
    task = attachment.task

    # Use session-based user lookup to avoid Flask-Login current_user caching issues
    from ..auth.decorators import _get_user_from_session
    _user = _get_user_from_session()

    # Check permissions - only PMP/Admin (internal) or the original uploader may delete
    can_delete = False
    if _user and _user.is_internal and _user.role and _user.role.name in ('PMP', 'Admin'):
        can_delete = True
    elif _user and attachment.uploaded_by_id == _user.id:
        can_delete = True

    if not can_delete:
        abort(403, description="No tienes permiso para eliminar este archivo")
    
    try:
        # audit entry before removal
        try:
            audit = AuditLog(
                user_id=_user.id if _user else getattr(current_user, 'id', 0),
                action='DELETE',
                entity_type='task_attachment',
                entity_id=attachment.id,
                changes={
                    'task_id': task.id,
                    'filename': attachment.filename,
                }
            )
            db.session.add(audit)
            db.session.flush()
        except Exception:
            current_app.logger.exception('Failed to write AuditLog for attachment delete')

        # Delete the physical file
        task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task.id}')
        filepath = os.path.join(task_folder, attachment.stored_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Delete from database
        db.session.delete(attachment)
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description='Error interno del servidor')
    except OSError as e:
        current_app.logger.error(f"Error deleting file: {e}")
        # Still delete from DB even if file deletion fails
        db.session.delete(attachment)
        db.session.commit()
    
    return jsonify({"deleted": attachment_id}), 200


def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = current_app.config.get('ALLOWED_EXTENSIONS', {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_unique_filename(task_id, filename):
    """Generate a unique filename using UUID to avoid race conditions."""
    import uuid as _uuid
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = 'file'

    _, ext = os.path.splitext(safe_name)
    # Use UUID to guarantee uniqueness without filesystem race conditions
    final_name = f"{_uuid.uuid4().hex}{ext}"

    task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task_id}')
    os.makedirs(task_folder, exist_ok=True)

    return final_name, task_folder


@api_bp.route("/tasks/<int:task_id>/attachments", methods=["POST"])
@limiter.limit("20/minute")
def upload_attachment(task_id):
    """Upload attachment(s) to a task"""
    if not current_user.is_authenticated:
        abort(401)
    
    task = Task.query.get_or_404(task_id)
    
    # Check permissions - only users assigned to this task can upload
    assigned_user_ids = set([u.id for u in task.assignees]) if getattr(task, 'assignees', None) else set()
    can_upload = bool(
        task.assigned_to_id == current_user.id or
        current_user.id in assigned_user_ids or
        task.assigned_client_id == current_user.id
    )
    
    if not can_upload:
        return jsonify({"error": "No tienes permiso para subir archivos a esta tarea"}), 403
    
    if 'file' not in request.files:
        return jsonify({"error": "No se encontró archivo"}), 400
    
    files = request.files.getlist('file')
    uploaded = []
    errors = []
    
    for file in files:
        if file and file.filename:
            if not allowed_file(file.filename):
                errors.append(f"Tipo de archivo no permitido: {file.filename}")
                continue
            
            try:
                stored_filename, task_folder = get_unique_filename(task_id, file.filename)
                filepath = os.path.join(task_folder, stored_filename)
                file.save(filepath)
                
                file_size = os.path.getsize(filepath)
                mime_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
                
                attachment = TaskAttachment(
                    task_id=task_id,
                    filename=file.filename,
                    stored_filename=stored_filename,
                    file_size=file_size,
                    mime_type=mime_type,
                    uploaded_by_id=current_user.id
                )
                db.session.add(attachment)
                db.session.commit()
                
                uploaded.append({
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "file_size": attachment.file_size
                })
            except Exception as e:
                current_app.logger.error(f"Error uploading attachment: {e}")
                errors.append(f"Error al subir {file.filename}: {str(e)}")
    
    return jsonify({
        "uploaded": uploaded,
        "errors": errors,
        "success": len(uploaded) > 0
    }), 200 if uploaded else 400


# User endpoints (for admin)
from ..models import User

def user_to_dict(u: User):
    return {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "name": u.name,
        "role_id": u.role_id,
        "is_internal": u.is_internal,
        "is_active": u.is_active,
        "is_azure": bool(u.azure_oid),
        "azure_oid": u.azure_oid,
        "company": u.company,
        "phone": u.phone,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@api_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """Get user details for admin editing"""
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.role or current_user.role.name not in ('Admin', 'PMP'):
        abort(403)
    
    user = User.query.get_or_404(user_id)
    return jsonify(user_to_dict(user))


# ==================== LICENSE ENDPOINTS ====================
from ..services import license_service

@api_bp.route("/license/activate", methods=["POST"])
@limiter.limit("10/minute")
def activate_license():
    """Activate a new license"""
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.role or current_user.role.name != 'Admin':
        abort(403, description="Solo administradores pueden activar licencias")
    
    data = request.get_json()
    current_app.logger.debug('License activation request payload: %s', data)
    if not data or not data.get('license_key'):
        return jsonify({"success": False, "message": "Se requiere clave de licencia"}), 400
    
    result = license_service.activate_license(data['license_key'])
    # Log result for debugging
    if not result.get('success'):
        current_app.logger.warning('License activation failed: %s', result.get('message'))
        # Prefer explicit http_status from service when available
        if result.get('http_status'):
            return jsonify(result), result.get('http_status')
        msg = result.get('message', 'Error al activar licencia')
        # Distinguish network or external-service errors to return appropriate HTTP codes
        if 'No se pudo conectar' in msg or 'Tiempo de espera' in msg or 'Error al activar licencia:' in msg:
            return jsonify(result), 503
        return jsonify(result), 400
    return jsonify(result), 200


# ==================== WEBHOOK ENDPOINTS ====================
from ..services import webhook_service as _wh


def _require_admin():
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.role or current_user.role.name not in ('Admin', 'PMP'):
        abort(403, description='Solo administradores/PMP pueden gestionar webhooks')


def _validate_webhook_url(url: str) -> bool:
    """Validates webhook URL is safe: must be http/https and not point to internal/private IPs."""
    from urllib.parse import urlparse
    import ipaddress
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.hostname
        if not host:
            return False
        # Block loopback and common internal hostnames
        if host.lower() in ('localhost', '127.0.0.1', '::1', '0.0.0.0', 'metadata.google.internal'):
            return False
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                return False
        except ValueError:
            pass  # It's a hostname, not a raw IP — allow it
        return True
    except Exception:
        return False


@api_bp.route('/webhooks', methods=['GET'])
@limiter.limit("30/minute")
def list_webhooks():
    _require_admin()
    webhooks = _wh.get_webhooks()
    # Mask secret in list view
    safe = [{**w, 'secret': '***' if w.get('secret') else ''} for w in webhooks]
    return jsonify({'webhooks': safe, 'available_events': _wh.EVENTS})


@api_bp.route('/webhooks', methods=['POST'])
@limiter.limit("20/minute")
def create_webhook():
    _require_admin()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    url = (data.get('url') or '').strip()
    events = data.get('events') or []
    secret = data.get('secret', '')
    active = bool(data.get('active', True))

    if not name:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    if not _validate_webhook_url(url):
        return jsonify({'error': 'URL inválida. Debe ser http/https y no apuntar a IPs privadas.'}), 400
    if not events:
        return jsonify({'error': 'Selecciona al menos un evento'}), 400
    invalid = [e for e in events if e not in _wh.EVENTS]
    if invalid:
        return jsonify({'error': f'Eventos inválidos: {invalid}'}), 400

    wh = _wh.upsert_webhook(None, name, url, events, secret, active)
    return jsonify(wh), 201


@api_bp.route('/webhooks/<webhook_id>', methods=['PUT', 'PATCH'])
@limiter.limit("20/minute")
def update_webhook(webhook_id):
    _require_admin()
    data = request.get_json() or {}
    existing = next((w for w in _wh.get_webhooks() if w.get('id') == webhook_id), None)
    if not existing:
        abort(404)

    name = (data.get('name') or existing['name']).strip()
    url = (data.get('url') or existing['url']).strip()
    events = data.get('events', existing['events'])
    secret = data.get('secret', existing.get('secret', ''))
    # Don't overwrite secret if client sends '***' (masked)
    if secret == '***':
        secret = existing.get('secret', '')
    active = bool(data.get('active', existing.get('active', True)))

    if not name:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    if not _validate_webhook_url(url):
        return jsonify({'error': 'URL inválida. Debe ser http/https y no apuntar a IPs privadas.'}), 400

    wh = _wh.upsert_webhook(webhook_id, name, url, events, secret, active)
    return jsonify(wh)


@api_bp.route('/webhooks/<webhook_id>', methods=['DELETE'])
@limiter.limit("10/minute")
def delete_webhook(webhook_id):
    _require_admin()
    deleted = _wh.delete_webhook(webhook_id)
    if not deleted:
        abort(404)
    return jsonify({'deleted': webhook_id})


@api_bp.route('/webhooks/<webhook_id>/test', methods=['POST'])
@limiter.limit("10/minute")
def test_webhook_endpoint(webhook_id):
    _require_admin()
    result = _wh.test_webhook(webhook_id)
    status = 200 if result.get('success') else 502
    return jsonify(result), status


@api_bp.route('/webhooks/<webhook_id>/deliveries', methods=['GET'])
@limiter.limit("30/minute")
def get_webhook_deliveries(webhook_id):
    _require_admin()
    from app.models import WebhookDelivery
    limit = min(int(request.args.get('limit', 50)), 200)
    deliveries = (WebhookDelivery.query
                  .filter_by(webhook_id=webhook_id)
                  .order_by(WebhookDelivery.created_at.desc())
                  .limit(limit)
                  .all())
    # Summary stats
    total = WebhookDelivery.query.filter_by(webhook_id=webhook_id).count()
    success_count = WebhookDelivery.query.filter_by(webhook_id=webhook_id, success=True).count()
    return jsonify({
        'webhook_id': webhook_id,
        'total': total,
        'success_count': success_count,
        'failure_count': total - success_count,
        'success_rate': round(success_count / total * 100) if total else None,
        'deliveries': [d.to_dict() for d in deliveries],
    })


@api_bp.route("/license/validate", methods=["POST"])
def validate_license():
    """Validate current license"""
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.role or current_user.role.name != 'Admin':
        abort(403, description="Solo administradores pueden validar licencias")
    
    result = license_service.validate_license()
    if result.get('error_code') in ('network','timeout','external_server_error') or result.get('http_status'):
        return jsonify(result), result.get('http_status', 503)
    return jsonify(result), 200


@api_bp.route("/license/status", methods=["GET"])
def license_status():
    """Get current license status"""
    if not current_user.is_authenticated:
        abort(401)
    
    result = license_service.check_license_status()
    # Serialize license object if present
    if result.get('license'):
        lic = result['license']
        result['license'] = {
            'license_key': lic.license_key[:8] + '...' + lic.license_key[-4:] if len(lic.license_key) > 12 else lic.license_key,
            'status': lic.status,
            'license_type': lic.license_type,
            'customer_name': lic.customer_name,
            'max_users': lic.max_users,
            'activated_at': lic.activated_at.isoformat() if lic.activated_at else None,
            'expires_at': lic.expires_at.isoformat() if lic.expires_at else None,
            'last_validated_at': lic.last_validated_at.isoformat() if lic.last_validated_at else None
        }
    return jsonify(result), 200


@api_bp.route("/license/deactivate", methods=["POST"])
def deactivate_license():
    """Deactivate current license"""
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.role or current_user.role.name != 'Admin':
        abort(403, description="Solo administradores pueden desactivar licencias")
    
    result = license_service.deactivate_license()
    if not result.get('success'):
        current_app.logger.warning('License deactivation failed: %s', result.get('message'))
        if result.get('http_status'):
            return jsonify(result), result.get('http_status')
        if result.get('message') and ('No se pudo conectar' in result.get('message') or 'Tiempo de espera' in result.get('message')):
            return jsonify(result), 503
        return jsonify(result), 400
    return jsonify(result), 200

