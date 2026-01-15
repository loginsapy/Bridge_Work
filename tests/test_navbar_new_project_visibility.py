def test_admin_and_pmp_see_new_project_button(client, db, create_user, login):
    from app.models import Role
    # Ensure roles exist
    admin_role = Role.query.filter_by(name='Admin').first()
    if not admin_role:
        admin_role = Role(name='Admin')
        db.session.add(admin_role)
    pmp_role = Role.query.filter_by(name='PMP').first()
    if not pmp_role:
        pmp_role = Role(name='PMP')
        db.session.add(pmp_role)
    db.session.commit()

    # Admin user
    admin = create_user(email='admin_nav@example.com', is_internal=True)
    admin.role = admin_role
    db.session.commit()
    login(admin)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' in html

    # PMP user
    pmp = create_user(email='pmp_nav@example.com', is_internal=True)
    pmp.role = pmp_role
    db.session.commit()
    login(pmp)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' in html


def test_non_admin_roles_do_not_see_new_project(client, db, create_user, login):
    # Client user
    client_user = create_user(email='client_nav@example.com', is_internal=False)
    login(client_user)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' not in html

    # Participant role
    from app.models import Role
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        db.session.add(role)
        db.session.commit()

    participant = create_user(email='participant_nav@example.com', is_internal=True)
    participant.role = role
    db.session.commit()
    login(participant)
    rv = client.get('/')
    html = rv.get_data(as_text=True)
    assert 'Nuevo Proyecto' not in html