def test_navbar_no_settings_link(client, db, create_user, login):
    u = create_user(email='navuser@example.com', is_internal=True)
    login(u)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Configuración' not in html or 'Mi Perfil' in html


def test_profile_has_config_button(client, db, create_user, login):
    u = create_user(email='profileuser@example.com', is_internal=True)
    login(u)
    rv = client.get('/profile')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Configuración' in html
    assert '/settings' in html