def test_admin_settings_shows_experimental_note(client, db, create_user, login):
    # Admin user
    from app.models import Role
    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()

    admin = create_user(email='admin_settings@example.com', is_internal=True)
    admin.role = role
    db.session.commit()

    login(admin)
    rv = client.get('/admin/settings')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Experimental' in html
    assert 'Nota:' in html
    assert 'Generar Recordatorios' in html