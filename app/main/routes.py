from datetime import datetime, timedelta
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
from ..auth.decorators import internal_required


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
            send_email=SystemSettings.get('notify_task_approved', True)
        )
    else:
        # Notificar al creador del proyecto aunque no requiera aprobación
        NotificationService.notify_task_completed(
            task=task,
            completed_by_user=completed_by_user,
            notify_client=False,
            send_email=SystemSettings.get('notify_task_completed', True)
        )


@main_bp.route('/')
@login_required
def index():
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    
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
        # Participante ve solo proyectos donde tiene tareas asignadas (incluyendo multi-asignados)
        user_project_ids = db.session.query(Task.project_id).filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).distinct().subquery()
        
        active_projects_count = db.session.query(func.count(Project.id)).filter(
            Project.status == 'ACTIVE',
            Project.id.in_(user_project_ids)
        ).scalar()
        tasks_completed_count = db.session.query(func.count(Task.id)).filter(
            Task.status == 'COMPLETED',
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).scalar()
        recent_projects = Project.query.filter(Project.id.in_(user_project_ids)).order_by(Project.start_date.desc()).limit(5).all()
        recent_activity = Task.query.filter(
            Task.status == 'COMPLETED',
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
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
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
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
                'manager_id': project.manager_id,
                'client_ids': old_client_ids,
                'member_ids': old_member_ids
            }
            
            # Aplicar cambios
            project.name = request.form.get('name') or project.name
            project.description = request.form.get('description')
            project.budget_hours = float(request.form.get('budget_hours')) if request.form.get('budget_hours') and request.form.get('budget_hours').strip() else project.budget_hours
            project.status = request.form.get('status', project.status)
            
            # Actualizar responsable del proyecto
            manager_id = request.form.get('manager_id')
            project.manager_id = int(manager_id) if manager_id and manager_id.strip() else None
            
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
                'manager_id': project.manager_id,
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
    
    # Obtener usuarios internos para selector de responsable
    available_managers = User.query.filter_by(is_internal=True, is_active=True).order_by(User.first_name).all()

    return render_template('project_edit.html', project=project, available_clients=available_clients, available_members=available_members, project_member_ids=project_member_ids, available_managers=available_managers)


@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Validar permisos - solo Admin y PMP pueden eliminar
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    if user_role not in ['PMP', 'Admin']:
        flash('Solo usuarios PMP o Admin pueden eliminar proyectos.', 'danger')
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
    today = datetime.now().date()
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
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    
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
            
    # Obtener usuarios cliente para el modal de creación
    client_role = Role.query.filter_by(name='Cliente').first()
    available_clients = User.query.filter_by(role_id=client_role.id).order_by(User.first_name).all() if client_role else []
    
    # Provide current time context for templates that compare dates
    return render_template('projects.html', 
                           projects=projects, 
                           no_role=False, 
                           now=datetime.now(),
                           current_user_role_name=user_role,
                           available_clients=available_clients)


@main_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None

    # Usuario sin rol: no puede ver nada
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return redirect(url_for('main.projects'))

    # Control de acceso según rol
    if user_role in ['PMP', 'Admin']:
        # PMP/Admin puede ver cualquier proyecto
        pass
    elif user_role == 'Participante':
        # Participante solo puede ver proyectos donde tiene tareas asignadas o es miembro
        has_tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).first()
        is_member = current_user in project.members
        if not has_tasks and not is_member:
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
        # Cliente ve todas las tareas EXCEPTO las marcadas como solo internas
        # Usamos or_(is_internal_only == False, is_internal_only == None) para manejar NULL
        from sqlalchemy import or_
        tasks = Task.query.filter(
            Task.project_id == project_id,
            or_(Task.is_internal_only == False, Task.is_internal_only == None)
        ).order_by(Task.status, Task.priority.desc()).all()
    else:
        # Participantes solo ven sus tareas asignadas (incluye multi-asignados)
        tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).order_by(Task.status, Task.priority.desc()).all()

    # Sugeridos para asignación: usuarios internos
    assignees = User.query.filter_by(is_internal=True).order_by(User.first_name).all()
    # Candidate predecessors: all tasks in this project (for parent selection and dependencies)
    candidate_predecessors = Task.query.filter(Task.project_id == project_id).order_by(Task.title).all()
    
    # Build nested task tree using parent_task_id (hierarchy, not dependencies)
    def build_task_tree(task_list):
        """Build a tree structure using parent_task_id (WBS hierarchy).
        
        This creates a proper parent-child tree where:
        - Tasks with no parent_task_id are roots
        - Tasks with parent_task_id are children of that parent
        Also assigns WBS numbers (1, 1.1, 1.2, 2, 2.1, etc.)
        """
        tasks_by_id = {t.id: t for t in task_list}
        children_map = {t.id: [] for t in task_list}
        root_ids = []
        
        for t in task_list:
            if t.parent_task_id and t.parent_task_id in tasks_by_id:
                # Has a valid parent in the visible task list
                children_map[t.parent_task_id].append(t)
            else:
                # No parent or parent not visible - treat as root
                root_ids.append(t.id)
        
        # Sort function: prefer position, then status, priority, title
        status_order = {'BACKLOG': 0, 'IN_PROGRESS': 1, 'IN_REVIEW': 2, 'COMPLETED': 3}
        priority_order = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
        def sort_key(x):
            # if a manual position is set, respect it
            if getattr(x, 'position', None) is not None:
                return (0, x.position)
            return (1, status_order.get(x.status, 99), -priority_order.get(x.priority, 0), x.title or '')
        
        # Build recursive nodes with WBS numbering
        def build_node(tid, depth=0, wbs_prefix='', index=1):
            t = tasks_by_id[tid]
            t.tree_depth = depth  # Attach depth for indentation
            
            # Assign WBS number (e.g., "1", "1.1", "1.2", "2", "2.1.1")
            if wbs_prefix:
                t.wbs_number = f"{wbs_prefix}.{index}"
            else:
                t.wbs_number = str(index)
            
            children = sorted(children_map[tid], key=sort_key)
            child_nodes = []
            for i, c in enumerate(children, 1):
                child_nodes.append(build_node(c.id, depth + 1, t.wbs_number, i))
            
            return {'task': t, 'children': child_nodes}
        
        roots = [tasks_by_id[rid] for rid in root_ids]
        roots_sorted = sorted(roots, key=sort_key)
        forest = []
        for i, r in enumerate(roots_sorted, 1):
            forest.append(build_node(r.id, 0, '', i))
        
        return forest

    tasks_tree = build_task_tree(tasks)
    
    # Calculate predecessor order info for each task
    for task in tasks:
        if task.predecessors:
            # Sort predecessors by their WBS number if available, otherwise by ID
            sorted_preds = sorted(task.predecessors, key=lambda p: (getattr(p, 'wbs_number', '999'), p.id))
            task.predecessor_order = [(i+1, p) for i, p in enumerate(sorted_preds)]
        else:
            task.predecessor_order = []

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
    # Only internal users with role 'PMP' or 'Admin' can reorder tasks
    if not current_user.is_internal:
        return jsonify({'error': 'Permission denied'}), 403
    if not getattr(current_user, 'role', None) or current_user.role.name not in ['PMP', 'Admin']:
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

        # Recompute WBS numbers for current project view and return mapping so client can update UI
        tasks_all = Task.query.filter_by(project_id=project_id).all()
        tasks_by_id = {t.id: t for t in tasks_all}
        children_map = {t.id: [] for t in tasks_all}
        root_ids = []
        for t in tasks_all:
            if t.parent_task_id and t.parent_task_id in tasks_by_id:
                children_map[t.parent_task_id].append(t)
            else:
                root_ids.append(t.id)

        status_order = {'BACKLOG': 0, 'IN_PROGRESS': 1, 'IN_REVIEW': 2, 'COMPLETED': 3}
        priority_order = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
        def sort_key(x):
            if getattr(x, 'position', None) is not None:
                return (0, x.position)
            return (1, status_order.get(x.status, 99), -priority_order.get(x.priority, 0), x.title or '')

        wbs_map = {}
        def build_and_assign(tid, depth=0, prefix='', index=1):
            t = tasks_by_id[tid]
            wbs = f"{prefix}.{index}" if prefix else str(index)
            wbs_map[tid] = wbs
            children = sorted(children_map[tid], key=sort_key)
            for i, c in enumerate(children, 1):
                build_and_assign(c.id, depth+1, wbs, i)

        roots = [tasks_by_id[rid] for rid in root_ids]
        roots_sorted = sorted(roots, key=sort_key)
        for i, r in enumerate(roots_sorted, 1):
            build_and_assign(r.id, 0, '', i)

        return jsonify({'status': 'ok', 'wbs': wbs_map})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@main_bp.route('/project/<int:project_id>/kanban')
