import os, sys, secrets
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app, db
from app.models import Role, User

app = create_app()
with app.app_context():
    roles_needed = ['Admin', 'PMP', 'Participante', 'Cliente']
    created = []
    for rname in roles_needed:
        r = Role.query.filter_by(name=rname).first()
        if not r:
            r = Role(name=rname)
            db.session.add(r)
            created.append(rname)
    db.session.commit()

    # Admin user defaults
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@bridgework.com')
    admin_password = os.environ.get('ADMIN_PASSWORD') or secrets.token_urlsafe(12)

    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(email=admin_email, first_name='Admin', last_name='System', is_internal=True, is_active=True)
        admin.set_password(admin_password)
        admin_role = Role.query.filter_by(name='Admin').first()
        admin.role = admin_role
        db.session.add(admin)
        db.session.commit()
        created_user = True
    else:
        # ensure admin has Admin role and active
        admin_role = Role.query.filter_by(name='Admin').first()
        admin.role = admin_role
        admin.is_active = True
        # update password if env variable provided
        if os.environ.get('ADMIN_PASSWORD'):
            admin.set_password(os.environ.get('ADMIN_PASSWORD'))
        db.session.commit()
        created_user = False

    print('\nRoles created:', ', '.join(created) if created else 'None')
    print(f"Admin user: {admin.email} (created={created_user})")
    if os.environ.get('ADMIN_PASSWORD'):
        print('Admin password set from environment variable.')
    else:
        print(f"Temporary admin password: {admin_password}")
    print('\nIMPORTANT: Change the password after login and remove temporary credentials from env.')
