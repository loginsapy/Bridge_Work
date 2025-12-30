from flask import current_app


def check_failed_alerts(threshold: int = None, window_hours: int = None):
    """Check recent AlertLog failures and notify internal admins if threshold exceeded.

    Returns: dict with {'failures': count, 'notified': [user_ids]}
    """
    app = current_app._get_current_object()
    from datetime import datetime, timedelta

    from ..models import AlertLog, User
    # Resolve config defaults
    threshold = threshold or app.config.get('ALERT_MONITOR_FAILURE_THRESHOLD', 5)
    window_hours = window_hours or app.config.get('ALERT_MONITOR_WINDOW_HOURS', 1)

    now = datetime.now()
    since = now - timedelta(hours=window_hours)

    failures = (
        AlertLog.query
        .filter(AlertLog.status == 'FAILED')
        .filter(AlertLog.created_at >= since)
        .all()
    )

    notified = []
    if len(failures) >= threshold:
        # Gather admin/internal users
        admins = User.query.filter(User.is_internal == True).all()
        from app.notifications.provider import get_provider

        provider = get_provider(app)
        subject = f"Alert send failures detected: {len(failures)} failures in last {window_hours}h"
        sample_tasks = [f.task_id for f in failures[:10]]
        text = f"There have been {len(failures)} failed alert sends in the last {window_hours} hours. Sample task ids: {sample_tasks}"

        for a in admins:
            try:
                ok = provider.send_email(a.id, subject, text)
                if ok:
                    notified.append(a.id)
            except Exception:
                app.logger.exception('Failed to notify admin %s', a.email)

    return {'failures': len(failures), 'notified': notified}


# Celery wrapper
try:
    from run import celery

    @celery.task(name='alerts.check_failed_alerts')
    def celery_check_failed_alerts(threshold=None, window_hours=None):
        return check_failed_alerts(threshold=threshold, window_hours=window_hours)
except Exception:
    celery_check_failed_alerts = None
