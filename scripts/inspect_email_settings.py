import sys
sys.path.insert(0, r'c:\Users\david\Proyectos\BridgeWork-Recuperar')
from app import create_app
app = create_app()
with app.app_context():
    from app.models import SystemSettings
    keys = ['smtp_host','smtp_port','smtp_username','smtp_password','smtp_use_tls','email_from','notify_task_assigned']
    for k in keys:
        print(k, '=>', SystemSettings.get(k))
