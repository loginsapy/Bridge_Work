from app import create_app
app = create_app()
from app.models import AuditLog
import json

with app.app_context():
    rows = AuditLog.query.filter(AuditLog.entity_type=='Project', AuditLog.entity_id==111).order_by(AuditLog.created_at.desc()).limit(5).all()
    if not rows:
        print('NO_RECORDS')
    else:
        for r in rows:
            changes = json.dumps(r.changes) if r.changes else 'null'
            print(f"id={r.id} action={r.action} user_id={r.user_id} at={r.created_at} changes={changes}")
