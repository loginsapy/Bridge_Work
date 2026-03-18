from celery import Celery
from celery.schedules import crontab


def make_celery(app):
    """Create and configure a Celery object using Flask app config."""
    broker = app.config.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    backend = app.config.get('CELERY_RESULT_BACKEND', broker)
    celery = Celery(app.import_name, broker=broker, backend=backend)
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Periodic schedule: run due-date reminders every day at 08:00 server time
    celery.conf.beat_schedule = {
        'due-date-reminders-daily': {
            'task': 'alerts.generate_alerts',
            'schedule': crontab(hour=8, minute=0),
        },
        'cleanup-audit-logs-weekly': {
            'task': 'alerts.cleanup_audit_logs',
            'schedule': crontab(hour=3, minute=0, day_of_week=1),  # Monday 03:00
        },
    }
    celery.conf.timezone = app.config.get('CELERY_TIMEZONE', 'America/Asuncion')

    return celery
