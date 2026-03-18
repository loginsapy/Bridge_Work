from app.models import User, Role


def test_participant_does_not_see_budget_card(client, db, create_user, login):
    u = create_user(email='part_rv@example.com', is_internal=True)
    # create_user assigns PMP by default; override to Participante
    part_role = Role.query.filter_by(name='Participante').first()
    if not part_role:
        part_role = Role(name='Participante')
        db.session.add(part_role)
        db.session.commit()
    u.role = part_role
    db.session.commit()

    login(u)
    html = client.get('/').get_data(as_text=True)
    assert 'Presupuesto usado' not in html


def test_pmp_sees_budget_card(client, db, create_user, login):
    u = create_user(email='pmp_rv@example.com', is_internal=True)
    # create_user already assigns PMP role
    login(u)
    html = client.get('/').get_data(as_text=True)
    assert 'Presupuesto usado' in html


def test_participant_case_insensitive(client, db, create_user, login):
    part_role = Role.query.filter_by(name='participante').first()
    if not part_role:
        part_role = Role(name='participante')
        db.session.add(part_role)
        db.session.commit()

    u = create_user(email='part2_rv@example.com', is_internal=True)
    u.role = part_role
    db.session.commit()

    login(u)
    html = client.get('/').get_data(as_text=True)
    assert 'Presupuesto usado' not in html


def test_client_does_not_see_budget_card(client, db, create_user, login):
    u = create_user(email='client_rv@example.com', is_internal=False)
    login(u)
    html = client.get('/').get_data(as_text=True)
    assert 'Presupuesto usado' not in html


def test_team_cards_visibility_by_role(client, db, create_user, login):
    admin_role = Role.query.filter_by(name='Admin').first()
    if not admin_role:
        admin_role = Role(name='Admin')
        db.session.add(admin_role)
        db.session.commit()

    part_role = Role.query.filter_by(name='Participante').first()
    if not part_role:
        part_role = Role(name='Participante')
        db.session.add(part_role)
        db.session.commit()

    u_pmp = create_user(email='pmp2_rv@example.com', is_internal=True)

    u_admin = create_user(email='admin_rv@example.com', is_internal=True)
    u_admin.role = admin_role
    db.session.commit()

    u_part = create_user(email='part3_rv@example.com', is_internal=True)
    u_part.role = part_role
    db.session.commit()

    u_client = create_user(email='client2_rv@example.com', is_internal=False)

    for user, should_see in [(u_pmp, True), (u_admin, True), (u_part, False), (u_client, False)]:
        login(user)
        html = client.get('/').get_data(as_text=True)
        if should_see:
            assert 'Velocidad del Equipo' in html, f"{user.email} should see team cards"
            assert 'Equipo con Actividad Reciente' in html
        else:
            assert 'Velocidad del Equipo' not in html, f"{user.email} should NOT see team cards"
            assert 'Equipo con Actividad Reciente' not in html
