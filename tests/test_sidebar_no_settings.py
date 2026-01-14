def test_sidebar_no_settings_link_for_client_and_internal(client, db, create_user, login):
    # client
    c = create_user(email='csidebar@example.com', is_internal=False)
    login(c)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert '/settings' not in html
    assert 'Configuración' not in html

    # internal
    i = create_user(email='isidebar@example.com', is_internal=True)
    login(i)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert '/settings' not in html
    assert 'Configuración' not in html