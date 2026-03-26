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


def test_admin_settings_branding_reset_theme(client, db, create_user, login):
    from app.models import Role, SystemSettings

    role = Role.query.filter_by(name='Admin').first()
    if not role:
        role = Role(name='Admin')
        db.session.add(role)
        db.session.commit()

    admin = create_user(email='admin_reset_theme@example.com', is_internal=True)
    admin.role = role
    db.session.commit()

    # Set custom colors
    db.session.add(SystemSettings(key='primary_color', value='#112233', category='branding', value_type='string'))
    db.session.add(SystemSettings(key='secondary_color', value='#445566', category='branding', value_type='string'))
    db.session.add(SystemSettings(key='accent_color', value='#778899', category='branding', value_type='string'))
    db.session.commit()

    login(admin)

    rv = client.post('/admin/settings', data={'section': 'branding', 'reset_theme': '1'}, follow_redirects=True)
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Colores del tema restablecidos a los valores predeterminados.' in html

    assert SystemSettings.query.filter_by(key='primary_color').first() is None
    assert SystemSettings.query.filter_by(key='secondary_color').first() is None
    assert SystemSettings.query.filter_by(key='accent_color').first() is None
    assert SystemSettings.query.filter_by(key='sidebar_color').first() is None

    # Comprobar que la carga al renderizar vuelve a defaults del código
    assert SystemSettings.get('primary_color', '#E86A33') == '#E86A33'
    assert SystemSettings.get('secondary_color', '#6c757d') == '#6c757d'
    assert SystemSettings.get('accent_color', '#00c875') == '#00c875'
    assert SystemSettings.get('sidebar_color', '#1a1d29') == '#1a1d29'
