from run import app
from app import db
from app.models import User, Project, Task, TimeEntry, Role
from datetime import datetime, timedelta
import random

with app.app_context():
    print('Running augment_seed (non-destructive)...')

    # Ensure roles exist
    for rname in ['Participante', 'PMP', 'Cliente']:
        if not Role.query.filter_by(name=rname).first():
            db.session.add(Role(name=rname))
    db.session.commit()

    # Add extra internal users if fewer than 8
    internal_count = User.query.filter_by(is_internal=True).count()
    if internal_count < 8:
        extras = [
            ('marco@bridgework.com', 'Marco', 'Polo'),
            ('lucia@bridgework.com', 'Lucía', 'Fernández'),
            ('sofia@bridgework.com', 'Sofía', 'Martínez'),
            ('pablo@bridgework.com', 'Pablo', 'López')
        ]
        for email, first, last in extras:
            if not User.query.filter_by(email=email).first():
                u = User(email=email, first_name=first, last_name=last, is_internal=True)
                u.set_password('password')
                u.role = Role.query.filter_by(name='Participante').first()
                db.session.add(u)
        db.session.commit()
        print('Added extra internal users')
    else:
        print('Sufficient internal users present')

    # Add extra client users if fewer than 4
    client_count = User.query.filter_by(is_internal=False).count()
    if client_count < 4:
        clients = [
            ('acme@example.com', 'ACME', 'Corp'),
            ('globex@example.com', 'Globex', 'Inc')
        ]
        for email, first, last in clients:
            if not User.query.filter_by(email=email).first():
                u = User(email=email, first_name=first, last_name=last, is_internal=False)
                u.set_password('client123')
                u.role = Role.query.filter_by(name='Cliente').first()
                db.session.add(u)
        db.session.commit()
        print('Added extra clients')
    else:
        print('Sufficient clients present')

    # Add sample projects if fewer than 6
    project_count = Project.query.count()
    if project_count < 6:
        internal_users = User.query.filter_by(is_internal=True).all()
        clients = User.query.filter_by(is_internal=False).all()
        sample_projects = [
            ('Portal Marketing', 'Campaña de marketing y landing pages', 80, 'ACTIVE'),
            ('Integración CRM', 'Conectar CRM con sistema interno', 120, 'IN_PROGRESS')
        ]
        for name, desc, budget, status in sample_projects:
            if not Project.query.filter_by(name=name).first():
                p = Project(name=name, description=desc, budget_hours=budget, status=status, start_date=datetime.now().date())
                # assign manager randomly
                if internal_users:
                    p.manager_id = random.choice(internal_users).id
                # assign a client if available
                if clients:
                    p.client_id = random.choice(clients).id
                db.session.add(p)
        db.session.commit()
        print('Added extra projects')
    else:
        print('Sufficient projects present')

    # Add some tasks for new projects
    new_projects = Project.query.filter(Project.name.in_(['Portal Marketing', 'Integración CRM'])).all()
    internal_users = User.query.filter_by(is_internal=True).all()
    for p in new_projects:
        existing_tasks = Task.query.filter_by(project_id=p.id).count()
        if existing_tasks < 3:
            for i in range(3):
                t = Task(
                    project_id=p.id,
                    title=f'Init task {i+1} for {p.name}',
                    assigned_to_id=random.choice(internal_users).id if internal_users else None,
                    status=random.choice(['BACKLOG','IN_PROGRESS','IN_REVIEW']),
                    due_date=datetime.now().date() + timedelta(days=random.randint(3, 30))
                )
                db.session.add(t)
    db.session.commit()
    print('Added tasks for new projects')

    # Add a few random time entries
    for t in Task.query.limit(10).all():
        if TimeEntry.query.filter_by(task_id=t.id).count() == 0:
            entry = TimeEntry(user_id=t.assigned_to_id or User.query.filter_by(is_internal=True).first().id,
                              task_id=t.id,
                              hours=round(random.uniform(0.5, 6.0),1),
                              date=datetime.now().date() - timedelta(days=random.randint(0,10))
                              description='Trabajo inicial')
            db.session.add(entry)
    db.session.commit()
    print('Augmentation complete')