@login_required
def project_kanban(project_id):
    project = Project.query.get_or_404(project_id)
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None

    # Usuario sin rol: no puede ver nada
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return redirect(url_for('main.projects'))

    # Control de acceso según rol
    if user_role in ['PMP', 'Admin']:
        pass
    elif user_role == 'Participante':
        has_tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).first()
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
        tasks = Task.query.filter(Task.project_id == project_id).filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        ).all()
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


@main_bp.route('/project/<int:project_id>/gantt')
@login_required
def project_gantt(project_id):
    """Vista Gantt del proyecto con timeline de tareas."""
    project = Project.query.get_or_404(project_id)
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None

    # Usuario sin rol: no puede ver nada
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return redirect(url_for('main.projects'))

    # Control de acceso según rol
    if user_role in ['PMP', 'Admin']:
        pass
    elif user_role == 'Participante':
        has_tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).first()
        is_member = current_user in project.members
        if not has_tasks and not is_member:
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
        tasks = Task.query.filter_by(project_id=project_id).order_by(Task.position, Task.id).all()
    elif user_role == 'Participante':
        tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).order_by(Task.position, Task.id).all()
    elif user_role == 'Cliente' or not current_user.is_internal:
        from sqlalchemy import or_
        tasks = Task.query.filter(
            Task.project_id == project_id,
            or_(Task.is_internal_only == False, Task.is_internal_only == None)
        ).order_by(Task.position, Task.id).all()
    else:
        tasks = Task.query.filter_by(project_id=project_id, assigned_to_id=current_user.id).order_by(Task.position, Task.id).all()
    
    assignees = User.query.filter_by(is_internal=True).order_by(User.first_name).all()
    metrics = calculate_project_metrics(project_id)
    
    # Preparar datos para el Gantt
    gantt_tasks = []
    for task in tasks:
        # Necesitamos start_date y due_date para mostrar en el Gantt
        start = task.start_date
        end = task.due_date
        
        # Si no hay fechas, usar valores por defecto
        if not start and not end:
            continue  # Omitir tareas sin fechas en el Gantt
        
        if not start:
            start = end
        if not end:
            # Estimar duración basada en horas estimadas o usar 1 día por defecto
            from datetime import timedelta
            days = int(task.estimated_hours / 8) if task.estimated_hours else 1
            end = start + timedelta(days=max(1, days))
        
        # Construir lista de dependencias (predecessors)
        dependencies = ','.join([str(p.id) for p in task.predecessors]) if task.predecessors else ''
        
        gantt_tasks.append({
            'id': str(task.id),
            'name': task.title,
            'start': start.strftime('%Y-%m-%d') if hasattr(start, 'strftime') else str(start)[:10],
            'end': end.strftime('%Y-%m-%d') if hasattr(end, 'strftime') else str(end)[:10],
            'progress': 100 if task.status == 'COMPLETED' else (50 if task.status in ['IN_PROGRESS', 'IN_REVIEW'] else 0),
            'dependencies': dependencies,
            'status': task.status,
            'priority': task.priority,
            'assignee': task.assigned_to.first_name if task.assigned_to else None,
            'parent_id': task.parent_task_id
        })
    
    return render_template('gantt.html', project=project, tasks=tasks, gantt_tasks=gantt_tasks,
                          metrics=metrics, users=assignees, now=datetime.now())


