def test_non_pmp_cannot_access_admin(client, db, create_user, login):
    from app.models import Role
    # ensure a Cliente role exists
    r = Role.query.filter_by(name='Cliente').first()
    if not r:
        r = Role(name='Cliente')
        db.session.add(r)
        db.session.commit()

    user = create_user(email='c@example.com', is_internal=False)
    login(user)

    rv = client.get('/admin/users', follow_redirects=False)
    # should be forbidden for non-PMP
    assert rv.status_code == 403


def test_pmp_can_access_admin(client, db, create_user, login):
    from app.models import Role
    r = Role(name='PMP')
    db.session.add(r)
    db.session.commit()

    user = create_user(email='admin2@example.com', is_internal=True)
    # assign role via relationship to ensure it's available during request
    from app.models import User
    u = User.query.get(user.id)
    u.role = r
    u.role_id = r.id
    db.session.commit()

    login(u)
    # debug
    from app.models import Role, User
    print('DBG ROLES:', [r.name for r in Role.query.all()])
    u_ref = User.query.get(u.id)
    print('DBG USER:', u_ref.email, 'role_id=', u_ref.role_id, 'role=', (u_ref.role.name if u_ref.role else None), 'is_internal=', u_ref.is_internal)
    rv = client.get('/admin/users')
    # should be accessible by PMP
    assert rv.status_code == 200
    assert b'Usuarios' in rv.data