def test_sidebar_no_settings_link_for_client_and_internal(client, db, create_user, login):
    # client
    c = create_user(email='csidebar@example.com', is_internal=False)
    login(c)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert '/settings' not in html
    assert 'Configuración' not in html

    # internal (non-admin)
    i = create_user(email='isidebar@example.com', is_internal=True)
    login(i)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert '/settings' not in html
    assert 'Configuración' not in html

    # admin (should see 'Configuración' menu)
    from app.models import Role
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()

    admin = create_user(email='admin_sidebar@example.com', is_internal=True)
    admin.role = role
    db.session.commit()

    login(admin)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Configuración' in html
    assert 'Administración' not in html