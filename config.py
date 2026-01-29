import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File uploads config
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE', 16 * 1024 * 1024))  # 16MB default
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', 'csv'}

    # Alert monitoring defaults
    ALERT_MONITOR_FAILURE_THRESHOLD = int(os.environ.get('ALERT_MONITOR_FAILURE_THRESHOLD', '5'))
    ALERT_MONITOR_WINDOW_HOURS = int(os.environ.get('ALERT_MONITOR_WINDOW_HOURS', '1'))

    # Azure / MSAL settings - ASEGÚRATE QUE ESTÉN CONFIGURADAS
    AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
    AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
    AZURE_AUTHORITY = os.environ.get('AZURE_AUTHORITY', 'https://login.microsoftonline.com/common')
    AZURE_SCOPES = ['User.Read']  # Scopes needed


class DevConfig(Config):
    # Default to sqlite for local dev convenience; override with DATABASE_URL env var if needed
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')
    DEBUG = True

    # Celery / Redis defaults for local development
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
    # A simple daily job example (can be tuned)
    CELERY_BEAT_SCHEDULE = {
        'daily-generate-alerts': {
            'task': 'alerts.generate_alerts',
            'schedule': 86400.0,  # seconds (daily)
            'args': (2,),
        },
        'monitor-failed-alerts': {
            'task': 'alerts.check_failed_alerts',
            'schedule': 600.0,  # seconds (10 minutes)
            'args': (),
        },
        'weekly-cleanup-audit-logs': {
            'task': 'alerts.cleanup_audit_logs',
            'schedule': 604800.0,  # seconds (weekly - 7 days)
            'args': (),
        },
    }

    # Notification provider config (optional)
    EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'stub')  # 'stub' or 'sendgrid'
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    EMAIL_FROM = os.environ.get('EMAIL_FROM', 'noreply@example.com')


class ProdConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    DEBUG = False
