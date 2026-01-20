"""Idempotent script to ensure critical application data exists.

Safety: This script *does not* drop or truncate tables. It inserts missing roles, a temporary admin user
(if missing), default system settings, a sample project, and a sample client + example task.

If the configured DB is remote (not sqlite/localhost), set CONFIRM_RESEED_REMOTE=YES to allow running.
"""
import os
import secrets
from getpass import getpass

from app import create_app, db
from app.models import Role, User, Project, Task, SystemSettings
from app.utils.safety import is_safe_db_uri


def main():
    # Determine DB URI
    from flask import current_app
    app = create_app()
    uri = None
    with app.app_context():
        uri = app.config.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL') or ''

    if not is_safe_db_uri(uri) and os.environ.get('CONFIRM_RESEED_REMOTE') != 'YES':
        print("Refusing to reseed on remote DB. To proceed set CONFIRM_RESEED_REMOTE=YES and re-run.")
        return 1

    with app.app_context():
        created = {
            'roles': [],
            'admin_created': False,
            'client_created': False,
            'project_created': False,
            'task_created': False,
            'settings_set': []
        }

        # Roles
        roles = ['Admin', 'PMP', 'Participante', 'Cliente']
        for r in roles:
            existing = Role.query.filter_by(name=r).first()
            if not existing:
                Role_r = Role(name=r)
                db.session.add(Role_r)
                created['roles'].append(r)
        db.session.commit()

        # System Settings (safe defaults)
        defaults = {
            'app_name': 'BridgeWork',
            'primary_color': '#0d6efd',
            'date_format': 'DD/MM/YYYY',
            'language': 'es',
        }
        for k, v in defaults.items():
            s = SystemSettings.get(k)
            if s is None:
                SystemSettings.set(k, v)
                created['settings_set'].append(k)

        # Admin user
        admin_email = 'admin@bridgework.com'
        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            temp_pw = secrets.token_urlsafe(12)
            admin = User(email=admin_email, first_name='Admin', last_name='System', is_internal=True)
            admin.set_password(temp_pw)
            admin_role = Role.query.filter_by(name='Admin').first()
            if admin_role:
                admin.role = admin_role
            db.session.add(admin)
            db.session.commit()
            created['admin_created'] = True
        else:
            temp_pw = None

        # Sample client user
        client_email = 'client@example.com'
        client = User.query.filter_by(email=client_email).first()
        if not client:
            client_pw = secrets.token_urlsafe(10)
            client = User(email=client_email, first_name='Cliente', last_name='Demo', is_internal=False)
            client.set_password(client_pw)
            client_role = Role.query.filter_by(name='Cliente').first()
            if client_role:
                client.role = client_role
            db.session.add(client)
            db.session.commit()
            created['client_created'] = True
        else:
            client_pw = None

        # Sample project
        proj_name = 'Primer Proyecto'  # idempotent by name
        project = Project.query.filter_by(name=proj_name).first()
        if not project:
            project = Project(name=proj_name, description='Proyecto creado automáticamente para desarrollo', start_date=None, budget_hours=0)
            db.session.add(project)
            db.session.commit()
            created['project_created'] = True

        # Ensure client is attached to project clients association
        if client not in project.clients:
            project.clients.append(client)
            db.session.commit()

        # Sample task assigned to admin and client
        t_title = 'Tarea de Ejemplo'  # idempotent by title and project
        task = Task.query.filter_by(title=t_title, project_id=project.id).first()
        if not task:
            task = Task(project_id=project.id, title=t_title, description='Tarea creada automáticamente para desarrollo', status='BACKLOG')
            task.assigned_to_id = admin.id
            task.assigned_client_id = client.id
            db.session.add(task)
            db.session.commit()
            created['task_created'] = True

        # Print summary
        print('Reseed summary:')
        if created['roles']:
            print('  Roles created:', ', '.join(created['roles']))
        if created['settings_set']:
            print('  System settings set:', ', '.join(created['settings_set']))
        if created['admin_created']:
            print('  Admin user created:', admin_email)
            print('    Temporary password:', temp_pw)
        else:
            print('  Admin user already existed:', admin_email)
        if created['client_created']:
            print('  Client user created:', client_email)
            print('    Password:', client_pw)
        else:
            print('  Client user already existed:', client_email)
        if created['project_created']:
            print('  Project created:', proj_name)
        else:
            print('  Project already existed:', proj_name)
        if created['task_created']:
            print('  Example task created:', t_title)
        else:
            print('  Example task already existed:', t_title)

    return 0


if __name__ == '__main__':
    exit(main())