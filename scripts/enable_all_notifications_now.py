import sys
import os
# Ensure project root is on PYTHONPATH when running as a script
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root not in sys.path:
    sys.path.insert(0, root)

from app import create_app
from app import db
from app.models import SystemSettings

app = create_app()
with app.app_context():
    keys = [
        'notify_task_assigned', 'notify_task_completed', 'notify_task_approved',
        'notify_task_rejected', 'notify_task_comment', 'notify_due_date_reminder',
        'show_notification_center', 'enable_push_notifications'
    ]
    for k in keys:
        SystemSettings.set(k, 'true', category='notifications', value_type='boolean', user_id=None)
    db.session.commit()

    # Print current values
    results = {k: SystemSettings.get(k) for k in keys}
    print('Enabled notification keys:')
    for k, v in results.items():
        print(f' - {k}: {v} ({type(v).__name__})')
