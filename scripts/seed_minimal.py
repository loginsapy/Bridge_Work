"""Insert minimal sample data to test parent/child and predecessor behavior.
Creates:
 - 1 internal user
 - 1 project
 - 3 tasks: parent, child (parent_task_id -> parent), predecessor (predecessor -> child)
"""
from app import create_app, db
from app.models import User, Project, Task

app = create_app()

with app.app_context():
    # Create an internal user
    u = User(email='dev@example.com', first_name='Dev', last_name='User', is_internal=True)
    u.set_password('password')
    db.session.add(u)
    db.session.flush()

    # Create project
    p = Project(name='Seed Project', description='Minimal seed project')
    db.session.add(p)
    db.session.flush()

    # Parent task
    parent = Task(project_id=p.id, title='Parent Task', description='Parent for child')
    db.session.add(parent)
    db.session.flush()

    # Child task (hierarchical)
    child = Task(project_id=p.id, title='Child Task', description='Child of parent', parent_task_id=parent.id)
    db.session.add(child)
    db.session.flush()

    # Predecessor task (separate task that will be a predecessor of child)
    pred = Task(project_id=p.id, title='Predecessor Task', description='Predecessor of child')
    db.session.add(pred)
    db.session.flush()

    # Link predecessor -> child (child has predecessor pred)
    child.predecessors.append(pred)

    db.session.commit()

    print('Seed complete:')
    print('User:', u.id, u.email)
    print('Project:', p.id, p.name)
    print('Tasks:')
    for t in [parent, child, pred]:
        print(f" - {t.id}: {t.title} (parent={t.parent_task_id}, predecessors={[x.id for x in t.predecessors]})")
