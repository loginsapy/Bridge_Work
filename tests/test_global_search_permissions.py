def test_global_search_requires_role(client, db, create_user, login):
    # User with no role
    u = create_user(email='norole_search@example.com', is_internal=True)
    u.role = None
    from app import db as _db
    _db.session.commit()

    login(u)
    rv = client.get('/search?q=proj')
    assert rv.status_code == 403
    data = rv.get_json()
    assert 'No tienes permisos' in data['error']


def test_global_search_allowed_for_participant(client, db, create_user, login):
    from app.models import Role, Project
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='part_search@example.com', is_internal=True)
    participant.role = role
    db.session.commit()

    # Create a project and a task to find
    p = Project(name='SearchProject')
    from app import db as _db
    _db.session.add(p); _db.session.commit()

    login(participant)
    rv = client.get('/search?q=Search')
    assert rv.status_code == 200
    data = rv.get_json()
    assert 'projects' in data
