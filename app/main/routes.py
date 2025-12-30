from datetime import datetime, timedelta, timezone
import os
import uuid
import mimetypes
from flask import render_template, jsonify, request, redirect, url_for, flash, abort, current_app, send_from_directory
from flask_login import current_user, login_required
from sqlalchemy import func
from werkzeug.utils import secure_filename

from . import main_bp
from .. import db
from ..models import Project, Task, TimeEntry, User, Role, TaskAttachment, AuditLog, SystemNotification, SystemSettings, HourlyRate, project_clients
from ..metrics import calculate_project_metrics
from ..services import NotificationService


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS', set())


def get_unique_filename(task_id, filename):
    """Generate a unique filename to avoid duplicates"""
    # Secure the filename first
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = 'file'
    
    # Get extension
    name, ext = os.path.splitext(safe_name)
    if not ext:
        ext = ''
    
    # Create task folder path
    task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task_id}')
    os.makedirs(task_folder, exist_ok=True)
    
    # Check if file with same name exists, if so, add unique suffix
    final_name = safe_name
    counter = 1
    while os.path.exists(os.path.join(task_folder, final_name)):
        final_name = f"{name}_{counter}{ext}"
        counter += 1
    
    return final_name, task_folder


def notify_clients_task_completed(task, completed_by_user=None):
    """Notifica a los clientes asociados al proyecto cuando una tarea se completa"""
    project = task.project
    
    # Marcar la tarea como pendiente de aprobación
    if task.requires_approval and task.is_external_visible:
        task.approval_status = 'PENDING'
        
        # Usar el servicio de notificaciones para notificar a clientes
        NotificationService.notify_task_completed(
            task=task,
            completed_by_user=completed_by_user,
            notify_client=True,
            send_email=True
        )
    else:
        # Notificar al creador del proyecto aunque no requiera aprobación
        NotificationService.notify_task_completed(
            task=task,
            completed_by_user=completed_by_user,
            notify_client=False,
            send_email=False  # Solo notificación in-app para completados normales
        )


@main_bp.route('/')
@login_required
def index():
    user_role = current_user.role.name if current_user.role else None
    
    # Usuario sin rol: mostrar dashboard vacío con mensaje
    if not user_role:
        return render_template(
            'dashboard.html',
            no_role=True,
            active_projects_count=0,
            hours_this_week=0,
            tasks_completed_count=0,
            avg_budget_usage=0,
            recent_projects=[],
            project_status_data={},
            budget_chart_labels=[],
            budget_chart_data_used=[],
            budget_chart_data_planned=[],
            recent_activity=[],
            projects_by_status={'PLANNING': [], 'ACTIVE': [], 'COMPLETED': [], 'ARCHIVED': []},
            active_team_members=[],
            now=datetime.now()
        )
    
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())

    # Filtrar datos según rol
    if user_role in ['PMP', 'Admin']:
        # PMP/Admin ve todo
        active_projects_count = db.session.query(func.count(Project.id)).filter(Project.status == 'ACTIVE').scalar()
        tasks_completed_count = db.session.query(func.count(Task.id)).filter(
            Task.status == 'COMPLETED',
            Task.assigned_to_id == current_user.id
        ).scalar()
        recent_projects = Project.query.order_by(Project.start_date.desc()).limit(5).all()
        recent_activity = Task.query.filter_by(status='COMPLETED').order_by(Task.due_date.desc()).limit(5).all()
        projects_by_status = {
            'PLANNING': Project.query.filter_by(status='PLANNING').order_by(Project.start_date.desc()).all(),
            'ACTIVE': Project.query.filter_by(status='ACTIVE').order_by(Project.start_date.desc()).all(),
            'COMPLETED': Project.query.filter_by(status='COMPLETED').order_by(Project.end_date.desc()).all(),
            'ARCHIVED': Project.query.filter_by(status='ARCHIVED').order_by(Project.end_date.desc()).all()
        }
    elif user_role == 'Participante':
        # Participante ve solo proyectos donde tiene tareas asignadas
        user_project_ids = db.session.query(Task.project_id).filter(
            Task.assigned_to_id == current_user.id
        ).distinct().subquery()
        
        active_projects_count = db.session.query(func.count(Project.id)).filter(
            Project.status == 'ACTIVE',
            Project.id.in_(user_project_ids)
        ).scalar()
        tasks_completed_count = db.session.query(func.count(Task.id)).filter(
            Task.status == 'COMPLETED',
            Task.assigned_to_id == current_user.id
        ).scalar()
        recent_projects = Project.query.filter(Project.id.in_(user_project_ids)).order_by(Project.start_date.desc()).limit(5).all()
        recent_activity = Task.query.filter(
            Task.status == 'COMPLETED',
            Task.assigned_to_id == current_user.id
        ).order_by(Task.due_date.desc()).limit(5).all()
        projects_by_status = {
            'PLANNING': Project.query.filter(Project.status == 'PLANNING', Project.id.in_(user_project_ids)).order_by(Project.start_date.desc()).all(),
            'ACTIVE': Project.query.filter(Project.status == 'ACTIVE', Project.id.in_(user_project_ids)).order_by(Project.start_date.desc()).all(),
            'COMPLETED': Project.query.filter(Project.status == 'COMPLETED', Project.id.in_(user_project_ids)).order_by(Project.end_date.desc()).all(),
            'ARCHIVED': Project.query.filter(Project.status == 'ARCHIVED', Project.id.in_(user_project_ids)).order_by(Project.end_date.desc()).all()
        }
    else:
        # Cliente u otros roles: proyectos donde es cliente
        client_project_ids = db.session.query(Project.id).filter(
            Project.clients.contains(current_user)
        ).subquery()
        
        active_projects_count = db.session.query(func.count(Project.id)).filter(
            Project.status == 'ACTIVE',
            Project.id.in_(client_project_ids)
        ).scalar()
        tasks_completed_count = 0
        recent_projects = Project.query.filter(Project.id.in_(client_project_ids)).order_by(Project.start_date.desc()).limit(5).all()
        recent_activity = []
        projects_by_status = {
            'PLANNING': Project.query.filter(Project.status == 'PLANNING', Project.id.in_(client_project_ids)).order_by(Project.start_date.desc()).all(),
            'ACTIVE': Project.query.filter(Project.status == 'ACTIVE', Project.id.in_(client_project_ids)).order_by(Project.start_date.desc()).all(),
            'COMPLETED': Project.query.filter(Project.status == 'COMPLETED', Project.id.in_(client_project_ids)).order_by(Project.end_date.desc()).all(),
            'ARCHIVED': Project.query.filter(Project.status == 'ARCHIVED', Project.id.in_(client_project_ids)).order_by(Project.end_date.desc()).all()
        }

    # KPI data común
    hours_this_week = db.session.query(func.sum(TimeEntry.hours)).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.date >= start_of_week
    ).scalar() or 0

    # Budget usage calculation
    projects_with_budget = Project.query.filter(Project.budget_hours.isnot(None)).all()
    total_projects_with_budget = len(projects_with_budget)
    total_budget_usage_percent = 0

    for p in projects_with_budget:
        if p.budget_hours > 0:
            total_hours_spent = db.session.query(func.sum(TimeEntry.hours)).join(Task).filter(Task.project_id == p.id).scalar() or 0
            usage_percent = (total_hours_spent / p.budget_hours) * 100
            total_budget_usage_percent += usage_percent

    avg_budget_usage = (total_budget_usage_percent / total_projects_with_budget) if total_projects_with_budget > 0 else 0

    # Calcular progreso de proyectos recientes
    for p in recent_projects:
        if p.budget_hours and p.budget_hours > 0:
            total_hours_spent = db.session.query(func.sum(TimeEntry.hours)).join(Task).filter(Task.project_id == p.id).scalar() or 0
            p.progress = (total_hours_spent / p.budget_hours) * 100
        else:
            p.progress = 0

    # Project status distribution
    project_status_counts = db.session.query(Project.status, func.count(Project.id)).group_by(Project.status).all()
    project_status_data = {status: count for status, count in project_status_counts}

    # Budget chart data (last 7 days)
    budget_chart_labels = []
    budget_chart_data_used = []
    budget_chart_data_planned = [] # Mocked planned data
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        budget_chart_labels.append(day.strftime('%a'))
        daily_hours = db.session.query(func.sum(TimeEntry.hours)).filter(TimeEntry.date == day).scalar() or 0
        budget_chart_data_used.append(float(daily_hours))
        # Simple linear progression for planned budget
        budget_chart_data_planned.append(float(sum(budget_chart_data_used) * 0.95 / (7-i)))

    # Usuarios internos con actividad reciente (time entries en las últimas 2 semanas)
    two_weeks_ago = today - timedelta(days=14)
    active_team_members = db.session.query(User).join(TimeEntry, TimeEntry.user_id == User.id).filter(
        User.is_internal == True,
        TimeEntry.date >= two_weeks_ago
    ).distinct().limit(6).all()
    
    # Agregar estadísticas a cada miembro
    for member in active_team_members:
        member.recent_tasks_count = db.session.query(func.count(func.distinct(Task.id))).join(
            TimeEntry, TimeEntry.task_id == Task.id
        ).filter(
            TimeEntry.user_id == member.id,
            TimeEntry.date >= two_weeks_ago
        ).scalar() or 0
        member.hours_logged = db.session.query(func.sum(TimeEntry.hours)).filter(
            TimeEntry.user_id == member.id,
            TimeEntry.date >= two_weeks_ago
        ).scalar() or 0


    return render_template(
        'dashboard.html',
        no_role=False,
        active_projects_count=active_projects_count,
        hours_this_week=hours_this_week,
        tasks_completed_count=tasks_completed_count,
        avg_budget_usage=avg_budget_usage,
        recent_projects=recent_projects,
        project_status_data=project_status_data,
        budget_chart_labels=budget_chart_labels,
        budget_chart_data_used=budget_chart_data_used,
        budget_chart_data_planned=budget_chart_data_planned,
        recent_activity=recent_activity,
        projects_by_status=projects_by_status,
        active_team_members=active_team_members,
        now=datetime.now()
    )


