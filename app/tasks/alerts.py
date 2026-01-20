from datetime import date, datetime, timedelta
from .. import db
from ..models import Task, AlertLog


def generate_alerts(cutoff_days=None, idempotency_hours=24):
    """Generate AlertLog entries for tasks due within `cutoff_days` and not completed.

    - Reads system settings to determine whether due-date reminders are enabled
      and what the configured cutoff in days is if **cutoff_days** is None.
    - Avoid creating duplicate AlertLog entries for the same task within `idempotency_hours`.
    - Return a dict with created AlertLog objects and grouping by recipient_id.

    This is pure-Python and can be called from tests directly. The Celery task
    below simply wraps this function for scheduled execution.
    """
    from ..models import SystemSettings

    # Check global switch -> coerce strings like 'false'/'true' to booleans
    enabled = SystemSettings.get('notify_due_date_reminder', True)
    if isinstance(enabled, str):
        enabled = enabled.lower() not in ('false', '0', 'no')
    else:
        enabled = bool(enabled)

    if not enabled:
        return {"created": [], "groups": {}}

    # Determine cutoff from settings if not provided
    if cutoff_days is None:
        try:
            cutoff_days = int(SystemSettings.get('due_date_reminder_days', 2))
        except Exception:
            cutoff_days = 2

    today = date.today()
    cutoff = today + timedelta(days=int(cutoff_days))
    now = datetime.now()
    idempotency_delta = timedelta(hours=idempotency_hours)

    # Tasks with due_date not null, due_date <= cutoff, and not completed
    tasks = (
        Task.query
        .filter(Task.due_date != None)
        .filter(Task.due_date <= cutoff)
        .filter(Task.status != 'COMPLETED')
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

    # Persist last run metadata to SystemSettings for admin visibility
    try:
        from ..models import SystemSettings
        SystemSettings.set('last_due_reminder_run', datetime.utcnow().isoformat(), category='notifications', value_type='string')
        SystemSettings.set('last_due_reminder_created', str(len(created)), category='notifications', value_type='number')
        db.session.commit()
    except Exception:
        # If persisting metadata fails, ignore to not break alerts generation
        db.session.rollback()

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


def cleanup_old_audit_logs():
    """Elimina registros de auditoría con más de 6 meses de antigüedad.
    
    Esta función se ejecuta periódicamente para mantener la base de datos limpia.
    Los registros de auditoría se conservan por 6 meses (180 días).
    """
    from ..models import AuditLog
    
    cutoff_date = datetime.now() - timedelta(days=180)
    
    try:
        deleted_count = AuditLog.query.filter(AuditLog.created_at < cutoff_date).delete()
        if deleted_count > 0:
            db.session.commit()
            return {"deleted": deleted_count, "cutoff_date": cutoff_date.isoformat()}
        return {"deleted": 0, "cutoff_date": cutoff_date.isoformat()}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


# Celery task wrapper (import lazily to avoid circular imports during app startup)

try:
    # Celery app will be attached at runtime (from run.celery)
    from run import celery

    @celery.task(name='alerts.generate_alerts')
    def celery_generate_alerts(cutoff_days=2, idempotency_hours=24):
        return generate_alerts(cutoff_days=cutoff_days, idempotency_hours=idempotency_hours)
    
    @celery.task(name='alerts.cleanup_audit_logs')
    def celery_cleanup_audit_logs():
        """Tarea Celery para limpiar registros de auditoría antiguos"""
        return cleanup_old_audit_logs()
        
except Exception:
    # Running in contexts without Celery available (tests, import-time) is fine
    celery_generate_alerts = None
    celery_cleanup_audit_logs = None
