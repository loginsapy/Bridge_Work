from celery import Celery


def make_celery(app):
    """Create and configure a Celery object using Flask app config."""
    broker = app.config.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    backend = app.config.get('CELERY_RESULT_BACKEND', broker)
    celery = Celery(app.import_name, broker=broker, backend=backend)
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            # Ensure tasks run with Flask app context
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
