def test_time_entries_shows_no_role_message(client, db, create_user, login):
    # Create internal user but remove role to simulate no-role
    u = create_user(email='norole_time@example.com', is_internal=True)
    # Force no role
    from app import db as _db
    u.role = None
    _db.session.commit()

    login(u)
    rv = client.get('/time')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'No tienes un rol asignado' in html
    assert 'Contacta al administrador' in html
