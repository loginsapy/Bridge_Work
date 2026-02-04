from flask import jsonify, request, abort, current_app
from . import api_bp
from .. import db
from ..models import Project, Task, TimeEntry, User, TaskAttachment
from sqlalchemy.exc import SQLAlchemyError
from datetime import date, datetime
from marshmallow import ValidationError
from .schemas import ProjectSchema, TaskSchema, TimeEntrySchema
from flask_login import current_user
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
        
        db.session.commit()
        # If API provided multiple assignees, assign them after creation
        if validated.get('assignees'):
            users = User.query.filter(User.id.in_(validated.get('assignees'))).all()
            t.assignees = users
            db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))
    return jsonify(task_to_dict(t)), 201


@api_bp.route("/tasks/<int:task_id>", methods=["PUT", "PATCH"])
def update_task(task_id):
    t = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    
    # Role-based restrictions: participants and clients may only change 'status' via API
    from flask_login import current_user
    is_pmp_admin = (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name in ('PMP','Admin'))
    is_participant = (getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_internal', False) and getattr(current_user, 'role', None) and current_user.role.name == 'Participante')
    is_client = (not getattr(current_user, 'is_internal', True)) and (t.project and t.project.client_id == getattr(current_user, 'id', None))

    if is_participant or is_client:
        allowed_keys = {'status'}
        extra = set([k for k in data.keys() if k not in allowed_keys])
        if extra:
            return jsonify({'error': 'No tienes permiso para modificar campos además de status'}), 403

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
        new_start = parse_datetime(data['start_date']) if 'start_date' in data else t.start_date
        new_due = parse_datetime(data['due_date']) if 'due_date' in data else t.due_date
        is_valid, error_msg = Task.validate_dates(new_start, new_due)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

    # Capture old assignment values to detect changes
    old_assigned_to = t.assigned_to_id
    old_assigned_client = t.assigned_client_id
    old_assignees = set([u.id for u in t.assignees]) if getattr(t, 'assignees', None) else set()

    for field in ["project_id", "parent_task_id", "title", "description", "assigned_to_id", "assigned_client_id", "status", "priority", "start_date", "due_date", "is_external_visible", "estimated_hours"]:
        if field in data:
            if field in ["start_date", "due_date"]:
                # Only PMP/Admin users may modify date fields
                from flask_login import current_user
                if not (getattr(current_user, 'is_authenticated', False) and current_user.is_internal and getattr(current_user, 'role', None) and current_user.role.name in ('PMP', 'Admin')):
                    return jsonify({'error': 'No tienes permiso para modificar fechas'}), 403
                setattr(t, field, parse_datetime(data[field]))
            else:
                if field == 'status':
                    # Normalize and set canonical status
                    t.set_status(data[field])
                else:
                    setattr(t, field, data[field])

    # Handle 'assignees' (list of user ids) explicitly
    if 'assignees' in data:
        try:
            new_ids = set([int(x) for x in (data.get('assignees') or [])])
        except Exception:
            return jsonify({'error': 'assignees must be a list of user ids'}), 400
        users = User.query.filter(User.id.in_(list(new_ids))).all()
        t.assignees = users

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        abort(500, description=str(e))

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
            entity_type='task',
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


@api_bp.route("/attachments/<int:attachment_id>", methods=["DELETE"])
def delete_attachment(attachment_id):
    """Delete a task attachment"""
    if not current_user.is_authenticated:
        abort(401)
    
    attachment = TaskAttachment.query.get_or_404(attachment_id)
    task = attachment.task
    
    # Check permissions - only internal users or the uploader can delete
    can_delete = False
    if current_user.is_internal:
        can_delete = True
    elif attachment.uploaded_by_id == current_user.id:
        can_delete = True
    
    if not can_delete:
        abort(403, description="No tienes permiso para eliminar este archivo")
    
    try:
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
        abort(500, description=str(e))
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
    """Generate a unique filename to avoid duplicates"""
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = 'file'
    
    name, ext = os.path.splitext(safe_name)
    if not ext:
        ext = ''
    
    task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task_id}')
    os.makedirs(task_folder, exist_ok=True)
    
    final_name = safe_name
    counter = 1
    while os.path.exists(os.path.join(task_folder, final_name)):
        final_name = f"{name}_{counter}{ext}"
        counter += 1
    
    return final_name, task_folder


@api_bp.route("/tasks/<int:task_id>/attachments", methods=["POST"])
def upload_attachment(task_id):
    """Upload attachment(s) to a task"""
    if not current_user.is_authenticated:
        abort(401)
    
    task = Task.query.get_or_404(task_id)
    
    # Check permissions - internal users or assigned client can upload
    can_upload = False
    if current_user.is_internal:
        can_upload = True
    elif task.assigned_client_id == current_user.id:
        can_upload = True
    
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

