from sqlalchemy import func
from . import db
from .models import Task, TimeEntry, Project

def calculate_project_metrics(project_id):
    """
    Calcula KPIs financieros y de ejecución para un proyecto específico.
    Retorna un diccionario listo para usar en la plantilla.
    """
    project = Project.query.get(project_id)
    if not project:
        return {
            'total_tasks': 0,
            'completed_tasks': 0,
            'total_hours': 0,
            'budget_usage': 0
        }

    # 1. Conteo de Tareas
    total_tasks = Task.query.filter_by(project_id=project_id).count()
    completed_tasks = Task.query.filter_by(project_id=project_id, status='COMPLETED').count()
    
    # 2. Cálculo de Horas (Sumar TimeEntries vinculados a las tareas del proyecto)
    total_hours = db.session.query(func.sum(TimeEntry.hours))\
        .join(Task)\
        .filter(Task.project_id == project_id)\
        .scalar() or 0

    # 3. Uso del Presupuesto
    budget_usage = 0
    if project.budget_hours and project.budget_hours > 0:
        budget_usage = (total_hours / project.budget_hours) * 100

    return {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'total_hours': total_hours,
        'budget_usage': min(budget_usage, 100) # Tope visual del 100%
    }