from typing import Dict, List
from time import sleep
from flask import current_app
from app import db


def send_grouped_alerts(groups: Dict[int, List[int]], retries: int = 3, backoff_factor: float = 0.5):
    """Send grouped alerts to recipients using provider.render_alert and provider.send_email.

    groups: {recipient_id: [task_id, ...]}
    Returns: {'success': [recipient_ids], 'failed': [recipient_ids]}
    """
    app = current_app._get_current_object()
    # Import provider getter at runtime so tests can monkeypatch module-level get_provider
    from app.notifications.provider import get_provider
    provider = get_provider(app)

    successes = []
    failures = []

    for recipient_id, task_ids in groups.items():
        # Render the message using the provider helper (which uses templates)
        try:
            subject, text, html = provider.render_alert(recipient_id, task_ids)
        except Exception:
            # Fallback rendering
            subject = f"{len(task_ids)} pending tasks due soon"
            text = f"You have {len(task_ids)} tasks due soon: {task_ids}"
            html = None

        attempt = 0
        while attempt < retries:
            attempt += 1
            try:
                ok = provider.send_email(recipient_id, subject, text, html=html)
                if ok:
                    successes.append(recipient_id)
                    # mark associated AlertLog entries as SENT
                    try:
                        from ..models import AlertLog
                        from datetime import datetime
                        for tid in task_ids:
                            al = (
                                AlertLog.query
                                .filter(AlertLog.task_id == tid)
                                .filter(AlertLog.recipient_id == recipient_id)
                                .filter(AlertLog.status == 'CREATED')
                                .first()
                            )
                            if al:
                                al.status = 'SENT'
                                al.sent_at = datetime.now()
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

                    # increment metrics
                    try:
                        app.metrics.inc_sent()
                    except Exception:
                        app.extensions.setdefault('metrics', {}).setdefault('alerts_sent', 0)
                        app.extensions['metrics']['alerts_sent'] += 1
                        # increment Prometheus counter if available
                        try:
                            current_app.metrics.alerts_sent.inc()
                        except Exception:
                            pass
                    break
                else:
                    current_app.logger.warning('Failed to send to %s (attempt %s)', recipient_id, attempt)
            except Exception as e:
                current_app.logger.exception('Exception sending to %s (attempt %s): %s', recipient_id, attempt, e)
            # backoff
            sleep(backoff_factor * (2 ** (attempt - 1)))
        else:
            failures.append(recipient_id)
            # mark associated AlertLog entries as FAILED
            try:
                from ..models import AlertLog
                from datetime import datetime
                for tid in task_ids:
                    al = (
                        AlertLog.query
                        .filter(AlertLog.task_id == tid)
                        .filter(AlertLog.recipient_id == recipient_id)
                        .filter(AlertLog.status == 'CREATED')
                        .first()
                    )
                    if al:
                        al.status = 'FAILED'
                        al.sent_at = datetime.now()
                db.session.commit()
            except Exception:
                db.session.rollback()

            try:
                app.metrics.inc_failed()
            except Exception:
                app.extensions.setdefault('metrics', {}).setdefault('alerts_failed', 0)
                app.extensions['metrics']['alerts_failed'] += 1

    return {'success': successes, 'failed': failures}

# Celery task wrapper if Celery is available
try:
    from run import celery

    @celery.task(name='alerts.send_grouped_alerts', autoretry_for=(RuntimeError,), retry_backoff=True, retry_kwargs={'max_retries': 5})
    def celery_send_grouped_alerts(groups, retries=3, backoff_factor=0.5):
        res = send_grouped_alerts(groups, retries=retries, backoff_factor=backoff_factor)
        if res['failed']:
            # Raise to trigger Celery autoretry
            raise RuntimeError(f"Failed to send to recipients: {res['failed']}")
        return res
except Exception:
    celery_send_grouped_alerts = None
