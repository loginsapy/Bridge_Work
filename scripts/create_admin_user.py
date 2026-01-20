from app import create_app, db
from app.models import User, Role

app = create_app()

with app.app_context():
    admin_email = 'admin@bridgework.com'
    admin_password = 'admin123'

    existing = User.query.filter_by(email=admin_email).first()
    if existing:
        print(f"User {admin_email} already exists with id {existing.id}")
    else:
        # ensure role exists
        role = Role.query.filter_by(name='Admin').first()
        if not role:
            role = Role(name='Admin')
            db.session.add(role)
            db.session.flush()

        user = User(email=admin_email, first_name='Admin', last_name='BridgeWork', is_internal=True, is_active=True, role_id=role.id)
        user.set_password(admin_password)
        db.session.add(user)
        db.session.commit()
        print(f"Created user {admin_email} with id {user.id}")

    # Confirm dev user exists
    dev = User.query.filter_by(email='dev@example.com').first()
    if dev:
        print(f"dev@example.com exists (id={dev.id}). Password set during seeding: 'password'")
    else:
        print('dev@example.com not found')