# Crear tarea desde modal en project_detail
@main_bp.route('/task', methods=['POST'])
@login_required
def create_task():
    project_id = request.form.get('project_id')
    project = Project.query.get_or_404(project_id)

    # Only internal users with appropriate roles can create tasks
    if (not current_user.is_internal) or (current_user.role and current_user.role.name == 'Participante'):
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
            priority=request.form.get('priority') or 'MEDIUM'
        )

        # Assign to a client (customer) separately from internal assignee
        assigned_client_id = request.form.get('assigned_client_id')
        if assigned_client_id and assigned_client_id.strip():
            task.assigned_client_id = int(assigned_client_id)

        start_date_str = request.form.get('start_date')
        if start_date_str:
            task.start_date = datetime.fromisoformat(start_date_str)

        due_date_str = request.form.get('due_date')
        if due_date_str:
            task.due_date = datetime.fromisoformat(due_date_str)

        estimated_hours = request.form.get('estimated_hours')
        if estimated_hours and estimated_hours.strip():
            task.estimated_hours = float(estimated_hours)

        # Assign to a user(s) if provided (multi-select)
        assignee_ids = [int(x) for x in request.form.getlist('assignees') if x and x.strip()]
        if assignee_ids:
            users = User.query.filter(User.id.in_(assignee_ids)).all()
            task.assignees = users
            # Keep compatibility with single assigned_to_id: use first selected if any
            task.assigned_to_id = users[0].id if users else None

        # Parent task (hierarchy)
        parent_task_id = request.form.get('parent_task_id')
        if parent_task_id and parent_task_id.strip():
            parent_id = int(parent_task_id)
            parent_task = Task.query.get(parent_id)
            if not parent_task or parent_task.project_id != project.id:
                flash('Tarea padre inválida.', 'danger')
                return redirect(url_for('main.project_detail', project_id=project_id))
            task.parent_task_id = parent_id

        # Internal only flag - only visible for PMP/Admin
        task.is_internal_only = request.form.get('is_internal_only') == 'on'

        db.session.add(task)
        db.session.flush()  # Get task ID

        # Handle predecessors at creation time (if provided)
        predecessor_ids = [int(x) for x in request.form.getlist('predecessor_ids') if x and x.strip()]
        if predecessor_ids:
            task.validate_predecessor_ids(predecessor_ids)
            preds = Task.query.filter(Task.id.in_(predecessor_ids)).all()
            task.predecessors = preds

        # If assignees were provided via form, notify them (and persist)
        assignee_ids = [int(x) for x in request.form.getlist('assignees') if x and x.strip()]
        if assignee_ids:
            users = User.query.filter(User.id.in_(assignee_ids)).all()
            task.assignees = users
            # Keep compat with single assigned_to_id
            task.assigned_to_id = users[0].id if users else None

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

        send_email_setting = SystemSettings.get('notify_task_assigned', 'true')
        send_email = send_email_setting == 'true' or send_email_setting == True
        email_sent = False

        # If we created with multiple assignees via form, notify each (excluding creator)
        if assignee_ids:
            project_obj = Project.query.get(task.project_id) if task.project_id else None
            for uid in set(assignee_ids):
                if uid != getattr(current_user, 'id', None):
                    try:
                        NotificationService.notify(
                            user_id=uid,
                            title='Nueva tarea asignada',
                            message=f"Se te ha asignado la tarea '{task.title}'{(' en el proyecto '+project_obj.name) if project_obj else ''}",
                            notification_type=NotificationService.TASK_ASSIGNED,
                            related_entity_type='task',
                            related_entity_id=task.id,
                            send_email=send_email,
                            email_context={'task': task, 'project': project_obj, 'assigned_by': current_user}
                        )
                        email_sent = True
                    except Exception:
                        current_app.logger.exception('Failed to notify new assignee %s for task %s', uid, task.id)
        else:
            # Backwards compatibility: notify single assigned_to_id if provided
            if task.assigned_to_id and task.assigned_to_id != current_user.id:
                NotificationService.notify_task_assigned(
                    task=task,
                    assigned_by_user=current_user,
                    send_email=send_email,
                    notify_client=False
                )
                email_sent = True

        # Notificar al cliente asignado (si existe y es diferente al creador)
        if task.assigned_client_id and task.assigned_client_id != current_user.id:
            NotificationService.notify_task_assigned(
                task=task,
                assigned_by_user=current_user,
                send_email=send_email,
                notify_client=True
            )
            email_sent = True

        if email_sent and send_email:
            flash('Se ha enviado una notificación por correo al usuario asignado.', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear tarea: {str(e)}', 'danger')

    return redirect(url_for('main.project_detail', project_id=project.id))


# --- Admin: User and Role Management (PMP or Admin) ---

def _ensure_pmp():
    """Ensure user has PMP or Admin role for management features"""
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
    if not role or role.name not in ('PMP', 'Admin'):
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
                db.session.flush()  # Get role ID
                
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
        # Validate base_url first (if provided)
        base_url = (request.form.get('base_url') or '').strip()
        if base_url and not base_url.lower().startswith(('http://', 'https://')):
            flash('La Base URL debe comenzar con http:// o https://', 'danger')
            return redirect(url_for('main.admin_notifications'))

        try:
            SystemSettings.set('email_provider', request.form.get('email_provider', 'stub'), 'notifications', 'Proveedor de email', user_id=current_user.id)
            SystemSettings.set('sendgrid_api_key', request.form.get('sendgrid_api_key', ''), 'notifications', 'API Key de SendGrid', user_id=current_user.id)
            SystemSettings.set('email_from', request.form.get('email_from', ''), 'notifications', 'Email remitente', user_id=current_user.id)
            SystemSettings.set('email_from_name', request.form.get('email_from_name', 'BridgeWork'), 'notifications', 'Nombre remitente', user_id=current_user.id)
            # Normalize and save base_url (remove trailing slash)
            if base_url:
                base_url = base_url.rstrip('/')
            SystemSettings.set('base_url', base_url, 'notifications', 'Base URL para enlaces en emails', user_id=current_user.id)

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

    # Only internal users with appropriate roles can create projects
    if not current_user.is_internal or (current_user.role and current_user.role.name in ['Participante', 'Cliente']):
        flash('No tienes permiso para crear proyectos.', 'danger')
        return redirect(url_for('main.projects'))
    
    try:
        new_project = Project(
            name=name,
            description=description,
            budget_hours=float(budget_hours) if budget_hours and budget_hours.strip() else None,
            status='ACTIVE',
            project_type=project_type,
            manager_id=current_user.id if current_user.is_internal else None,
            start_date=datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else datetime.now().date(),
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
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    
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
        # Participante: solo ver tareas donde está asignado (incluye multi-asignados)
        query = query.filter(
            (Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))
        )
    elif user_role == 'Cliente' or not current_user.is_internal:
        # Cliente: solo ver tareas que estén asignadas al cliente explícitamente
        query = query.filter(Task.assigned_client_id == current_user.id)
    else:
        # Cualquier otro rol: no ve nada
        query = query.filter(Task.id == -1)  # Query que no devuelve nada
    
    if status_filter:
        # Treat COMPLETED filter as including both 'COMPLETED' and legacy 'DONE' statuses
        if status_filter == 'COMPLETED':
            query = query.filter(Task.status.in_(['COMPLETED', 'DONE']))
        else:
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
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    page = int(request.args.get('page', 1))
    per_page = 25

    # Usuario sin rol: mostrar mensaje y lista vacía
    if not user_role:
        flash('No tienes un rol asignado. Contacta al administrador para obtener acceso.', 'warning')
        return render_template('time_entries.html', time_entries=[], total_hours_week=0, page=1, total_pages=0, users=[], total_count=0, page_urls=[], prev_url=None, next_url=None, no_role=True)

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

    # If PMP/Admin, expose list of users for filter (only users that have time entries within the date filters)
    users = []
    if user_role in ['PMP', 'Admin']:
        user_ids_q = db.session.query(TimeEntry.user_id.distinct())
        if start_date_s:
            try:
                s_date = datetime.strptime(start_date_s, '%Y-%m-%d').date()
                user_ids_q = user_ids_q.filter(TimeEntry.date >= s_date)
            except Exception:
                pass
        if end_date_s:
            try:
                e_date = datetime.strptime(end_date_s, '%Y-%m-%d').date()
                user_ids_q = user_ids_q.filter(TimeEntry.date <= e_date)
            except Exception:
                pass
        user_ids = [r[0] for r in user_ids_q.all()]
        if user_ids:
            users = User.query.filter(User.id.in_(user_ids)).order_by(User.first_name).all()
        else:
            users = []

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
            TimeEntry.date >= (datetime.now().date().replace(day=1))
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
            project_clients.c.user_id == c.id
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


@main_bp.route('/clients/create', methods=['POST'])
@login_required
def create_client():
    """Create a new client user"""
    if not _ensure_pmp():
        return redirect(url_for('main.clients'))
    
    from werkzeug.security import generate_password_hash
    
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    company = request.form.get('company', '').strip()
    phone = request.form.get('phone', '').strip()
    
    # Validation
    if not email:
        flash('El email es requerido.', 'danger')
        return redirect(url_for('main.clients'))
    
    if User.query.filter_by(email=email).first():
        flash('Ya existe un usuario con ese email.', 'danger')
        return redirect(url_for('main.clients'))
    
    if not password or len(password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
        return redirect(url_for('main.clients'))
    
    # Get or create client role
    client_role = Role.query.filter_by(name='Cliente').first()
    if not client_role:
        # Create the role if it doesn't exist
        client_role = Role(name='Cliente')
        db.session.add(client_role)
        db.session.flush()
    
    client = User(
        email=email,
        first_name=first_name or None,
        last_name=last_name or None,
        company=company or None,
        phone=phone or None,
        is_internal=False,
        is_active=True,
        role_id=client_role.id
    )
    client.set_password(password)
    
    db.session.add(client)
    db.session.commit()
    
    flash(f'Cliente {email} creado exitosamente.', 'success')
    return redirect(url_for('main.clients'))


@main_bp.route('/clients/update', methods=['POST'])
@login_required
def update_client():
    """Update an existing client user"""
    if not _ensure_pmp():
        return redirect(url_for('main.clients'))
    
    from werkzeug.security import generate_password_hash
    
    client_id = request.form.get('client_id')
    client = User.query.get_or_404(client_id)
    
    # Only allow editing non-internal users (clients)
    if client.is_internal:
        flash('No puedes editar usuarios internos desde esta página.', 'danger')
        return redirect(url_for('main.clients'))
    
    # Azure users can only have company/phone updated
    is_azure = bool(client.azure_oid)
    
    if is_azure:
        # Only update additional info for Azure users
        client.company = request.form.get('company', '').strip() or None
        client.phone = request.form.get('phone', '').strip() or None
    else:
        # Local users - all fields can be updated
        email = request.form.get('email', '').strip()
        if email and email != client.email:
            if User.query.filter_by(email=email).first():
                flash('Ya existe un usuario con ese email.', 'danger')
                return redirect(url_for('main.clients'))
            client.email = email
        
        client.first_name = request.form.get('first_name', '').strip() or None
        client.last_name = request.form.get('last_name', '').strip() or None
        client.company = request.form.get('company', '').strip() or None
        client.phone = request.form.get('phone', '').strip() or None
        
        # Update password only if provided
        password = request.form.get('password', '')
        if password:
            if len(password) < 6:
                flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
                return redirect(url_for('main.clients'))
            client.set_password(password)
    
    db.session.commit()
    flash(f'Cliente {client.email} actualizado.', 'success')
    return redirect(url_for('main.clients'))


@main_bp.route('/clients/delete', methods=['POST'])
@login_required
def delete_client():
    """Delete a client user (only if they have no projects)"""
    if not _ensure_pmp():
        return redirect(url_for('main.clients'))
    
    client_id = request.form.get('client_id')
    client = User.query.get_or_404(client_id)
    
    # Only allow deleting non-internal users (clients)
    if client.is_internal:
        flash('No puedes eliminar usuarios internos desde esta página.', 'danger')
        return redirect(url_for('main.clients'))
    
    # Check if client has associated projects
    has_projects = db.session.query(project_clients).filter(
        project_clients.c.user_id == client.id
    ).first()
    
    if has_projects:
        flash('No se puede eliminar el cliente porque tiene proyectos asociados.', 'danger')
        return redirect(url_for('main.clients'))
    
    email = client.email
    db.session.delete(client)
    db.session.commit()
    
    flash(f'Cliente {email} eliminado.', 'success')
    return redirect(url_for('main.clients'))


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
    
    # Hours by user (last 30 days)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    user_hours = db.session.query(
        User.email,
        func.sum(TimeEntry.hours).label('total_hours')
    ).join(TimeEntry).filter(
        TimeEntry.date >= thirty_days_ago
    ).group_by(User.id, User.email).all()
    
    return render_template('reports.html',
        total_projects=total_projects,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        total_budget=total_budget,
        total_hours_spent=total_hours_spent,
        budget_usage_percent=budget_usage_percent,
        user_hours=user_hours
    )


# ========== TIME ENTRIES ROUTES ==========

@main_bp.route('/time-entries/new', methods=['GET', 'POST'])
@login_required
def create_time_entry():
    if request.method == 'POST':
        try:
            task_id = request.form.get('task_id')
            task = Task.query.get_or_404(task_id)
            
            # Validar que no hay predecesoras incompletas
            incomplete_preds = task.incomplete_predecessors()
            if incomplete_preds:
                pred_names = ', '.join([p.title for p in incomplete_preds[:3]])
                if len(incomplete_preds) > 3:
                    pred_names += f' y {len(incomplete_preds) - 3} más'
                flash(f'No se puede registrar tiempo en esta tarea. Primero deben completarse las tareas predecesoras: {pred_names}', 'warning')
                return redirect(url_for('main.create_time_entry', task_id=task_id))
            
            date_str = request.form.get('date')
            hours = float(request.form.get('hours'))
            description = request.form.get('description')
            is_billable = request.form.get('is_billable') == 'on'
            
            time_entry = TimeEntry(
                task_id=task_id,
                user_id=current_user.id,
                date=datetime.fromisoformat(date_str).date() if date_str else datetime.now().date(),
                hours=hours,
                description=description,
                is_billable=is_billable
            )
            
            db.session.add(time_entry)
            db.session.flush()
            
            # Auditoría
            audit = AuditLog(
                entity_type='TimeEntry',
                entity_id=time_entry.id,
                action='CREATE',
                user_id=current_user.id,
                changes={'task_id': task_id, 'hours': hours, 'date': str(time_entry.date)}
            )
            db.session.add(audit)
            db.session.commit()
            flash(f'Tiempo registrado: {hours}h', 'success')
            return redirect(url_for('main.time_entries'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    # Show tasks based on role: PMP/Admin sees all, others see only their assigned tasks
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    if user_role in ['PMP', 'Admin']:
        tasks = Task.query.order_by(Task.title).all()
    else:
        tasks = Task.query.filter_by(assigned_to_id=user.id if user else -1).order_by(Task.title).all()
    
    # Marcar tareas bloqueadas por predecesoras
    for t in tasks:
        t.has_incomplete_predecessors = len(t.incomplete_predecessors()) > 0

    selected_task_id = request.args.get('task_id', type=int)
    return render_template('time_entry_edit.html', tasks=tasks, now=datetime.now(), selected_task_id=selected_task_id)


@main_bp.route('/time-entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_time_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    
    # Solo el propietario o PMP puede editar (PMP puede marcar facturado)
    is_owner = entry.user_id == current_user.id
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    role_name = user.role.name if (user and user.role) else None
    if not (is_owner or role_name == 'PMP'):
        flash('No tienes permiso para editar este registro.', 'danger')
        return redirect(url_for('main.time_entries'))
    
    if request.method == 'POST':
        try:
            old_values = {'date': str(entry.date), 'hours': float(entry.hours), 'is_billable': entry.is_billable}
            
            # Only owners can modify date/hours/description
            if is_owner:
                entry.date = datetime.fromisoformat(request.form.get('date')).date()
                entry.hours = float(request.form.get('hours'))
                entry.description = request.form.get('description')
            # Only PMP users can change the 'is_billable' flag
            if role_name == 'PMP':
                entry.is_billable = request.form.get('is_billable') == 'on'
            else:
                # preserve existing value (ignore any tampering in form)
                entry.is_billable = entry.is_billable
            
            new_values = {'date': str(entry.date), 'hours': float(entry.hours), 'is_billable': entry.is_billable}
            changes = {k: {'old': old_values[k], 'new': new_values[k]} for k in old_values if old_values[k] != new_values[k]}
            
            if changes:
                audit = AuditLog(
                    entity_type='TimeEntry',
                    entity_id=entry.id,
                    action='UPDATE',
                    user_id=current_user.id,
                    changes=changes
                )
                db.session.add(audit)
            
            db.session.commit()
            flash('Registro actualizado.', 'success')
            return redirect(url_for('main.time_entries'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    
    tasks = Task.query.all()
    return render_template('time_entry_edit.html', entry=entry, tasks=tasks)


@main_bp.route('/time-entry/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_time_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    
    if entry.user_id != current_user.id:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('main.time_entries'))
    
    try:
        # Auditoría antes de eliminar
        audit = AuditLog(
            entity_type='TimeEntry',
            entity_id=entry.id,
            action='DELETE',
            user_id=current_user.id,
            changes={'task_id': entry.task_id, 'hours': float(entry.hours), 'date': str(entry.date)}
        )
        db.session.add(audit)
        
        db.session.delete(entry)
        db.session.commit()
        flash('Registro eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('main.time_entries'))


# ========== TASK ROUTES (ENHANCED) ==========

@main_bp.route('/task/<int:task_id>/status', methods=['POST'])
@internal_required
def update_task_status(task_id):
    from flask import session
    task = Task.query.get_or_404(task_id)
    project = task.project

    # Load fresh user from session
    from ..models import User
    uid = session.get('_user_id')
    user = User.query.get(int(uid)) if uid else None

    if not user or (project.manager_id and project.manager_id != user.id):
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        new_status = request.form.get('status')
        
        # Validate if task can advance to new status
        if new_status:
            can_advance, error_msg, blockers = task.can_advance_status(new_status)
            if not can_advance:
                return jsonify({
                    'error': error_msg,
                    **(blockers or {})
                }), 400

        task.status = new_status
        db.session.commit()
        return redirect(url_for('main.project_detail', project_id=project.id))
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@main_bp.route('/task/<int:task_id>')
@login_required
def task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    user_role = user.role.name if (user and user.role) else None
    
    # Control de acceso
    can_view = False
    can_edit = False
    
    if user_role in ['PMP', 'Admin']:
        can_view = True
        can_edit = True
    elif user_role == 'Participante':
        # Participante puede ver/editar si es su tarea asignada (incluye multi-asignados)
        if task.assigned_to_id == current_user.id or (getattr(task, 'assignees', None) and any(u.id == current_user.id for u in task.assignees)):
            can_view = True
            can_edit = True
    elif user_role == 'Cliente' or not current_user.is_internal:
        # Cliente puede ver tareas de sus proyectos solo si la tarea es visible externamente o está asignada a él (solo lectura)
        if current_user in project.clients:
            if task.is_external_visible or task.assigned_client_id == current_user.id:
                can_view = True
                can_edit = False
    
    if not can_view:
        flash('No tienes permiso para ver esta tarea.', 'danger')
        return redirect(url_for('main.projects'))
    
    time_entries = TimeEntry.query.filter_by(task_id=task_id).all()
    total_hours = db.session.query(func.sum(TimeEntry.hours)).filter_by(task_id=task_id).scalar() or 0
    
    return render_template('task_detail.html', task=task, time_entries=time_entries, total_hours=total_hours, now=datetime.now(), can_edit=can_edit)


@main_bp.route('/task/<int:task_id>/move', methods=['POST'])
@login_required
def move_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project

    # Only internal users can move tasks between statuses
    from ..auth.decorators import _get_user_from_session
    user = _get_user_from_session()
    if not user or not user.is_internal:
        return jsonify({'error': 'No tienes permiso para mover tareas.'}), 403

    data = request.get_json() or request.form
    new_status = data.get('status')
    old_status = task.status

    VALID_STATUSES = ['BACKLOG', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED']
    if not new_status or new_status not in VALID_STATUSES:
        return jsonify({'error': 'Estado inválido.'}), 400

    # Validate if task can advance to new status (blocked by predecessors or children)
    can_advance, error_msg, blockers = task.can_advance_status(new_status)
    if not can_advance:
        return jsonify({
            'error': error_msg,
            **(blockers or {})
        }), 400

    try:
        task.status = new_status
        
        # Registrar auditoría de cambio de estado (use session-bound user)
        audit = AuditLog(
            entity_type='Task',
            entity_id=task.id,
            action='UPDATE',
            user_id=user.id,
            changes={'status': {'old': old_status, 'new': new_status}}
        )
        db.session.add(audit)
        
        # Si la tarea se completa, notificar a los clientes
        if new_status == 'COMPLETED' and old_status != 'COMPLETED':
            notify_clients_task_completed(task, completed_by_user=user)
        # Notificar cambio de estado al asignado (solo in-app, sin email)
        elif old_status != new_status and task.assigned_to_id:
            NotificationService.notify_task_status_changed(
                task=task,
                old_status=old_status,
                changed_by_user=user,
                send_email=False
            )
        
        db.session.commit()
        return jsonify({'status': 'ok', 'task_id': task.id, 'new_status': task.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@main_bp.route('/user/<int:user_id>')
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    # Only internal users can view other users' profiles (PMP/Admins primarily). Allow self view.
    if current_user.id != user.id and not current_user.is_internal:
        flash('No tienes permiso para ver este perfil.', 'danger')
        return redirect(url_for('main.profile'))

    # Compute simple stats
    tasks_assigned = Task.query.filter_by(assigned_to_id=user.id).count()
    tasks_completed = Task.query.filter_by(assigned_to_id=user.id, status='COMPLETED').count()
    projects_managed = Project.query.filter_by(manager_id=user.id).count() if user.is_internal else 0
    total_hours = db.session.query(func.coalesce(func.sum(TimeEntry.hours), 0)).filter(TimeEntry.user_id == user.id).scalar() or 0

    recent_tasks = Task.query.filter_by(assigned_to_id=user.id).order_by(Task.due_date.desc().nullslast()).limit(5).all()

    # Attach last activity timestamp for each recent task (from AuditLog, TimeEntry, or approval timestamp)
    for t in recent_tasks:
        last_audit = db.session.query(func.max(AuditLog.created_at)).filter(AuditLog.entity_type == 'Task', AuditLog.entity_id == t.id).scalar()
        last_entry = db.session.query(func.max(TimeEntry.created_at)).filter(TimeEntry.task_id == t.id).scalar()
        candidates = [dt for dt in (last_audit, last_entry, t.approved_at) if dt is not None]
        t.last_activity = max(candidates) if candidates else None

    stats = {
        'tasks_assigned': tasks_assigned,
        'tasks_completed': tasks_completed,
        'projects_managed': projects_managed,
        'total_hours': float(total_hours)
    }

    return render_template('user_profile.html', user=user, stats=stats, recent_tasks=recent_tasks)


@main_bp.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project

    # Permitir a usuarios internos o al cliente del proyecto
    can_edit = current_user.is_internal or project.client_id == current_user.id
    if not can_edit:
        flash('No tienes permiso para editar esta tarea.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project.id))

    if request.method == 'POST':
        try:
            # Guardar valores anteriores para detectar cambios y auditoría
            old_assigned_to_id = task.assigned_to_id
            old_assigned_client_id = task.assigned_client_id
            old_parent_id = task.parent_task_id
            old_assignees = set([u.id for u in task.assignees]) if getattr(task, 'assignees', None) else set()
            old_values = {
                'title': task.title,
                'status': task.status,
                'priority': task.priority,
                'assigned_to_id': task.assigned_to_id,
                'is_internal_only': task.is_internal_only,
                'predecessor_ids': sorted([p.id for p in task.predecessors]),
                'parent_task_id': task.parent_task_id
            }
            
            task.title = request.form.get('title') or task.title
            task.description = request.form.get('description')
            # Handle optional status change: only update if provided and valid
            status_from_form = request.form.get('status')
            if status_from_form and status_from_form != task.status:
                can_advance, error_msg, blockers = task.can_advance_status(status_from_form)
                if not can_advance:
                    raise ValueError(error_msg)
                task.status = status_from_form
            # If no status provided, keep existing task.status unchanged
            task.priority = request.form.get('priority') or task.priority
            task.is_internal_only = request.form.get('is_internal_only') == 'on'

            start_date_str = request.form.get('start_date')
            if start_date_str:
                task.start_date = datetime.fromisoformat(start_date_str)
            else:
                task.start_date = None

            due_date_str = request.form.get('due_date')
            if due_date_str:
                task.due_date = datetime.fromisoformat(due_date_str)
            else:
                task.due_date = None

            # Update parent task (validate no cycles)
            parent_task_id = request.form.get('parent_task_id')
            if parent_task_id and parent_task_id.strip():
                new_parent_id = int(parent_task_id)
                if new_parent_id == task.id:
                    raise ValueError('La tarea no puede ser su propia tarea padre')
                parent_task = Task.query.get(new_parent_id)
                if not parent_task or parent_task.project_id != project.id:
                    raise ValueError('Tarea padre inválida')
                # Ensure not assigning a descendant as parent (would create cycle)
                descendant_ids = [d.id for d in task.descendants()]
                if new_parent_id in descendant_ids:
                    raise ValueError('No se puede asignar una subtarea como tarea padre')
                task.parent_task_id = new_parent_id
            else:
                task.parent_task_id = None

            estimated_hours = request.form.get('estimated_hours')
            if estimated_hours and estimated_hours.strip():
                task.estimated_hours = float(estimated_hours)
            else:
                task.estimated_hours = None

            # Update assignees (multi-select). Keep assigned_to_id for compatibility (first selected)
            current_app.logger.debug('edit_task: raw assignees payload = %s', request.form.getlist('assignees'))
            assignee_ids = [int(x) for x in request.form.getlist('assignees') if x and x.strip()]
            # Use ORM relationship management only (avoid direct SQL deletes that confuse the ORM unit-of-work)
            if assignee_ids:
                users = User.query.filter(User.id.in_(assignee_ids)).all()
                task.assignees = users
                task.assigned_to_id = users[0].id if users else None
            else:
                # If no assignees selected, clear assignees and assigned_to_id
                task.assignees = []
                task.assigned_to_id = None

            # Update assigned client (separate field)
            assigned_client_id = request.form.get('assigned_client_id')
            new_assigned_client_id = int(assigned_client_id) if assigned_client_id and assigned_client_id.strip() else None
            task.assigned_client_id = new_assigned_client_id

            # Handle predecessors (many-to-many)
            predecessor_ids = [int(x) for x in request.form.getlist('predecessor_ids') if x and x.strip()]
            try:
                # validate before assignment
                task.validate_predecessor_ids(predecessor_ids)
                if predecessor_ids:
                    preds = Task.query.filter(Task.id.in_(predecessor_ids)).all()
                else:
                    preds = []
                task.predecessors = preds
            except ValueError as ve:
                raise ve

            # Handle file attachments
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # get_unique_filename returns (stored_filename, task_folder)
                    stored_filename, task_folder = get_unique_filename(task.id, filename)
                    
                    # task_folder is already created inside get_unique_filename
                    file_path = os.path.join(task_folder, stored_filename)
                    file.save(file_path)
                    
                    attachment = TaskAttachment(
                        task_id=task.id,
                        filename=filename,
                        stored_filename=stored_filename,
                        file_size=os.path.getsize(file_path),
                        mime_type=file.content_type,
                        uploaded_by_id=current_user.id
                    )
                    db.session.add(attachment)

            # Registrar auditoría de cambios en tarea
            new_values = {
                'title': task.title,
                'status': task.status,
                'priority': task.priority,
                'assigned_to_id': task.assigned_to_id,
                'is_internal_only': task.is_internal_only,
                'predecessor_ids': sorted([p.id for p in task.predecessors]),
                'parent_task_id': task.parent_task_id
            }
            changes = {k: {'old': old_values[k], 'new': new_values[k]} for k in old_values if old_values[k] != new_values[k]}
            
            if changes:
                audit = AuditLog(
                    entity_type='Task',
                    entity_id=task.id,
                    action='UPDATE',
                    user_id=current_user.id,
                    changes=changes
                )
                db.session.add(audit)

            db.session.commit()
            
            send_email_setting = SystemSettings.get('notify_task_assigned', 'true')
            send_email = send_email_setting == 'true' or send_email_setting == True
            email_sent = False

            # Notify newly added assignees (for multi-assign)
            new_assignees = set([u.id for u in task.assignees]) if getattr(task, 'assignees', None) else set()
            added = new_assignees - old_assignees
            if added:
                project_obj = Project.query.get(task.project_id) if task.project_id else None
                for uid in added:
                    if uid != getattr(current_user, 'id', None):
                        try:
                            NotificationService.notify(
                                user_id=uid,
                                title='Nueva tarea asignada',
                                message=f"Se te ha asignado la tarea '{task.title}'{(' en el proyecto '+project_obj.name) if project_obj else ''}",
                                notification_type=NotificationService.TASK_ASSIGNED,
                                related_entity_type='task',
                                related_entity_id=task.id,
                                send_email=send_email,
                                email_context={'task': task, 'project': project_obj, 'assigned_by': current_user}
                            )
                            email_sent = True
                        except Exception:
                            current_app.logger.exception('Failed to notify new assignee %s for task %s', uid, task.id)

            # Notificar si se asignó a un nuevo cliente
            if new_assigned_client_id and new_assigned_client_id != old_assigned_client_id and new_assigned_client_id != current_user.id:
                NotificationService.notify_task_assigned(
                    task=task,
                    assigned_by_user=current_user,
                    send_email=send_email,
                    notify_client=True
                )
                email_sent = True

            if email_sent and send_email:
                flash('Se ha enviado una notificación por correo al usuario asignado.', 'info')            
            flash('Tarea actualizada.', 'success')
            return redirect(url_for('main.project_detail', project_id=project.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception('Error updating task %s: %s', task.id if task else None, e)
            flash(f'Error al actualizar: {str(e)}', 'danger')

    # Provide user list for assignment
    users = User.query.filter_by(is_internal=True).order_by(User.first_name).all()
    # Candidate predecessors: tasks within the same project (exclude self)
    candidate_predecessors = Task.query.filter(Task.project_id == project.id, Task.id != task.id).order_by(Task.title).all()
    return render_template('task_edit.html', task=task, project=project, users=users, candidate_predecessors=candidate_predecessors)


@main_bp.route('/task/<int:task_id>/client_accept', methods=['POST'])
@login_required
def client_accept_task(task_id):
    """Allow a project client to accept a task and mark it as completed (with approval metadata)."""
    task = Task.query.get_or_404(task_id)
    project = task.project

    # Only allow project client to accept
    is_project_client = (project.client_id and project.client_id == current_user.id) or (current_user in project.clients)
    if current_user.is_internal or not is_project_client:
        flash('No tienes permiso para realizar esta acción.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))

    # Additionally, client can only accept tasks that are explicitly assigned to them
    if task.assigned_client_id != current_user.id:
        flash('No tienes permiso para realizar esta acción.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))

    # Prevent completing if predecessors or descendants incomplete
    blockers = task.get_completion_blockers()
    if blockers['incomplete_predecessors']:
        flash('No se puede completar la tarea mientras existan predecesoras incompletas', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))
    if blockers['incomplete_children']:
        flash('No se puede completar la tarea mientras existan subtareas incompletas', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))

    try:
        old_status = task.status
        task.status = 'COMPLETED'
        task.approval_status = 'APPROVED'
        task.approved_by_id = current_user.id
        task.approved_at = datetime.now()

        audit = AuditLog(
            entity_type='Task',
            entity_id=task.id,
            action='UPDATE',
            user_id=current_user.id,
            changes={'status': {'old': old_status, 'new': task.status}, 'approval_status': {'old': None, 'new': 'APPROVED'}}
        )
        db.session.add(audit)
        db.session.commit()
        flash('Tarea aceptada y marcada como completada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('main.task_detail', task_id=task.id))


@main_bp.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.project

    # Solo usuarios internos pueden eliminar tareas
    if not current_user.is_internal:
        flash('No tienes permiso para eliminar esta tarea.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project.id))

    try:
        title = task.title
        task_id_backup = task.id
        
        # Registrar auditoría antes de eliminar
        audit = AuditLog(
            entity_type='Task',
            entity_id=task_id_backup,
            action='DELETE',
            user_id=current_user.id,
            changes={'title': title, 'project_id': project.id, 'status': task.status}
        )
        db.session.add(audit)
        
        db.session.delete(task)
        db.session.commit()
        flash(f"Tarea '{title}' eliminada.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')

    return redirect(url_for('main.project_detail', project_id=project.id))


# ========== PROFILE ROUTES ==========

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Vista del perfil del usuario actual"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            # Solo usuarios locales pueden actualizar ciertos campos
            if not current_user.azure_oid:
                current_user.first_name = request.form.get('first_name', '').strip() or current_user.first_name
                current_user.last_name = request.form.get('last_name', '').strip() or current_user.last_name
            
            db.session.commit()
            flash('Perfil actualizado correctamente.', 'success')
        
        elif action == 'change_password':
            # Solo usuarios locales pueden cambiar contraseña
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
    
    # Obtener estadísticas del usuario
    stats = {
        'tasks_assigned': Task.query.filter((Task.assigned_to_id == current_user.id) | (Task.assignees.any(User.id == current_user.id))).count(),
        'tasks_completed': Task.query.filter_by(assigned_to_id=current_user.id, status='DONE').count(),
        'projects_managed': Project.query.filter_by(manager_id=current_user.id).count() if current_user.is_internal else 0,
        'total_hours': db.session.query(func.sum(TimeEntry.hours)).filter_by(user_id=current_user.id).scalar() or 0
    }
    
    # Actividad reciente
    recent_tasks = Task.query.filter_by(assigned_to_id=current_user.id)\
        .order_by(Task.updated_at.desc() if hasattr(Task, 'updated_at') else Task.id.desc())\
        .limit(5).all()
    
    recent_time_entries = TimeEntry.query.filter_by(user_id=current_user.id)\
        .order_by(TimeEntry.date.desc())\
        .limit(5).all()
    
    return render_template('profile.html', 
                         stats=stats, 
                         recent_tasks=recent_tasks,
                         recent_time_entries=recent_time_entries)


# ========== SETTINGS ROUTES ==========

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'profile':
            # Actualizar perfil del usuario
            current_user.email = request.form.get('email') or current_user.email
            db.session.commit()
            flash('Perfil actualizado.', 'success')
        
        elif action == 'password':
            # Cambiar contraseña
            from werkzeug.security import check_password_hash, generate_password_hash
            
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
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


# --- Task Attachments ---

@main_bp.route('/task/<int:task_id>/upload', methods=['POST'])
@login_required
def upload_attachment(task_id):
    """Upload a file attachment to a task"""
    task = Task.query.get_or_404(task_id)
    project = task.project
    
    # Check permissions - internal users or a client associated with the project
    # Note: projects can have multiple clients via project.clients association
    can_upload = current_user.is_internal or (current_user in project.clients)
    if not can_upload:
        flash('No tienes permiso para subir archivos a esta tarea.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    if 'file' not in request.files:
        flash('No se seleccionó ningún archivo.', 'warning')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    file = request.files['file']
    current_app.logger.info(f"upload_attachment called by user={getattr(current_user, 'id', None)}, filename={file.filename}")
    
    if file.filename == '':
        print("DEBUG: No filename provided")
        flash('No se seleccionó ningún archivo.', 'warning')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    if not allowed_file(file.filename):
        allowed = current_app.config.get('ALLOWED_EXTENSIONS', None)
        print(f"DEBUG: File not allowed: {file.filename}; ALLOWED_EXTENSIONS={allowed} (type={type(allowed)})")
        flash('Tipo de archivo no permitido.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        # Get unique filename to avoid duplicates
        stored_filename, task_folder = get_unique_filename(task_id, file.filename)
        filepath = os.path.join(task_folder, stored_filename)
        
        # Save the file
        current_app.logger.info(f"Saving attachment to {filepath}")
        file.save(filepath)
        current_app.logger.info(f"Saved attachment to {filepath}")
        
        # Get file info
        file_size = os.path.getsize(filepath)
        mime_type = mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
        
        # Create database record
        attachment = TaskAttachment(
            task_id=task_id,
            filename=file.filename,  # Original filename
            stored_filename=stored_filename,  # Stored filename (unique)
            file_size=file_size,
            mime_type=mime_type,
            uploaded_by_id=current_user.id
        )
        db.session.add(attachment)
        db.session.commit()
        current_app.logger.debug(f"Attachment DB id after commit: {attachment.id}")
        
        flash(f'Archivo "{file.filename}" subido correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Error uploading attachment for task {task_id}: {e}")
        flash(f'Error al subir el archivo: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/attachment/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    """Download an attachment"""
    attachment = TaskAttachment.query.get_or_404(attachment_id)
    task = attachment.task
    project = task.project
    
    # Check permissions
    can_download = current_user.is_internal or project.client_id == current_user.id
    if not can_download:
        abort(403)
    
    task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task.id}')
    
    return send_from_directory(
        task_folder,
        attachment.stored_filename,
        as_attachment=True,
        download_name=attachment.filename  # Use original filename for download
    )


@main_bp.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(attachment_id):
    """Delete an attachment"""
    attachment = TaskAttachment.query.get_or_404(attachment_id)
    task = attachment.task
    project = task.project
    
    # Check permissions - only internal users or the uploader can delete
    can_delete = current_user.is_internal or attachment.uploaded_by_id == current_user.id
    if not can_delete:
        flash('No tienes permiso para eliminar este archivo.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))
    
    try:
        # Delete physical file
        task_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f'task_{task.id}')
        filepath = os.path.join(task_folder, attachment.stored_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # Delete database record
        filename = attachment.filename
        db.session.delete(attachment)
        db.session.commit()
        
        flash(f'Archivo "{filename}" eliminado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el archivo: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task.id))


# ========== NOTIFICATIONS & TASK APPROVAL ==========

@main_bp.route('/notifications')
@login_required
def notifications():
    """Vista de notificaciones del usuario"""
    user_notifications = SystemNotification.query.filter_by(user_id=current_user.id).order_by(
        SystemNotification.is_read,
        SystemNotification.created_at.desc()
    ).all()
    
    return render_template('notifications.html', notifications=user_notifications)


@main_bp.route('/notification/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Marcar una notificación como leída"""
    notification = SystemNotification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'No autorizado'}), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'status': 'ok'})


@main_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Marcar todas las notificaciones como leídas"""
    count = NotificationService.mark_all_as_read(current_user.id)
    return jsonify({'status': 'ok', 'count': count})


@main_bp.route('/search')
@login_required
def global_search():
    """Búsqueda global de proyectos, tareas y usuarios"""
    try:
        # Determine role and allow search for:
        # - internal users with role (PMP/Admin/Participante)
        # - clients (external users) but they will be limited to their projects/tasks
        user_role = current_user.role.name if (current_user and getattr(current_user, 'role', None)) else None
        if current_user.is_internal and not user_role:
            # Internal user without a role is not allowed to search
            return jsonify({'error': 'No tienes permisos para realizar búsquedas. Contacta al administrador.'}), 403

        query = request.args.get('q', '').strip()
        
        if not query or len(query) < 2:
            return jsonify({'results': [], 'query': query, 'projects': [], 'tasks': [], 'users': []})
        
        results = {
            'projects': [],
            'tasks': [],
            'users': [],
            'query': query
        }
        
        search_term = f"%{query}%"
        
        # Buscar proyectos
        if current_user.is_internal and user_role in ['PMP', 'Admin']:
            # PMP/Admin ven todos los proyectos
            projects = Project.query.filter(
                db.or_(
                    Project.name.ilike(search_term),
                    Project.description.ilike(search_term)
                )
            ).limit(5).all()
        elif current_user.is_internal and user_role == 'Participante':
            # Participante solo ve proyectos donde es miembro o tiene tareas asignadas
            projects = Project.query.filter(
                db.or_(
                    Project.name.ilike(search_term),
                    Project.description.ilike(search_term)
                ),
                db.or_(
                    Project.members.any(User.id == current_user.id),
                    Project.tasks.any(Task.assignee_id == current_user.id)
                )
            ).limit(5).all()
        else:
            # Clientes solo ven sus proyectos
            projects = Project.query.join(project_clients).filter(
                project_clients.c.user_id == current_user.id,
                db.or_(
                    Project.name.ilike(search_term),
                    Project.description.ilike(search_term)
                )
            ).limit(5).all()
        
        for p in projects:
            results['projects'].append({
                'id': p.id,
                'name': p.name,
                'status': p.status,
                'description': (p.description[:80] + '...') if p.description and len(p.description) > 80 else p.description,
                'url': url_for('main.project_detail', project_id=p.id)
            })
        
        # Buscar tareas
        if current_user.is_internal and user_role in ['PMP', 'Admin']:
            # PMP/Admin ven todas las tareas
            tasks = Task.query.filter(
                db.or_(
                    Task.title.ilike(search_term),
                    Task.description.ilike(search_term)
                )
            ).limit(8).all()
        elif current_user.is_internal and user_role == 'Participante':
            # Participante solo ve tareas que tiene asignadas o donde es miembro del proyecto
            tasks = Task.query.join(Project).filter(
                db.or_(
                    Task.title.ilike(search_term),
                    Task.description.ilike(search_term)
                ),
                db.or_(
                    Task.assignee_id == current_user.id,
                    Project.members.any(User.id == current_user.id)
                )
            ).limit(8).all()
        else:
            # Clientes solo ven tareas visibles de sus proyectos
            tasks = Task.query.join(Project).join(project_clients).filter(
                project_clients.c.user_id == current_user.id,
                Task.is_external_visible == True,
                db.or_(
                    Task.title.ilike(search_term),
                    Task.description.ilike(search_term)
                )
            ).limit(8).all()
        
        for t in tasks:
            results['tasks'].append({
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'priority': t.priority,
                'project_name': t.project.name if t.project else None,
                'url': url_for('main.task_detail', task_id=t.id)
            })
        
        # Buscar usuarios (solo para PMP/Admin)
        if current_user.is_internal and user_role in ['PMP', 'Admin']:
            users = User.query.filter(
                db.or_(
                    User.email.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term)
                )
            ).limit(5).all()
            
            for u in users:
                results['users'].append({
                    'id': u.id,
                    'name': u.name,
                    'email': u.email,
                    'is_internal': u.is_internal,
                    'role': u.role.name if u.role else None
                })
        
        return jsonify(results)
    except Exception as e:
        current_app.logger.exception(f"Search error: {e}")
        return jsonify({'error': str(e), 'projects': [], 'tasks': [], 'users': [], 'query': ''}), 500


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


@main_bp.route('/pending-approvals')
@login_required
def pending_approvals():
    """Vista de tareas pendientes de aprobación para clientes"""
    # Solo clientes pueden ver esta página
    if current_user.is_internal:
        flash('Esta sección es solo para clientes.', 'warning')
        return redirect(url_for('main.index'))
    
    # Obtener proyectos donde el usuario es cliente
    client_projects = Project.query.filter(Project.clients.contains(current_user)).all()
    project_ids = [p.id for p in client_projects]
    
    # Obtener tareas completadas pendientes de aprobación en esos proyectos
    pending_tasks = Task.query.filter(
        Task.project_id.in_(project_ids),
        Task.status == 'COMPLETED',
        Task.is_external_visible == True,
        Task.approval_status == 'PENDING'
    ).order_by(Task.due_date.desc()).all()
    
    return render_template('pending_approvals.html', tasks=pending_tasks)


@main_bp.route('/task/<int:task_id>/approve', methods=['POST'])
@login_required
def approve_task(task_id):
    """Cliente aprueba una tarea completada"""
    task = Task.query.get_or_404(task_id)
    project = task.project
    
    # Verificar que el usuario es cliente del proyecto
    if current_user not in project.clients:
        flash('No tienes permiso para aprobar esta tarea.', 'danger')
        return redirect(url_for('main.index'))
    
    notes = request.form.get('notes', '')
    
    try:
        task.approval_status = 'APPROVED'
        task.approved_by_id = current_user.id
        task.approved_at = datetime.now()
        task.approval_notes = notes
        
        # Auditoría de aprobación
        audit = AuditLog(
            entity_type='Task',
            entity_id=task.id,
            action='UPDATE',
            user_id=current_user.id,
            changes={'approval_status': {'old': 'PENDING', 'new': 'APPROVED'}, 'approved_by_client': current_user.email}
        )
        db.session.add(audit)
        
        # Marcar notificaciones relacionadas como leídas
        SystemNotification.query.filter_by(
            user_id=current_user.id,
            related_entity_type='Task',
            related_entity_id=task.id
        ).update({'is_read': True})
        
        db.session.commit()
        
        # Notificar al responsable de la tarea que fue aprobada
        NotificationService.notify_task_approved(
            task=task,
            approved_by_user=current_user,
            send_email=SystemSettings.get('notify_task_approved', True)
        )
        
        flash(f'Tarea "{task.title}" aprobada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al aprobar: {str(e)}', 'danger')
    
    return redirect(url_for('main.pending_approvals'))


@main_bp.route('/task/<int:task_id>/reject', methods=['POST'])
@login_required
def reject_task(task_id):
    """Cliente rechaza una tarea completada"""
    task = Task.query.get_or_404(task_id)
    project = task.project
    
    # Verificar que el usuario es cliente del proyecto
    if current_user not in project.clients:
        flash('No tienes permiso para rechazar esta tarea.', 'danger')
        return redirect(url_for('main.index'))
    
    notes = request.form.get('notes', '')
    
    if not notes:
        flash('Debes indicar el motivo del rechazo.', 'warning')
        return redirect(url_for('main.pending_approvals'))
    
    try:
        task.approval_status = 'REJECTED'
        task.approved_by_id = current_user.id
        task.approved_at = datetime.now()
        task.approval_notes = notes
        
        # Volver a IN_REVIEW para que el equipo revise
        task.status = 'IN_REVIEW'
        
        # Auditoría de rechazo
        audit = AuditLog(
            entity_type='Task',
            entity_id=task.id,
            action='UPDATE',
            user_id=current_user.id,
            changes={'approval_status': {'old': 'PENDING', 'new': 'REJECTED'}, 'status': {'old': 'COMPLETED', 'new': 'IN_REVIEW'}, 'rejection_reason': notes}
        )
        db.session.add(audit)
        
        # Marcar notificaciones del cliente como leídas
        SystemNotification.query.filter_by(
            user_id=current_user.id,
            related_entity_type='Task',
            related_entity_id=task.id
        ).update({'is_read': True})
        
        db.session.commit()
        
        # Notificar al responsable de la tarea que fue rechazada (con email)
        NotificationService.notify_task_rejected(
            task=task,
            rejected_by_user=current_user,
            rejection_reason=notes,
            send_email=SystemSettings.get('notify_task_rejected', True)
        )
        
        flash(f'Tarea "{task.title}" rechazada. El equipo será notificado.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al rechazar: {str(e)}', 'danger')
    
    return redirect(url_for('main.pending_approvals'))


# ========== AUDIT LOG ROUTES ==========

def pmp_or_admin_required(f):
    """Decorator to require PMP or Admin role"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.role or current_user.role.name not in ['PMP', 'Admin']:
            flash('Solo usuarios PMP o Admin pueden acceder a esta sección.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


@main_bp.route('/audit')
@login_required
@pmp_or_admin_required
def audit_log():
    """Vista del registro de auditoría - Solo PMP y Admin"""
    # Limpiar registros antiguos (más de 6 meses)
    cleanup_old_audit_logs()
    
    # Filtros
    entity_type = request.args.get('entity_type', '')
    action = request.args.get('action', '')
    user_id = request.args.get('user_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    # Construir query
    query = AuditLog.query
    
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= date_from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.created_at < date_to_dt)
        except ValueError:
            pass
    
    # Ordenar y paginar
    query = query.order_by(AuditLog.created_at.desc())
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    
    # Obtener registro más antiguo
    oldest = AuditLog.query.order_by(AuditLog.created_at.asc()).first()
    oldest_record = oldest.created_at if oldest else None
    
    # Obtener usuarios para filtro
    users = User.query.filter(User.is_internal == True).order_by(User.first_name).all()
    
    filters = {
        'entity_type': entity_type,
        'action': action,
        'user_id': user_id,
        'date_from': date_from,
        'date_to': date_to
    }
    
    return render_template('audit_log.html',
        logs=logs,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        filters=filters,
        users=users,
        oldest_record=oldest_record
    )


def cleanup_old_audit_logs():
    """Elimina registros de auditoría con más de 6 meses de antigüedad"""
    try:
        cutoff_date = datetime.now() - timedelta(days=180)  # 6 meses
        deleted_count = AuditLog.query.filter(AuditLog.created_at < cutoff_date).delete()
        if deleted_count > 0:
            db.session.commit()
            current_app.logger.info(f'Limpieza de auditoría: {deleted_count} registros eliminados')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error limpiando auditoría: {e}')


# ========== ADMIN SETTINGS ROUTES ==========

def admin_required(f):
    """Decorator to require Admin role only for settings"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.role or current_user.role.name != 'Admin':
            flash('Solo los administradores pueden acceder a esta sección.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@main_bp.route('/admin/settings', methods=['GET'])
@login_required
@admin_required
def admin_settings_page():
    """Admin settings page"""
    from app.models import SystemSettings, Role
    
    # Get all users
    users = User.query.order_by(User.created_at.desc()).all()
    
    # Get all roles
    roles = Role.query.all()
    
    # Get all settings as dict (raw DB values)
    all_settings = SystemSettings.query.all()
    settings = {s.key: s.value for s in all_settings}
    
    # Ensure sensible defaults: notifications ON by default
    defaults = {
        'notify_task_assigned': 'true',
        'notify_task_completed': 'true',
        'notify_task_approved': 'true',
        'notify_task_rejected': 'true',
        'notify_task_comment': 'true',
        'notify_due_date_reminder': 'true',
        'show_notification_center': 'true'
    }
    for k, v in defaults.items():
        settings.setdefault(k, v)

    # Normalize boolean-like options so templates can rely on Python booleans
    notify_keys = [
        'notify_task_assigned', 'notify_task_completed', 'notify_task_approved',
        'notify_task_rejected', 'notify_task_comment', 'notify_due_date_reminder',
        'show_notification_center', 'enable_push_notifications'
    ]
    for k in notify_keys:
        raw = settings.get(k, defaults.get(k, 'true'))
        if isinstance(raw, str):
            settings[k] = raw.lower() not in ('false', '0', 'no')
        else:
            settings[k] = bool(raw)
    
    # Get system stats
    stats = {
        'total_users': User.query.count(),
        'total_projects': Project.query.count(),
        'total_tasks': Task.query.count(),
        'active_users': User.query.filter_by(is_active=True).count()
    }
    
    return render_template('admin_settings.html', 
                         users=users, 
                         roles=roles,
                         settings=settings,
                         stats=stats)


@main_bp.route('/admin/settings', methods=['POST'])
@login_required
@admin_required
def admin_settings():
    """Handle admin settings form submission"""
    from app.models import SystemSettings
    
    section = request.form.get('section', 'general')
    
    # Get all form fields (except section and csrf)
    fields_to_save = {k: v for k, v in request.form.items() 
                     if k not in ('section', 'csrf_token')}
    
    # Handle checkboxes (they only submit when checked)
    checkbox_fields = [
        'smtp_use_tls', 'allow_projects_without_manager', 'require_task_estimation',
        'block_parent_until_children_complete', 'notify_task_assigned', 'notify_task_completed',
        'notify_task_approved', 'notify_task_rejected', 'notify_task_comment', 
        'notify_due_date_reminder', 'show_notification_center',
        'enable_push_notifications', 'enable_azure_auth', 'enable_local_auth',
        'allow_public_registration', 'password_require_complexity'
    ]
    
    for cb in checkbox_fields:
        if cb not in fields_to_save:
            fields_to_save[cb] = 'false'
        else:
            fields_to_save[cb] = 'true'
    
    # Handle password field - don't update if empty
    if 'smtp_password' in fields_to_save and not fields_to_save['smtp_password']:
        del fields_to_save['smtp_password']
    
    # Save each setting; for checkbox fields, save as boolean value_type
    for key, value in fields_to_save.items():
        if value is not None and value != '':
            value_type = 'boolean' if key in checkbox_fields else 'string'
            SystemSettings.set(
                key=key,
                value=str(value),
                category=section,
                description=None,
                value_type=value_type,
                user_id=current_user.id
            )
    
    db.session.commit()
    flash('Configuración guardada correctamente.', 'success')
    return redirect(url_for('main.admin_settings_page') + f'#{section}')


@main_bp.route('/admin/settings/user/create', methods=['POST'])
@login_required
@admin_required
def admin_settings_create_user():
    """Create a new user from settings page"""
    from werkzeug.security import generate_password_hash
    from app.models import Role
    
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    role_id = request.form.get('role_id')
    is_internal = request.form.get('is_internal') == '1'
    
    # Check if email already exists
    if User.query.filter_by(email=email).first():
        flash('Ya existe un usuario con ese email.', 'danger')
        return redirect(url_for('main.admin_settings_page') + '#users')
    
    # Create user
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        role_id=int(role_id) if role_id else None,
        is_internal=is_internal,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()
    
    flash(f'Usuario {email} creado correctamente.', 'success')
    return redirect(url_for('main.admin_settings_page') + '#users')


@main_bp.route('/admin/settings/user/update', methods=['POST'])
@login_required
@admin_required  
def admin_settings_update_user():
    """Update an existing user from settings page"""
    from werkzeug.security import generate_password_hash
    
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    # Azure Entra ID users can only have their role updated
    is_azure_user = bool(user.azure_oid)
    
    if is_azure_user:
        # Only allow role update for Azure users
        user.role_id = int(request.form.get('role_id')) if request.form.get('role_id') else user.role_id
    else:
        # Local users - all fields can be updated
        user.email = request.form.get('email', user.email)
        user.first_name = request.form.get('first_name', user.first_name)
        user.last_name = request.form.get('last_name', user.last_name)
        user.role_id = int(request.form.get('role_id')) if request.form.get('role_id') else user.role_id
        user.is_internal = request.form.get('is_internal') == '1'
        
        # Update password only if provided
        password = request.form.get('password')
        if password:
            user.password_hash = generate_password_hash(password)
    
    db.session.commit()
    flash(f'Usuario {user.email} actualizado.', 'success')
    return redirect(url_for('main.admin_settings_page') + '#users')


@main_bp.route('/api/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'No puedes desactivar tu propia cuenta'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': user.is_active})


@main_bp.route('/admin/test-email', methods=['POST'])
@login_required
@admin_required
def admin_test_email():
    """Test SMTP email configuration"""
    from app.models import SystemSettings
    import smtplib
    from email.mime.text import MIMEText

    try:
        # Get email settings
        host = SystemSettings.get('smtp_host', '')
        port = int(SystemSettings.get('smtp_port', '587'))
        username = SystemSettings.get('smtp_username', '')
        password = SystemSettings.get('smtp_password', '')
        use_tls = SystemSettings.get('smtp_use_tls', 'true') == 'true'
        from_email = SystemSettings.get('email_from', username)
        from_name = SystemSettings.get('email_from_name', 'BridgeWork')

        if not host or not username:
            return jsonify({'success': False, 'error': 'Configura el servidor SMTP primero'}), 400

        # Create test message
        msg = MIMEText(f'Este es un correo de prueba desde {from_name}.\n\nSi recibes este mensaje, la configuración SMTP es correcta.')
        msg['Subject'] = f'[{from_name}] Prueba de conexión SMTP'
        msg['From'] = f'{from_name} <{from_email}>'
        msg['To'] = current_user.email

        # Connect and send
        if use_tls and port == 587:
            server = smtplib.SMTP(host, port)
            server.starttls()
        elif port == 465:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)

        if username and password:
            server.login(username, password)

        server.sendmail(from_email, [current_user.email], msg.as_string())
        server.quit()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/admin/run-due-reminders', methods=['POST'])
@login_required
@admin_required
def admin_run_due_reminders():
    """Trigger generation of due date reminders manually (admin-only)."""
    from app.tasks.alerts import generate_alerts

    try:
        res = generate_alerts()
        created = res.get('created', [])
        groups = res.get('groups', {})
        # Ensure keys are JSON-serializable (strings)
        simple_groups = {str(k): len(v) for k, v in groups.items()}
        return jsonify({'success': True, 'created': len(created), 'groups': simple_groups})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/admin/enable-all-notifications', methods=['POST'])
@login_required
@admin_required
def admin_enable_all_notifications():
    """Enable all email notification toggles (admin-only convenience endpoint)."""
    from app.models import SystemSettings, AuditLog

    keys = [
        'notify_task_assigned', 'notify_task_completed', 'notify_task_approved',
        'notify_task_rejected', 'notify_task_comment', 'notify_due_date_reminder',
        'show_notification_center', 'enable_push_notifications'
    ]
    try:
        for k in keys:
            SystemSettings.set(k, 'true', category='notifications', value_type='boolean', user_id=current_user.id)
        # Audit log
        audit = AuditLog(
            entity_type='SystemSettings',
            entity_id=0,
            action='UPDATE',
            user_id=current_user.id,
            changes={'enabled_all_notifications': True}
        )
        db.session.add(audit)
        db.session.commit()
        return jsonify({'success': True, 'enabled': keys})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/admin/send-test-notification', methods=['POST'])
@login_required
@admin_required
def admin_send_test_notification():
    """Create a test notification for the current admin user and attempt send (admin-only)."""
    from app.services.notifications import NotificationService

    try:
        # Create an in-app notification
        note = NotificationService.create(
            user_id=current_user.id,
            title='Prueba de Notificación',
            message='Este es un mensaje de prueba generado desde la configuración de administrador',
            notification_type=NotificationService.GENERAL
        )
        # Attempt to send email for this notification
        sent = NotificationService.send_email(user_id=current_user.id, subject=note.title, notification_type=note.notification_type, context={'message': note.message, 'title': note.title})
        return jsonify({'success': True, 'notification_id': note.id, 'email_sent': bool(sent)})
    except Exception as e:
        current_app.logger.exception('Error sending test notification: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500