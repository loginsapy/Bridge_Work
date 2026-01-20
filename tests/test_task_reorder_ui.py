def test_participant_sees_disabled_grip_in_board(client, db, create_project, create_task, create_user, login):
    # Create role 'Participante'
    from app.models import Role
    role = Role(name='Participante')
    db.session.add(role)
    db.session.commit()

    # Create an internal user but with role 'Participante'
    u = create_user(email='participant_ui@example.com', is_internal=True)
    u.role = role
    db.session.commit()

    login(u)
    p = create_project(name='P-ui-board')
    t1 = create_task(project_id=p['id'], title='UT1', assigned_to_id=u.id)

    rv = client.get(f"/project/{p['id']}")
    assert rv.status_code == 200
    # The disabled grip should appear for participants
    assert b'disabled-grip' in rv.data
    assert b'Solo Admin/PMP pueden reordenar' in rv.data