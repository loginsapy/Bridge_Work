from app.models import Project, Role, User


def test_add_members_to_project(client, db, create_user, login):
    admin = create_user(email='admin_pm@example.com', is_internal=True)
    u1 = create_user(email='u1_pm@example.com', is_internal=True)
    u2 = create_user(email='u2_pm@example.com', is_internal=True)

    login(admin)

    # Create a project
    p = Project(name='Test Project')
    db.session.add(p)
    db.session.commit()
    proj_id = p.id

    # Add members u1 and u2 to the project
    resp = client.post(f'/project/{proj_id}/edit',
                       data={'name': 'Test Project', 'member_ids': [str(u1.id), str(u2.id)]},
                       follow_redirects=True)
    assert resp.status_code == 200

    proj = db.session.get(Project, proj_id)
    member_emails = {m.email for m in proj.members}
    assert 'u1_pm@example.com' in member_emails
    assert 'u2_pm@example.com' in member_emails