# Mockup preview routes for design review
@main_bp.route('/mock/dashboard')
def mock_dashboard():
    return render_template('mockups/dashboard_mockup.html')


@main_bp.route('/mock/project')
def mock_project():
    return render_template('mockups/project_mockup.html')


@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Solo PMP o Admin pueden editar proyectos
    user_role = current_user.role.name if current_user.role else None
    if user_role not in ['PMP', 'Admin']:
        flash('Solo usuarios PMP o Admin pueden editar proyectos.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project.id))
    
    # Obtener usuarios con rol Cliente para el selector
    client_role = Role.query.filter_by(name='Cliente').first()
    available_clients = User.query.filter_by(role_id=client_role.id).order_by(User.first_name).all() if client_role else []

    # Obtener usuarios con rol Participante para selector de miembros
    participant_role = Role.query.filter_by(name='Participante').first()
    available_members = User.query.filter_by(role_id=participant_role.id).order_by(User.first_name).all() if participant_role else []
    
    if request.method == 'POST':
        try:
            # Capturar valores anteriores para auditoría
            old_client_ids = [c.id for c in project.clients]
            old_member_ids = [m.id for m in project.members]
            old_values = {
                'name': project.name,
                'description': project.description,
                'budget_hours': float(project.budget_hours) if project.budget_hours else None,
                'status': project.status,
                'client_ids': old_client_ids,
                'member_ids': old_member_ids
            }
            
            # Aplicar cambios
            project.name = request.form.get('name') or project.name
            project.description = request.form.get('description')
            project.budget_hours = float(request.form.get('budget_hours')) if request.form.get('budget_hours') and request.form.get('budget_hours').strip() else project.budget_hours
            project.status = request.form.get('status', project.status)
            
            # Actualizar clientes asociados
            client_ids = request.form.getlist('client_ids')
            new_clients = User.query.filter(User.id.in_(client_ids)).all() if client_ids else []
            project.clients = new_clients

            # Actualizar miembros participantes
            member_ids = request.form.getlist('member_ids')
            # Ensure we include existing member ids so that if the user isn't in the 'Participante' role anymore
            # they continue to appear in the project members list when editing
            member_id_ints = [int(m) for m in member_ids] if member_ids else []
            new_members = User.query.filter(User.id.in_(member_id_ints)).all() if member_id_ints else []
            project.members = new_members
            
            # Registrar cambios en auditoría
            new_client_ids = [c.id for c in project.clients]
            new_member_ids = [m.id for m in project.members]
            new_values = {
                'name': project.name,
                'description': project.description,
                'budget_hours': float(project.budget_hours) if project.budget_hours else None,
                'status': project.status,
                'client_ids': new_client_ids,
                'member_ids': new_member_ids
            }
            
            changes = {}
            for field, old_val in old_values.items():
                new_val = new_values[field]
                if old_val != new_val:
                    changes[field] = {'old': old_val, 'new': new_val}
            
            if changes:
                audit = AuditLog(
                    entity_type='Project',
                    entity_id=project.id,
                    action='UPDATE',
                    user_id=current_user.id,
                    changes=changes
                )
                db.session.add(audit)
            
            db.session.commit()
            flash(f"Proyecto '{project.name}' actualizado.", 'success')
            return redirect(url_for('main.project_detail', project_id=project.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
    
    # Ensure available_members includes existing project members even if their role changed
    participant_role = Role.query.filter_by(name='Participante').first()
    role_members = User.query.filter_by(role_id=participant_role.id).order_by(User.first_name).all() if participant_role else []
    # Combine and deduplicate
    member_map = {u.id: u for u in role_members}
    for m in project.members:
        member_map.setdefault(m.id, m)
    available_members = list(member_map.values())

    # IDs of currently assigned members (for checkbox checked state)
    project_member_ids = [m.id for m in project.members]

    return render_template('project_edit.html', project=project, available_clients=available_clients, available_members=available_members, project_member_ids=project_member_ids)


@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Validar permisos
    if not current_user.is_internal or (project.manager_id and project.manager_id != current_user.id):
        flash('No tienes permiso para eliminar este proyecto.', 'danger')
        return redirect(url_for('main.projects'))
    
    try:
        project_name = project.name
        project_id_backup = project.id
        
        # Registrar auditoría antes de eliminar
        audit = AuditLog(
            entity_type='Project',
            entity_id=project_id_backup,
            action='DELETE',
            user_id=current_user.id,
            changes={'name': project_name, 'status': project.status}
        )
        db.session.add(audit)
        
        db.session.delete(project)
        db.session.commit()
        flash(f"Proyecto '{project_name}' eliminado.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
    return redirect(url_for('main.projects'))


@main_bp.route('/api/kpi/velocity')
def kpi_velocity():
    """Provides data for the velocity chart on the dashboard."""
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    
    # Días en español
    dias_semana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    
    labels = []
    data = []
    
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        labels.append(dias_semana[i])
        
        daily_hours = db.session.query(func.sum(TimeEntry.hours)).filter(
            TimeEntry.date == day
        ).scalar() or 0
        
        data.append(float(daily_hours))
        
    return jsonify({'labels': labels, 'data': data})


@main_bp.route('/projects')
@login_required
def projects():
    """
    Visibilidad de proyectos según rol:
    - PMP/Admin: puede ver todos los proyectos
    - Participante: solo proyectos donde tiene tareas asignadas
    - Cliente: solo proyectos donde es cliente
    - Sin Rol: no puede ver nada
    """
    user_role = current_user.role.name if current_user.role else None
    
    # Usuario sin rol: mostrar mensaje y lista vacía
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return render_template('projects.html', projects=[], no_role=True)
    
    # PMP o Admin: puede ver todo
    if user_role in ['PMP', 'Admin']:
        projects = Project.query.order_by(Project.start_date.desc()).all()
    # Participante: solo proyectos donde tiene tareas asignadas
    elif user_role == 'Participante':
        # Participante puede ver proyectos donde tiene tareas asignadas
        # OR donde forma parte del equipo (`members`).
        project_ids = db.session.query(Task.project_id).filter(
            Task.assigned_to_id == current_user.id
        ).distinct().subquery()
        projects = Project.query.filter(
            (Project.id.in_(project_ids)) | (Project.members.contains(current_user))
        ).order_by(Project.start_date.desc()).all()
    # Cliente: solo proyectos donde es cliente
    elif user_role == 'Cliente' or not current_user.is_internal:
        projects = Project.query.filter(Project.clients.contains(current_user)).order_by(Project.start_date.desc()).all()
    else:
        # Cualquier otro rol: no ve nada por defecto
        projects = []
    
    # Calcular progreso y horas para cada proyecto en tiempo real
    for p in projects:
        total_hours = db.session.query(func.sum(TimeEntry.hours)).join(Task).filter(Task.project_id == p.id).scalar() or 0
        p.hours_spent = total_hours # Atributo temporal para la vista
        if p.budget_hours and p.budget_hours > 0:
            p.progress = min((total_hours / p.budget_hours) * 100, 100)
        else:
            p.progress = 0
            
    # Provide current time context for templates that compare dates
    return render_template('projects.html', projects=projects, no_role=False, now=datetime.now())


@main_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    user_role = current_user.role.name if current_user.role else None

    # Usuario sin rol: no puede ver nada
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return redirect(url_for('main.projects'))

    # Control de acceso según rol
    if user_role in ['PMP', 'Admin']:
        # PMP/Admin puede ver cualquier proyecto
        pass
    elif user_role == 'Participante':
        # Participante solo puede ver proyectos donde tiene tareas asignadas
        has_tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).first()
        if not has_tasks:
            flash('No tienes permiso para ver este proyecto.', 'danger')
            return redirect(url_for('main.projects'))
    elif user_role == 'Cliente' or not current_user.is_internal:
        # Cliente solo puede ver sus proyectos
        if current_user not in project.clients:
            flash('No tienes permiso para ver este proyecto.', 'danger')
            return redirect(url_for('main.projects'))
    else:
        flash('No tienes permiso para ver este proyecto.', 'danger')
        return redirect(url_for('main.projects'))

    # Filtrar tareas según rol
    if user_role in ['PMP', 'Admin']:
        # PMP/Admin ve todas las tareas del proyecto
        tasks = Task.query.filter_by(project_id=project_id).order_by(Task.status, Task.priority.desc()).all()
    elif user_role == 'Cliente' or not current_user.is_internal:
        # Cliente ve solo tareas visibles externamente o asignadas a él dentro del proyecto (solo lectura)
        tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.is_external_visible == True) | (Task.assigned_client_id == current_user.id)
        ).order_by(Task.status, Task.priority.desc()).all()
    else:
        # Participantes solo ven sus tareas asignadas
        tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).order_by(Task.status, Task.priority.desc()).all()

    # Sugeridos para asignación: usuarios internos
    assignees = User.query.filter_by(is_internal=True).order_by(User.first_name).all()
    # Candidate predecessors: all tasks in this project
    candidate_predecessors = Task.query.filter(Task.project_id == project_id).order_by(Task.title).all()
    
    # Build nested task tree respecting explicit parent->child relationships only
    def build_task_tree(task_list):
        tasks_by_id = {t.id: t for t in task_list}
        children_map = {t.id: [] for t in task_list}
        for t in task_list:
            if t.parent_task_id and t.parent_task_id in tasks_by_id:
                children_map[t.parent_task_id].append(t)

        # sort function: prefer explicit position, then status, priority, title
        status_order = {'BACKLOG': 0, 'IN_PROGRESS': 1, 'IN_REVIEW': 2, 'COMPLETED': 3}
        priority_order = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}

        def sort_key(x):
            if getattr(x, 'position', None) is not None:
                return (0, x.position)
            return (1, status_order.get(x.status, 99), -priority_order.get(x.priority, 0), x.title or '')

        def build_node(tid):
            t = tasks_by_id[tid]
            children = sorted(children_map[tid], key=sort_key)
            return {'task': t, 'children': [build_node(c.id) for c in children]}

        roots = [t for t in task_list if not t.parent_task_id or t.parent_task_id not in tasks_by_id]
        roots_sorted = sorted(roots, key=sort_key)
        forest = [build_node(r.id) for r in roots_sorted]
        return forest

    tasks_tree = build_task_tree(tasks)

    # Calcular métricas del proyecto
    metrics = calculate_project_metrics(project_id)

    # Render Monday-style board view
    return render_template('board.html', project=project, tasks=tasks, tasks_tree=tasks_tree, metrics=metrics, 
                          users=assignees, candidate_predecessors=candidate_predecessors, now=datetime.now(), project_id=project.id)


