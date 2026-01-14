from app import create_app, db
from app.models import User, Project, Task
app = create_app()
with app.app_context():
    u = User(email='cli2@example.com', is_internal=True)
    db.session.add(u); db.session.commit()
    p = Project(name='Ptest2')
    db.session.add(p); db.session.commit()
    t1 = Task(project_id=p.id, title='A'); db.session.add(t1)
    t2 = Task(project_id=p.id, title='B'); db.session.add(t2)
    t3 = Task(project_id=p.id, title='C'); db.session.add(t3)
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh']=True
    rv = client.post(f"/project/{p.id}/tasks/reorder", json={'ordered_task_ids':[t3.id, t1.id, t2.id]})
    print('status', rv.status_code, rv.get_json())
    print('positions:', [(Task.query.get(x.id).id, Task.query.get(x.id).position) for x in [t1,t2,t3]])
