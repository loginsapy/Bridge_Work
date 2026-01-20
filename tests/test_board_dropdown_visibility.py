def test_participant_does_not_see_person_dropdown(client, db, create_project, create_task, create_user, login):
    # Setup project and a task
    p = create_project(name='P V')
    t = create_task(p['id'], title='Visible Task')

    # Create participant user and assign role 'Participante'
    from app.models import Role
    participant = create_user(email='pvis@example.com', is_internal=True)
    part_role = Role(name='Participante')
    db.session.add(part_role)
    db.session.commit()
    participant.role = part_role
    db.session.commit()

    # Login as participant
    login(participant)

    rv = client.get(f"/project/{p['id']}/board")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Participant should NOT see the person dropdown element
    assert 'id="personDropdown"' not in html
    # Participant should not have onclick handler to open dropdown
    assert 'onclick="showPersonDropdown' not in html


def test_client_does_not_see_person_dropdown(client, db, create_project, create_task, create_user, login):
    # Setup project and a task
    p = create_project(name='P C')
    t = create_task(p['id'], title='Client Task')

    # Create a client user (external)
    client_user = create_user(email='clientvis@example.com', is_internal=False)

    # Login as client
    login(client_user)

    rv = client.get(f"/project/{p['id']}/board")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)

    # Client should NOT see the person dropdown element
    assert 'id="personDropdown"' not in html
    # Client should not have onclick handler to open dropdown
    assert 'onclick="showPersonDropdown' not in html