@main_bp.route('/project/<int:project_id>/tasks/reorder', methods=['POST'])
@login_required
def reorder_project_tasks(project_id):
    """Persist order of tasks in a project based on the provided array of task IDs.
    Body: { "ordered_task_ids": [id1, id2, ...] }
    This sets the `position` field for the tasks according to the list order.
    """
    if not current_user.is_internal:
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json() or {}
    ids = data.get('ordered_task_ids')
    if not isinstance(ids, list):
        return jsonify({'error': 'ordered_task_ids must be a list'}), 400

    # Validate tasks belong to this project
    tasks = Task.query.filter(Task.id.in_(ids), Task.project_id == project_id).all()
    ids_set = set(ids)
    if len(tasks) != len(ids):
        return jsonify({'error': 'Invalid task ids or mismatch with project'}), 400

    try:
        for idx, tid in enumerate(ids):
            t = next((x for x in tasks if x.id == tid), None)
            if t:
                t.position = idx
        db.session.commit()
        return jsonify({'status': 'ok'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@main_bp.route('/project/<int:project_id>/kanban')
@login_required
def project_kanban(project_id):
    project = Project.query.get_or_404(project_id)
    user_role = current_user.role.name if current_user.role else None

    # Usuario sin rol: no puede ver nada
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return redirect(url_for('main.projects'))

    # Control de acceso según rol
    if user_role in ['PMP', 'Admin']:
        pass
    elif user_role == 'Participante':
        has_tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).first()
        if not has_tasks:
            flash('No tienes permiso para ver este proyecto.', 'danger')
            return redirect(url_for('main.projects'))
    elif user_role == 'Cliente' or not current_user.is_internal:
        if current_user not in project.clients:
            flash('No tienes permiso para ver este proyecto.', 'danger')
            return redirect(url_for('main.projects'))
    else:
        flash('No tienes permiso para ver este proyecto.', 'danger')
        return redirect(url_for('main.projects'))

    # Filtrar tareas según rol
    if user_role in ['PMP', 'Admin']:
        tasks = Task.query.filter_by(project_id=project_id).all()
    elif user_role == 'Participante':
        tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).all()
    elif user_role == 'Cliente' or not current_user.is_internal:
        tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.is_external_visible == True) | (Task.assigned_client_id == current_user.id)
        ).all()
    else:
        tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).all()
    
    assignees = User.query.filter_by(is_internal=True).order_by(User.first_name).all()
    metrics = calculate_project_metrics(project_id)
    
    # Agrupar tareas por estado
    tasks_by_status = {
        'BACKLOG': [t for t in tasks if t.status == 'BACKLOG'],
        'IN_PROGRESS': [t for t in tasks if t.status == 'IN_PROGRESS'],
        'IN_REVIEW': [t for t in tasks if t.status == 'IN_REVIEW'],
        'COMPLETED': [t for t in tasks if t.status == 'COMPLETED']
    }
    
    return render_template('kanban.html', project=project, tasks_by_status=tasks_by_status, 
                          metrics=metrics, users=assignees, now=datetime.now())


