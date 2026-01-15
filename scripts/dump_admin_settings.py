from app import create_app
from app.main.routes import admin_settings_page
app = create_app()
with app.app_context():
    resp = admin_settings_page()
    # The view returns a Response/Markup; but we can also reconstruct settings by calling the logic
    from app.models import SystemSettings
    all_settings = SystemSettings.query.all()
    settings = {s.key: s.value for s in all_settings}
    defaults = {
        'notify_task_assigned': 'true',
        'notify_task_completed': 'true',
        'notify_task_approved': 'true',
        'notify_task_rejected': 'true',
        'notify_task_comment': 'true',
        'notify_due_date_reminder': 'true',
        'show_notification_center': 'true'
    }
    for k, v in defaults.items():
        settings.setdefault(k, v)
    # Normalize
    notify_keys = [
        'notify_task_assigned', 'notify_task_completed', 'notify_task_approved',
        'notify_task_rejected', 'notify_task_comment', 'notify_due_date_reminder',
        'show_notification_center', 'enable_push_notifications'
    ]
    for k in notify_keys:
        raw = settings.get(k, defaults.get(k, 'true'))
        if isinstance(raw, str):
            settings[k] = raw.lower() not in ('false', '0', 'no')
        else:
            settings[k] = bool(raw)
    print(settings)
    
    # Also print types
    for k in notify_keys:
        print(k, settings.get(k), type(settings.get(k)))
