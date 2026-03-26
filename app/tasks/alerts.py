from datetime import date, datetime, timedelta
from .. import db
from ..models import Task, AlertLog


def generate_alerts(cutoff_days=None, idempotency_hours=24):
    """Send due-date reminder notifications for tasks due within `cutoff_days`.

    - Reads system settings for the enabled flag and cutoff days.
    - Uses an idempotency window (default 24 h) to avoid duplicate alerts.
    - Calls NotificationService.notify_task_due_soon() per task so the proper
      email template (task_due_soon.html) with a direct task URL is used.
    - Notifies the primary assignee AND any additional assignees.
    """
    from ..models import SystemSettings

    # Check global switch
    enabled = SystemSettings.get('notify_due_date_reminder', True)
    if isinstance(enabled, str):
        enabled = enabled.lower() not in ('false', '0', 'no')
    else:
        enabled = bool(enabled)

    if not enabled:
        return {"created": [], "groups": {}}

    if cutoff_days is None:
        try:
            cutoff_days = int(SystemSettings.get('due_date_reminder_days', 2))
        except Exception:
            cutoff_days = 2

    today = date.today()
    cutoff_dt = datetime.combine(today + timedelta(days=int(cutoff_days)), datetime.max.time())
    now = datetime.now()
    idempotency_delta = timedelta(hours=idempotency_hours)

    # Tasks with due_date not null, due within cutoff, and not completed/done/accepted
    terminal_statuses = ('COMPLETED', 'DONE', 'ACCEPTED')
    tasks = (
        Task.query
        .filter(Task.due_date != None)
        .filter(Task.due_date <= cutoff_dt)
        .filter(Task.status.notin_(terminal_statuses))
        .all()
    )

    created = []
    groups = {}

    try:
        from ..services.notifications import NotificationService
    except Exception:
        NotificationService = None

    for t in tasks:
        # Collect all recipients for this task
        recipients = set()
        if t.assigned_to_id:
            recipients.add(t.assigned_to_id)
        try:
            for u in t.assignees:
                if u.id:
                    recipients.add(u.id)
        except Exception:
            pass
        # Also notify PMP principal and PMP adicionales + Supervisores del proyecto
        try:
            if t.project and t.project.manager_id:
                recipients.add(t.project.manager_id)
            if t.project and getattr(t.project, 'members', None):
                for _m in t.project.members:
                    if getattr(_m, 'role', None) and _m.role.name in ('PMP', 'Supervisor'):
                        recipients.add(_m.id)
        except Exception:
            pass

        if not recipients:
            continue

        # Idempotency: skip if already alerted for this task within the window
        recent = (
            AlertLog.query
            .filter(AlertLog.task_id == t.id)
            .filter(AlertLog.created_at >= (now - idempotency_delta))
            .first()
        )
        if recent:
            continue

        due_date = t.due_date.date() if hasattr(t.due_date, 'date') else t.due_date
        days_until_due = (due_date - today).days

        for uid in recipients:
            al = AlertLog(task_id=t.id, recipient_id=uid, status='CREATED', created_at=now)
            db.session.add(al)
            created.append(al)
            groups.setdefault(uid, []).append(t.id)

            # Send notification via NotificationService (uses task_due_soon.html + task_url)
            if NotificationService:
                try:
                    from ..models import User, Project
                    project = Project.query.get(t.project_id) if t.project_id else None
                    if days_until_due <= 0:
                        title = "Tarea vencida"
                        message = f"La tarea '{t.title}' ya venció"
                    elif days_until_due == 1:
                        title = "Tarea vence mañana"
                        message = f"La tarea '{t.title}' vence mañana"
                    else:
                        title = f"Tarea vence en {days_until_due} días"
                        message = f"La tarea '{t.title}' vence en {days_until_due} días"

                    # Create in-app notification only; send_grouped_alerts handles email
                    NotificationService.notify(
                        user_id=uid,
                        title=title,
                        message=message,
                        notification_type=NotificationService.TASK_DUE_SOON,
                        related_entity_type='task',
                        related_entity_id=t.id,
                        send_email=False,
                        email_context={
                            'task': t,
                            'project': project,
                            'days_until_due': days_until_due,
                            'message': message,
                            'title': title,
                            'task_url': NotificationService._build_task_url(t),
                        }
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Failed to notify user %s for task %s', uid, t.id)
                    al.status = 'FAILED'

    if created:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Persist last run metadata
    try:
        SystemSettings.set('last_due_reminder_run', datetime.now().strftime('%d/%m/%Y %H:%M'), category='notifications', value_type='string')
        SystemSettings.set('last_due_reminder_created', str(len(created)), category='notifications', value_type='number')
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {"created": created, "groups": groups}


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