# Crear tarea desde modal en project_detail
@main_bp.route('/task', methods=['POST'])
@login_required
def create_task():
    project_id = request.form.get('project_id')
    project = Project.query.get_or_404(project_id)

    # Solo usuarios internos pueden crear tareas
    if not current_user.is_internal:
        flash('No tienes permiso para crear tareas en este proyecto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    try:
        title = request.form.get('title', '').strip()
        if not title:
            flash('El título de la tarea es obligatorio.', 'danger')
            return redirect(url_for('main.project_detail', project_id=project_id))

        # Allow setting status from form (for Kanban view)
        status = request.form.get('status', 'BACKLOG')
        if status not in ['BACKLOG', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED']:
            status = 'BACKLOG'

        task = Task(
            project_id=project.id,
            title=title,
            description=request.form.get('description') or None,
            status=status,
            priority=request.form.get('priority') or 'MEDIUM',
            parent_task_id=int(request.form.get('parent_task_id')) if request.form.get('parent_task_id') and request.form.get('parent_task_id').strip() else None
        )

        # Assign to a client (customer) separately from internal assignee
        assigned_client_id = request.form.get('assigned_client_id')
        if assigned_client_id and assigned_client_id.strip():
            task.assigned_client_id = int(assigned_client_id)

        due_date_str = request.form.get('due_date')
        if due_date_str:
            task.due_date = datetime.fromisoformat(due_date_str)

        estimated_hours = request.form.get('estimated_hours')
        if estimated_hours and estimated_hours.strip():
            task.estimated_hours = float(estimated_hours)

        # Assign to a user if provided
        assigned_to_id = request.form.get('assigned_to_id')
        if assigned_to_id and assigned_to_id.strip():
            task.assigned_to_id = int(assigned_to_id)

        db.session.add(task)
        db.session.flush()  # Get task ID

        # Handle predecessors at creation time (if provided)
        predecessor_ids = [int(x) for x in request.form.getlist('predecessor_ids') if x and x.strip()]
        if predecessor_ids:
            task.validate_predecessor_ids(predecessor_ids)
            preds = Task.query.filter(Task.id.in_(predecessor_ids)).all()
            task.predecessors = preds
        
        # Registrar auditoría de creación
        audit = AuditLog(
            entity_type='Task',
            entity_id=task.id,
            action='CREATE',
            user_id=current_user.id,
            changes={'title': task.title, 'project_id': task.project_id, 'status': task.status}
        )
        db.session.add(audit)
        db.session.commit()

        # Handle file attachments
        files = request.files.getlist('attachments')
        attachment_count = 0
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                try:
                    stored_filename, task_folder = get_unique_filename(task.id, file.filename)
                    filepath = os.path.join(task_folder, stored_filename)
                    file.save(filepath)
                    
                    file_size = os.path.getsize(filepath)
                    mime_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
                    
                    attachment = TaskAttachment(
                        task_id=task.id,
                        filename=file.filename,
                        stored_filename=stored_filename,
                        file_size=file_size,
                        mime_type=mime_type,
                        uploaded_by_id=current_user.id
                    )
                    db.session.add(attachment)
                    attachment_count += 1
                except Exception as e:
                    current_app.logger.error(f"Error uploading attachment: {str(e)}")

        if attachment_count > 0:
            db.session.commit()
            flash(f"Tarea '{task.title}' creada con {attachment_count} archivo(s) adjunto(s).", 'success')
        else:
            flash(f"Tarea '{task.title}' creada.", 'success')

        # Notificar al usuario asignado (si es diferente al creador)
        if task.assigned_to_id and task.assigned_to_id != current_user.id:
            NotificationService.notify_task_assigned(
                task=task,
                assigned_by_user=current_user,
                send_email=True
            )

    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear tarea: {str(e)}', 'danger')

    return redirect(url_for('main.project_detail', project_id=project.id))


# --- Admin: User and Role Management (PMP only) ---

def _ensure_pmp():
    # DEBUG: print current_user details (temporary)
    # Use session-stored user id to guarantee we check the current session state
    from flask import session
    uid = session.get('_user_id') or current_user.get_id()
    if not uid:
        abort(403)
    user = User.query.get(int(uid))
    if not user or not user.is_internal:
        abort(403)
    if not user.role_id:
        abort(403)
    role = Role.query.get(user.role_id)
    if not role or role.name != 'PMP':
        abort(403)
    return True


# ========== ADMIN DASHBOARD ==========

@main_bp.route('/admin')
@login_required
def admin_dashboard():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    # Estadísticas generales
    stats = {
        'total_users': User.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'total_projects': Project.query.count(),
        'total_hours': db.session.query(func.sum(TimeEntry.hours)).scalar() or 0
    }
    
    return render_template('admin/index.html', stats=stats)


@main_bp.route('/admin/users')
@login_required
def admin_users():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    users = User.query.order_by(User.email).all()
    roles = Role.query.order_by(Role.name).all()
    return render_template('admin/users.html', users=users, roles=roles)


@main_bp.route('/admin/user/new', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    roles = Role.query.order_by(Role.name).all()

    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            if not email:
                flash('El email es obligatorio.', 'danger')
                return render_template('admin/user_edit.html', user=None, roles=roles)

            if User.query.filter_by(email=email).first():
                flash('Ya existe un usuario con ese email.', 'danger')
                return render_template('admin/user_edit.html', user=None, roles=roles)

            from werkzeug.security import generate_password_hash
            password = request.form.get('password', '').strip()
            if not password:
                password = 'changeme123'  # Default password

            user = User(
                email=email,
                first_name=request.form.get('first_name', '').strip() or None,
                last_name=request.form.get('last_name', '').strip() or None,
                password_hash=generate_password_hash(password),
                is_internal=request.form.get('is_internal') == 'on',
                is_active=request.form.get('is_active') == 'on'
            )
            role_id = request.form.get('role_id')
            if role_id:
                user.role_id = int(role_id)

            db.session.add(user)
            db.session.flush()  # Get user ID
            
            # Registrar auditoría
            audit = AuditLog(
                entity_type='User',
                entity_id=user.id,
                action='CREATE',
                user_id=current_user.id,
                changes={'email': user.email, 'is_internal': user.is_internal, 'role_id': user.role_id}
            )
            db.session.add(audit)
            db.session.commit()
            flash(f'Usuario {email} creado exitosamente.', 'success')
            return redirect(url_for('main.admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear usuario: {str(e)}', 'danger')

    return render_template('admin/user_edit.html', user=None, roles=roles)


@main_bp.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    user = User.query.get_or_404(user_id)
    roles = Role.query.order_by(Role.name).all()

    if request.method == 'POST':
        try:
            # Guardar valores anteriores para auditoría
            old_values = {
                'role_id': user.role_id,
                'is_internal': user.is_internal,
                'is_active': user.is_active
            }
            
            role_id = request.form.get('role_id')
            if role_id:
                user.role_id = int(role_id)
            user.is_internal = True if request.form.get('is_internal') == 'on' else False
            user.is_active = True if request.form.get('is_active') == 'on' else False
            
            # Detectar cambios para auditoría
            new_values = {
                'role_id': user.role_id,
                'is_internal': user.is_internal,
                'is_active': user.is_active
            }
            changes = {}
            for field, old_val in old_values.items():
                if old_val != new_values[field]:
                    changes[field] = {'old': old_val, 'new': new_values[field]}
            
            # Cambiar contraseña solo para usuarios locales (sin azure_oid)
            new_password = request.form.get('password', '').strip()
            if new_password and not user.azure_oid:
                user.set_password(new_password)
                changes['password'] = {'old': '***', 'new': '***'}
            
            if changes:
                audit = AuditLog(
                    entity_type='User',
                    entity_id=user.id,
                    action='UPDATE',
                    user_id=current_user.id,
                    changes=changes
                )
                db.session.add(audit)
            
            db.session.commit()
            flash('Usuario actualizado.', 'success')
            return redirect(url_for('main.admin_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar usuario: {str(e)}', 'danger')

    return render_template('admin/user_edit.html', user=user, roles=roles)


@main_bp.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    user = User.query.get_or_404(user_id)
    
    # No permitir eliminar al usuario actual
    if user.id == current_user.id:
        flash('No puedes eliminar tu propio usuario.', 'danger')
        return redirect(url_for('main.admin_users'))
    
    try:
        email = user.email
        user_id_backup = user.id
        
        # Registrar auditoría antes de eliminar
        audit = AuditLog(
            entity_type='User',
            entity_id=user_id_backup,
            action='DELETE',
            user_id=current_user.id,
            changes={'email': email, 'is_internal': user.is_internal}
        )
        db.session.add(audit)
        
        db.session.delete(user)
        db.session.commit()
        flash(f'Usuario {email} eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar usuario: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_users'))


@main_bp.route('/admin/roles', methods=['GET', 'POST'])
@login_required
def admin_roles():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            if Role.query.filter_by(name=name).first():
                flash('El rol ya existe.', 'warning')
            else:
                role = Role(name=name)
                db.session.add(role)
                db.session.flush()
                
                # Registrar auditoría
                audit = AuditLog(
                    entity_type='Role',
                    entity_id=role.id,
                    action='CREATE',
                    user_id=current_user.id,
                    changes={'name': name}
                )
                db.session.add(audit)
                db.session.commit()
                flash('Rol creado.', 'success')
        return redirect(url_for('main.admin_roles'))
    roles = Role.query.order_by(Role.name).all()
    return render_template('admin/roles.html', roles=roles)


@main_bp.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
@login_required
def admin_delete_role(role_id):
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    role = Role.query.get_or_404(role_id)
    
    # No permitir eliminar roles en uso
    if User.query.filter_by(role_id=role_id).first():
        flash('No se puede eliminar un rol que está asignado a usuarios.', 'danger')
        return redirect(url_for('main.admin_roles'))
    
    try:
        name = role.name
        role_id_backup = role.id
        
        # Registrar auditoría antes de eliminar
        audit = AuditLog(
            entity_type='Role',
            entity_id=role_id_backup,
            action='DELETE',
            user_id=current_user.id,
            changes={'name': name}
        )
        db.session.add(audit)
        
        db.session.delete(role)
        db.session.commit()
        flash(f'Rol "{name}" eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
    return redirect(url_for('main.admin_roles'))


# ========== ADMIN: TARIFAS ==========

@main_bp.route('/admin/rates', methods=['GET', 'POST'])
@login_required
def admin_rates():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            try:
                rate = HourlyRate(
                    name=request.form.get('name'),
                    rate=float(request.form.get('rate', 0)),
                    currency=request.form.get('currency', 'USD'),
                    description=request.form.get('description'),
                    is_default=request.form.get('is_default') == 'on'
                )
                
                # Si es default, quitar default de los demás
                if rate.is_default:
                    HourlyRate.query.update({HourlyRate.is_default: False})
                
                db.session.add(rate)
                db.session.flush()
                
                # Auditoría
                audit = AuditLog(
                    entity_type='HourlyRate',
                    entity_id=rate.id,
                    action='CREATE',
                    user_id=current_user.id,
                    changes={'name': rate.name, 'rate': rate.rate, 'currency': rate.currency}
                )
                db.session.add(audit)
                db.session.commit()
                flash('Tarifa creada exitosamente.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error: {str(e)}', 'danger')
        
        elif action == 'update':
            rate_id = request.form.get('rate_id')
            rate = HourlyRate.query.get(rate_id)
            if rate:
                old_values = {'name': rate.name, 'rate': float(rate.rate), 'currency': rate.currency, 'is_active': rate.is_active}
                
                rate.name = request.form.get('name')
                rate.rate = float(request.form.get('rate', 0))
                rate.currency = request.form.get('currency', 'USD')
                rate.description = request.form.get('description')
                rate.is_active = request.form.get('is_active') == 'on'
                
                if request.form.get('is_default') == 'on':
                    HourlyRate.query.update({HourlyRate.is_default: False})
                    rate.is_default = True
                
                new_values = {'name': rate.name, 'rate': float(rate.rate), 'currency': rate.currency, 'is_active': rate.is_active}
                changes = {k: {'old': old_values[k], 'new': new_values[k]} for k in old_values if old_values[k] != new_values[k]}
                
                if changes:
                    audit = AuditLog(
                        entity_type='HourlyRate',
                        entity_id=rate.id,
                        action='UPDATE',
                        user_id=current_user.id,
                        changes=changes
                    )
                    db.session.add(audit)
                
                db.session.commit()
                flash('Tarifa actualizada.', 'success')
        
        elif action == 'delete':
            rate_id = request.form.get('rate_id')
            rate = HourlyRate.query.get(rate_id)
            if rate:
                audit = AuditLog(
                    entity_type='HourlyRate',
                    entity_id=rate.id,
                    action='DELETE',
                    user_id=current_user.id,
                    changes={'name': rate.name, 'rate': float(rate.rate)}
                )
                db.session.add(audit)
                db.session.delete(rate)
                db.session.commit()
                flash('Tarifa eliminada.', 'success')
        
        return redirect(url_for('main.admin_rates'))
    
    rates = HourlyRate.query.order_by(HourlyRate.name).all()
    currencies = ['USD', 'PYG', 'EUR']
    currency_names = {'USD': 'Dólares', 'PYG': 'Guaraníes (PYG)', 'EUR': 'Euro'}
    return render_template('admin/rates.html', rates=rates, currencies=currencies, currency_names=currency_names)


# ========== ADMIN: BRANDING ==========

@main_bp.route('/admin/branding', methods=['GET', 'POST'])
@login_required
def admin_branding():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Guardar configuraciones de branding
            SystemSettings.set('app_name', request.form.get('app_name', 'BridgeWork'), 'branding', 'Nombre de la aplicación', user_id=current_user.id)
            SystemSettings.set('app_subtitle', request.form.get('app_subtitle', 'Project Manager'), 'branding', 'Subtítulo', user_id=current_user.id)
            SystemSettings.set('primary_color', request.form.get('primary_color', '#0d6efd'), 'branding', 'Color primario', user_id=current_user.id)
            SystemSettings.set('secondary_color', request.form.get('secondary_color', '#6c757d'), 'branding', 'Color secundario', user_id=current_user.id)
            SystemSettings.set('sidebar_color', request.form.get('sidebar_color', '#1a1d29'), 'branding', 'Color del sidebar', user_id=current_user.id)
            
            # Logo upload
            if 'logo' in request.files:
                file = request.files['logo']
                if file and file.filename:
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(file.filename)
                    logo_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'branding')
                    os.makedirs(logo_path, exist_ok=True)
                    filepath = os.path.join(logo_path, f'logo_{filename}')
                    file.save(filepath)
                    SystemSettings.set('logo_path', f'/uploads/branding/logo_{filename}', 'branding', 'Ruta del logo', user_id=current_user.id)
            
            # Favicon upload
            if 'favicon' in request.files:
                file = request.files['favicon']
                if file and file.filename:
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(file.filename)
                    logo_path = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'branding')
                    os.makedirs(logo_path, exist_ok=True)
                    filepath = os.path.join(logo_path, f'favicon_{filename}')
                    file.save(filepath)
                    SystemSettings.set('favicon_path', f'/uploads/branding/favicon_{filename}', 'branding', 'Ruta del favicon', user_id=current_user.id)
            
            # Auditoría de cambios de branding
            audit = AuditLog(
                entity_type='SystemSettings',
                entity_id=0,
                action='UPDATE',
                user_id=current_user.id,
                changes={'category': 'branding', 'app_name': request.form.get('app_name')}
            )
            db.session.add(audit)
            
            db.session.commit()
            flash('Configuración de apariencia guardada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
        
        return redirect(url_for('main.admin_branding'))
    
    # Obtener configuraciones actuales
    settings = {
        'app_name': SystemSettings.get('app_name', 'BridgeWork'),
        'app_subtitle': SystemSettings.get('app_subtitle', 'Project Manager'),
        'primary_color': SystemSettings.get('primary_color', '#0d6efd'),
        'secondary_color': SystemSettings.get('secondary_color', '#6c757d'),
        'sidebar_color': SystemSettings.get('sidebar_color', '#1a1d29'),
        'logo_path': SystemSettings.get('logo_path'),
        'favicon_path': SystemSettings.get('favicon_path'),
    }
    
    return render_template('admin/branding.html', settings=settings)


# ========== ADMIN: CONFIGURACIÓN GENERAL ==========

@main_bp.route('/admin/general', methods=['GET', 'POST'])
@login_required
def admin_general():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            SystemSettings.set('default_currency', request.form.get('default_currency', 'USD'), 'general', 'Moneda predeterminada', user_id=current_user.id)
            SystemSettings.set('timezone', request.form.get('timezone', 'America/Mexico_City'), 'general', 'Zona horaria', user_id=current_user.id)
            SystemSettings.set('date_format', request.form.get('date_format', 'DD/MM/YYYY'), 'general', 'Formato de fecha', user_id=current_user.id)
            SystemSettings.set('time_format', request.form.get('time_format', '24h'), 'general', 'Formato de hora', user_id=current_user.id)
            SystemSettings.set('language', request.form.get('language', 'es'), 'general', 'Idioma', user_id=current_user.id)
            SystemSettings.set('week_start', request.form.get('week_start', 'monday'), 'general', 'Inicio de semana', user_id=current_user.id)
            SystemSettings.set('default_task_status', request.form.get('default_task_status', 'BACKLOG'), 'general', 'Estado inicial de tareas', user_id=current_user.id)
            SystemSettings.set('require_task_approval', request.form.get('require_task_approval', 'true'), 'general', 'Requerir aprobación de tareas', 'boolean', user_id=current_user.id)
            
            # Auditoría
            audit = AuditLog(
                entity_type='SystemSettings',
                entity_id=0,
                action='UPDATE',
                user_id=current_user.id,
                changes={'category': 'general', 'language': request.form.get('language'), 'timezone': request.form.get('timezone')}
            )
            db.session.add(audit)
            
            db.session.commit()
            flash('Configuración general guardada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
        
        return redirect(url_for('main.admin_general'))
    
    settings = {
        'default_currency': SystemSettings.get('default_currency', 'USD'),
        'timezone': SystemSettings.get('timezone', 'America/Mexico_City'),
        'date_format': SystemSettings.get('date_format', 'DD/MM/YYYY'),
        'time_format': SystemSettings.get('time_format', '24h'),
        'language': SystemSettings.get('language', 'es'),
        'week_start': SystemSettings.get('week_start', 'monday'),
        'default_task_status': SystemSettings.get('default_task_status', 'BACKLOG'),
        'require_task_approval': SystemSettings.get('require_task_approval', True),
    }
    
    currencies = ['USD', 'PYG', 'EUR']
    currency_names = {'USD': 'Dólares', 'PYG': 'Guaraníes (PYG)', 'EUR': 'Euro'}
    timezones = [
        'America/Asuncion', 'America/Mexico_City', 'America/New_York', 'America/Los_Angeles', 
        'America/Chicago', 'America/Bogota', 'America/Lima', 'America/Santiago', 
        'America/Buenos_Aires', 'America/Sao_Paulo', 'America/Montevideo',
        'Europe/Madrid', 'Europe/London', 'UTC'
    ]
    
    return render_template('admin/general.html', settings=settings, currencies=currencies, timezones=timezones, currency_names=currency_names)


# ========== ADMIN: CONTENIDO Y TEXTOS ==========

@main_bp.route('/admin/content', methods=['GET', 'POST'])
@login_required
def admin_content():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            SystemSettings.set('footer_text', request.form.get('footer_text', ''), 'content', 'Texto del footer', user_id=current_user.id)
            SystemSettings.set('copyright_text', request.form.get('copyright_text', '© 2025 BridgeWork'), 'content', 'Texto de copyright', user_id=current_user.id)
            SystemSettings.set('support_email', request.form.get('support_email', ''), 'content', 'Email de soporte', user_id=current_user.id)
            SystemSettings.set('support_phone', request.form.get('support_phone', ''), 'content', 'Teléfono de soporte', user_id=current_user.id)
            SystemSettings.set('terms_url', request.form.get('terms_url', ''), 'content', 'URL de términos', user_id=current_user.id)
            SystemSettings.set('privacy_url', request.form.get('privacy_url', ''), 'content', 'URL de privacidad', user_id=current_user.id)
            SystemSettings.set('welcome_message', request.form.get('welcome_message', ''), 'content', 'Mensaje de bienvenida', user_id=current_user.id)
            
            # Auditoría
            audit = AuditLog(
                entity_type='SystemSettings',
                entity_id=0,
                action='UPDATE',
                user_id=current_user.id,
                changes={'category': 'content'}
            )
            db.session.add(audit)
            
            db.session.commit()
            flash('Contenido actualizado.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
        
        return redirect(url_for('main.admin_content'))
    
    settings = {
        'footer_text': SystemSettings.get('footer_text', ''),
        'copyright_text': SystemSettings.get('copyright_text', '© 2025 BridgeWork'),
        'support_email': SystemSettings.get('support_email', ''),
        'support_phone': SystemSettings.get('support_phone', ''),
        'terms_url': SystemSettings.get('terms_url', ''),
        'privacy_url': SystemSettings.get('privacy_url', ''),
        'welcome_message': SystemSettings.get('welcome_message', ''),
    }
    
    return render_template('admin/content.html', settings=settings)


# ========== ADMIN: NOTIFICACIONES ==========

@main_bp.route('/admin/notifications', methods=['GET', 'POST'])
@login_required
def admin_notifications():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            SystemSettings.set('email_provider', request.form.get('email_provider', 'stub'), 'notifications', 'Proveedor de email', user_id=current_user.id)
            SystemSettings.set('sendgrid_api_key', request.form.get('sendgrid_api_key', ''), 'notifications', 'API Key de SendGrid', user_id=current_user.id)
            SystemSettings.set('email_from', request.form.get('email_from', ''), 'notifications', 'Email remitente', user_id=current_user.id)
            SystemSettings.set('email_from_name', request.form.get('email_from_name', 'BridgeWork'), 'notifications', 'Nombre remitente', user_id=current_user.id)
            SystemSettings.set('notify_task_assigned', request.form.get('notify_task_assigned', 'true'), 'notifications', 'Notificar asignación', 'boolean', user_id=current_user.id)
            SystemSettings.set('notify_task_completed', request.form.get('notify_task_completed', 'true'), 'notifications', 'Notificar completado', 'boolean', user_id=current_user.id)
            SystemSettings.set('notify_task_approved', request.form.get('notify_task_approved', 'true'), 'notifications', 'Notificar aprobación', 'boolean', user_id=current_user.id)
            
            # Auditoría
            audit = AuditLog(
                entity_type='SystemSettings',
                entity_id=0,
                action='UPDATE',
                user_id=current_user.id,
                changes={'category': 'notifications', 'email_provider': request.form.get('email_provider')}
            )
            db.session.add(audit)
            
            db.session.commit()
            flash('Configuración de notificaciones guardada.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
        
        return redirect(url_for('main.admin_notifications'))
    
    settings = {
        'email_provider': SystemSettings.get('email_provider', 'stub'),
        'sendgrid_api_key': SystemSettings.get('sendgrid_api_key', ''),
        'email_from': SystemSettings.get('email_from', ''),
        'email_from_name': SystemSettings.get('email_from_name', 'BridgeWork'),
        'notify_task_assigned': SystemSettings.get('notify_task_assigned', True),
        'notify_task_completed': SystemSettings.get('notify_task_completed', True),
        'notify_task_approved': SystemSettings.get('notify_task_approved', True),
    }
    
    return render_template('admin/notifications_config.html', settings=settings)


# ========== ADMIN: AUDITORÍA ==========

@main_bp.route('/admin/audit')
@login_required
def admin_audit():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/audit.html', logs=logs)


# ========== ADMIN: MANTENIMIENTO ==========

@main_bp.route('/admin/maintenance', methods=['GET', 'POST'])
@login_required
def admin_maintenance():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'clear_old_notifications':
            # Eliminar notificaciones leídas de más de 30 días
            cutoff = datetime.now() - timedelta(days=30)
            deleted = SystemNotification.query.filter(
                SystemNotification.is_read == True,
                SystemNotification.created_at < cutoff
            ).delete()
            db.session.commit()
            flash(f'{deleted} notificaciones antiguas eliminadas.', 'success')
        
        elif action == 'clear_old_audit':
            # Eliminar logs de auditoría de más de 90 días
            cutoff = datetime.now() - timedelta(days=90)
            deleted = AuditLog.query.filter(AuditLog.created_at < cutoff).delete()
            db.session.commit()
            flash(f'{deleted} registros de auditoría eliminados.', 'success')
        
        return redirect(url_for('main.admin_maintenance'))
    
    # Estadísticas del sistema
    stats = {
        'db_notifications': SystemNotification.query.count(),
        'db_audit_logs': AuditLog.query.count(),
        'db_time_entries': TimeEntry.query.count(),
        'db_tasks': Task.query.count(),
        'db_projects': Project.query.count(),
        'db_users': User.query.count(),
    }
    
    return render_template('admin/maintenance.html', stats=stats)


@main_bp.route('/projects/new', methods=['POST'])
@login_required
def create_project():
    name = request.form.get('name')
    description = request.form.get('description')
    budget_hours = request.form.get('budget_hours')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    project_type = request.form.get('project_type', 'APP_DEVELOPMENT')
    client_ids = request.form.getlist('client_ids')
    
    if not name:
        flash('El nombre del proyecto es un campo obligatorio.', 'danger')
        return redirect(url_for('main.projects'))
    
    try:
        new_project = Project(
            name=name,
            description=description,
            budget_hours=float(budget_hours) if budget_hours and budget_hours.strip() else None,
            status='ACTIVE',
            project_type=project_type,
            manager_id=current_user.id if current_user.is_internal else None,
            start_date=datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else datetime.now(timezone.utc).date(),
            end_date=datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        )
        db.session.add(new_project)
        db.session.flush()  # Get the project ID
        
        # Associate clients
        if client_ids:
            clients = User.query.filter(User.id.in_(client_ids)).all()
            new_project.clients = clients
        
        # Registrar auditoría de creación
        audit = AuditLog(
            entity_type='Project',
            entity_id=new_project.id,
            action='CREATE',
            user_id=current_user.id,
            changes={'name': name, 'status': 'ACTIVE', 'budget_hours': float(new_project.budget_hours) if new_project.budget_hours else None}
        )
        db.session.add(audit)
        
        db.session.commit()
        flash(f"Proyecto '{name}' creado con éxito.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear proyecto: {str(e)}', 'danger')
    
    return redirect(url_for('main.projects'))

@main_bp.route('/tasks')
@login_required
def tasks():
    """
    Visibilidad de tareas según rol:
    - PMP/Admin: puede ver todas las tareas
    - Participante: solo tareas asignadas a él
    - Cliente: solo tareas de sus proyectos que son visibles externamente
    - Sin Rol: no puede ver nada
    """
    user_role = current_user.role.name if current_user.role else None
    
    # Usuario sin rol: mostrar mensaje y lista vacía
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return render_template('tasks.html', tasks=[], no_role=True, now=datetime.now(), status_filter='', priority_filter='')
    
    # Filtros
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    
    query = Task.query
    
    # Aplicar filtro según rol
    if user_role in ['PMP', 'Admin']:
        # PMP/Admin ve todas las tareas
        pass
    elif user_role == 'Participante':
        # Participante solo ve sus tareas asignadas
        query = query.filter(Task.assigned_to_id == current_user.id)
    elif user_role == 'Cliente' or not current_user.is_internal:
        # Cliente: mostrar SOLO las tareas de sus proyectos que sean visibles externamente o estén asignadas al cliente
        client_project_ids = db.session.query(Project.id).filter(
            Project.clients.contains(current_user)
        ).subquery()
        query = query.filter(
            Task.project_id.in_(client_project_ids)
        ).filter(
            (Task.is_external_visible == True) | (Task.assigned_client_id == current_user.id)
        )
    else:
        # Cualquier otro rol: no ve nada
        query = query.filter(Task.id == -1)  # Query que no devuelve nada
    
    if status_filter:
        query = query.filter(Task.status == status_filter)
    
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)
    
    tasks = query.order_by(Task.due_date).all()
    
    # Calcular horas por tarea
    for t in tasks:
        t.hours_spent = db.session.query(func.sum(TimeEntry.hours)).filter_by(task_id=t.id).scalar() or 0
    
    return render_template('tasks.html', 
        tasks=tasks, 
        now=datetime.now(),
        status_filter=status_filter,
        priority_filter=priority_filter,
        no_role=False
    )

@main_bp.route('/time')
@main_bp.route('/time-entries')
@login_required
def time_entries():
    # Filters and pagination
    user_role = current_user.role.name if current_user.role else None
    page = int(request.args.get('page', 1))
    per_page = 25

    # Parse filters
    start_date_s = request.args.get('start_date')
    end_date_s = request.args.get('end_date')
    filter_user_id = request.args.get('user_id') if (user_role in ['PMP', 'Admin']) else None

    query = TimeEntry.query

    # Apply role-based visibility
    if user_role in ['PMP', 'Admin']:
        pass  # all entries visible, filters below will narrow if provided
    else:
        query = query.filter(TimeEntry.user_id == current_user.id)

    # Apply date filters
    if start_date_s:
        try:
            start_date = datetime.strptime(start_date_s, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date >= start_date)
        except Exception:
            pass
    if end_date_s:
        try:
            end_date = datetime.strptime(end_date_s, '%Y-%m-%d').date()
            query = query.filter(TimeEntry.date <= end_date)
        except Exception:
            pass

    # Apply user filter (PMP/Admin only)
    if filter_user_id:
        try:
            uid = int(filter_user_id)
            query = query.filter(TimeEntry.user_id == uid)
        except Exception:
            pass

    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page

    entries = query.order_by(TimeEntry.date.desc()).offset((page - 1) * per_page).limit(per_page).all()

    # Total hours visible in this filtered view
    total_hours_week = query.with_entities(func.sum(TimeEntry.hours)).filter(TimeEntry.date >= (datetime.now().date() - timedelta(days=7))).scalar() or 0

    # If PMP/Admin, expose list of users for filter
    users = User.query.order_by(User.first_name).all() if user_role in ['PMP', 'Admin'] else []

    # Build pagination urls (preserve filters)
    params = request.args.to_dict()
    def make_url_for(p):
        params_copy = params.copy()
        params_copy['page'] = p
        return url_for('main.time_entries', **params_copy)

    page_urls = [{'num': i, 'url': make_url_for(i), 'active': (i == page)} for i in range(1, total_pages + 1)] if total_pages > 0 else []
    prev_url = make_url_for(page - 1) if page > 1 else None
    next_url = make_url_for(page + 1) if page < total_pages else None

    return render_template('time_entries.html', time_entries=entries, total_hours_week=total_hours_week, page=page, total_pages=total_pages, users=users, total_count=total_count, page_urls=page_urls, prev_url=prev_url, next_url=next_url)

@main_bp.route('/team')
@login_required
def team():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    # Obtener usuarios internos
    internal_users = User.query.filter_by(is_internal=True).all()
    
    # Estadísticas de tareas por estado para cada usuario interno
    for u in internal_users:
        # Contar tareas por estado
        task_stats = db.session.query(
            Task.status, func.count(Task.id)
        ).filter(Task.assigned_to_id == u.id).group_by(Task.status).all()
        
        u.task_by_status = {status: count for status, count in task_stats}
        u.total_tasks = sum(u.task_by_status.values())
        
        # Horas este mes
        u.hours_this_month = db.session.query(func.sum(TimeEntry.hours)).join(Task).filter(
            TimeEntry.user_id == u.id,
            TimeEntry.date >= (datetime.utcnow().date().replace(day=1))
        ).scalar() or 0
    
    return render_template('team.html', internal_users=internal_users)


@main_bp.route('/clients')
@login_required
def clients():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    # Obtener clientes
    clients = User.query.filter_by(is_internal=False).all()
    
    # Estadísticas de proyectos por estado para cada cliente
    for c in clients:
        # Proyectos asociados al cliente a través de la tabla project_clients
        project_stats = db.session.query(
            Project.status, func.count(Project.id)
        ).join(project_clients).filter(
            project_clients.c.user_id == c.id,
        ).group_by(Project.status).all()
        
        c.project_by_status = {status: count for status, count in project_stats}
        c.total_projects = sum(c.project_by_status.values())
        
        # Tareas pendientes de aprobación
        c.pending_approvals = db.session.query(func.count(Task.id)).join(Project).join(
            project_clients
        ).filter(
            project_clients.c.user_id == c.id,
            Task.requires_approval == True,
            Task.approval_status == 'pending'
        ).scalar() or 0
    
    return render_template('clients.html', clients=clients)


@main_bp.route('/teams')
@login_required
def teams_alias():
    # Alias por compatibilidad: /teams -> /team
    return redirect(url_for('main.team'))

@main_bp.route('/reports')
@login_required
def reports():
    if not _ensure_pmp():
        return redirect(url_for('main.index'))
    # Reportes generales
    total_projects = db.session.query(func.count(Project.id)).scalar()
    total_tasks = db.session.query(func.count(Task.id)).scalar()
    completed_tasks = db.session.query(func.count(Task.id)).filter(Task.status == 'COMPLETED').scalar()
    
    # Budget overview
    projects_budget = db.session.query(
        func.sum(Project.budget_hours),
        func.sum(func.coalesce(
            db.session.query(func.sum(TimeEntry.hours))
            .join(Task)
            .filter(Task.project_id == Project.id)
            .correlate(Project)
            .as_scalar(), 0
        ))
    ).all()
    
    total_budget = projects_budget[0][0] or 0
    total_hours_spent = projects_budget[0][1] or 0
    budget_usage_percent = (total_hours_spent / total_budget * 100) if total_budget > 0 else 0

    return render_template('reports.html', 
        total_projects=total_projects, 
        total_tasks=total_tasks, 
        completed_tasks=completed_tasks,
        total_budget=total_budget,
        total_hours_spent=total_hours_spent,
        budget_usage_percent=budget_usage_percent
    )

@main_bp.route('/notifications')
@login_required
def notifications():
    """Vista de notificaciones del usuario"""
    user_notifications = SystemNotification.query.filter_by(user_id=current_user.id).order_by(
        SystemNotification.is_read,
        SystemNotification.created_at.desc()
    ).all()
    return render_template('notifications.html', notifications=user_notifications)

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            if not current_user.azure_oid:
                current_user.first_name = request.form.get('first_name', '').strip() or current_user.first_name
                current_user.last_name = request.form.get('last_name', '').strip() or current_user.last_name
            db.session.commit()
            flash('Perfil actualizado correctamente.', 'success')
        elif action == 'change_password':
            if current_user.azure_oid:
                flash('Los usuarios de Azure AD deben cambiar su contraseña desde el portal de Microsoft.', 'warning')
                return redirect(url_for('main.profile'))
            from werkzeug.security import check_password_hash, generate_password_hash
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            if not current_user.password_hash or not check_password_hash(current_user.password_hash, current_password):
                flash('Contraseña actual incorrecta.', 'danger')
                return redirect(url_for('main.profile'))
            if new_password != confirm_password:
                flash('Las contraseñas no coinciden.', 'danger')
                return redirect(url_for('main.profile'))
            if len(new_password) < 8:
                flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
                return redirect(url_for('main.profile'))
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Contraseña actualizada correctamente.', 'success')
        return redirect(url_for('main.profile'))

    stats = {
        'tasks_assigned': Task.query.filter_by(assigned_to_id=current_user.id).count(),
        'tasks_completed': Task.query.filter_by(assigned_to_id=current_user.id, status='COMPLETED').count(),
        'projects_managed': Project.query.filter_by(manager_id=current_user.id).count() if current_user.is_internal else 0,
        'total_hours': db.session.query(func.sum(TimeEntry.hours)).filter_by(user_id=current_user.id).scalar() or 0
    }

    recent_tasks = Task.query.filter_by(assigned_to_id=current_user.id).order_by(Task.due_date.desc()).limit(5).all()
    recent_time_entries = TimeEntry.query.filter_by(user_id=current_user.id).order_by(TimeEntry.date.desc()).limit(5).all()

    return render_template('profile.html', stats=stats, recent_tasks=recent_tasks, recent_time_entries=recent_time_entries)

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'profile':
            # actualizar email/perfil
            current_user.email = request.form.get('email') or current_user.email
            db.session.commit()
            flash('Perfil actualizado.', 'success')
        elif action == 'password':
            from werkzeug.security import check_password_hash, generate_password_hash
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not current_user.password_hash or not check_password_hash(current_user.password_hash, current_password):
                flash('Contraseña actual incorrecta.', 'danger')
                return redirect(url_for('main.settings'))
            if new_password != confirm_password:
                flash('Las contraseñas no coinciden.', 'danger')
                return redirect(url_for('main.settings'))
            if len(new_password) < 8:
                flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
                return redirect(url_for('main.settings'))
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Contraseña actualizada.', 'success')
        return redirect(url_for('main.settings'))

    return render_template('settings.html')

@main_bp.route('/notifications/recent')
@login_required
def recent_notifications():
    """Obtener notificaciones recientes como JSON (para dropdown)"""
    notifications = NotificationService.get_recent(current_user.id, limit=10)
    unread_count = NotificationService.get_unread_count(current_user.id)

    return jsonify({



        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'type': n.notification_type,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat() if n.created_at else None,
            'related_entity_type': n.related_entity_type,
            'related_entity_id': n.related_entity_id
        } for n in notifications]
    })

@main_bp.route('/notifications/mark_all_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Marcar todas las notificaciones del usuario como leídas (llamada desde el navbar)."""
    try:
        unread = SystemNotification.query.filter_by(user_id=current_user.id, is_read=False).all()
        for n in unread:
            n.is_read = True
        db.session.commit()
        return jsonify({'status': 'ok', 'updated': len(unread)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
