from dataclasses import dataclass
from typing import Optional

from . import db
from .models import Project, Task, TimeEntry
from sqlalchemy import func

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, Counter


class Metrics:
    def __init__(self, app):
        self.app = app
        self.registry = CollectorRegistry()

        # Define metrics
        self.tasks_total = Gauge(
            'app_tasks_total', 'Total number of tasks',
            registry=self.registry
        )
        self.tasks_completed = Gauge(
            'app_tasks_completed', 'Total number of completed tasks',
            registry=self.registry
        )
        self.hours_spent_total = Gauge(
            'app_hours_spent_total', 'Total hours spent across all projects',
            registry=self.registry
        )
        # Alerts sent counter
        self.alerts_sent = Counter('alerts_sent_total', 'Total number of alerts sent', registry=self.registry)
        # Add more gauges/counters as needed

    def registry_metrics(self):
        return generate_latest(self.registry)

    def content_type(self):
        return CONTENT_TYPE_LATEST


@dataclass
class ProjectMetrics:
    """Dataclass to hold project metrics."""
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    total_hours_spent: float
    budget_usage_percent: Optional[float]


def calculate_project_metrics(project_id: int) -> Optional[ProjectMetrics]:
    """Calculate and return metrics for a given project."""
    project = Project.query.get(project_id)
    if not project:
        return None

    # Task metrics
    tasks = Task.query.filter_by(project_id=project.id).all()
    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.status == 'COMPLETED'])
    completion_rate = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0

    # Time and budget metrics
    total_hours_spent = db.session.query(func.sum(TimeEntry.hours)).join(Task).filter(Task.project_id == project.id).scalar() or 0
    
    budget_usage_percent: Optional[float] = None
    if project.budget_hours and project.budget_hours > 0:
        budget_usage_percent = (total_hours_spent / project.budget_hours) * 100

    return ProjectMetrics(
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        completion_rate=completion_rate,
        total_hours_spent=float(total_hours_spent),
        budget_usage_percent=float(budget_usage_percent) if budget_usage_percent is not None else None,
    )
