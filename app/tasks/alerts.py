from datetime import date, datetime, timedelta
from .. import db
from ..models import Task, AlertLog


def generate_alerts(cutoff_days=2, idempotency_hours=24):
    """Generate AlertLog entries for tasks due within `cutoff_days` and not completed.

    - Avoid creating duplicate AlertLog entries for the same task within `idempotency_hours`.
    - Return a dict with created AlertLog objects and grouping by recipient_id.

    This is pure-Python and can be called from tests directly. The Celery task
    below simply wraps this function for scheduled execution.
    """
    today = date.today()
    cutoff = today + timedelta(days=cutoff_days)
    now = datetime.now()
    idempotency_delta = timedelta(hours=idempotency_hours)

    # Tasks with due_date not null, due_date <= cutoff, and not completed
    tasks = (
        Task.query
        .filter(Task.due_date != None)
        .filter(Task.due_date <= cutoff)
        .filter(Task.status.notin_(['DONE', 'COMPLETED']))
        .all()
    )

    created = []
    groups = {}

    for t in tasks:
        if not t.assigned_to_id:
            # Skip tasks without an assignee
            continue

        # Check for recent alerts for this task (idempotency window)
        recent = (
            AlertLog.query
            .filter(AlertLog.task_id == t.id)
            .filter(AlertLog.created_at != None)
            .filter(AlertLog.created_at >= (now - idempotency_delta))
            .first()
        )
        if recent:
            # already alerted recently
            continue

        al = AlertLog(task_id=t.id, recipient_id=t.assigned_to_id, status='CREATED', created_at=now)
        db.session.add(al)
        created.append(al)
        groups.setdefault(al.recipient_id, []).append(t.id)

    if created:
        db.session.commit()

    # Return created items and groups mapping
    result = {"created": created, "groups": groups}

    # If Celery is available, dispatch sending as a separate task
    try:
        from .sender import celery_send_grouped_alerts
        if celery_send_grouped_alerts:
            # pass only the groups mapping (simple serializable dict)
            celery_send_grouped_alerts.delay(groups)
    except Exception:
        # Not running under Celery / or import failed; ignore for now
        pass

    return result


# Celery task wrapper (import lazily to avoid circular imports during app startup)

try:
    # Celery app will be attached at runtime (from run.celery)
    from run import celery

    @celery.task(name='alerts.generate_alerts')
    def celery_generate_alerts(cutoff_days=2, idempotency_hours=24):
        return generate_alerts(cutoff_days=cutoff_days, idempotency_hours=idempotency_hours)
except Exception:
    # Running in contexts without Celery available (tests, import-time) is fine
    celery_generate_alerts = None
