from bs4 import BeautifulSoup


def test_limited_editor_sees_readonly_fields(client, db, create_user, create_project, create_task, login):
    # Participant view
    participant = create_user(email='partui@example.com', is_internal=True)
    from app.models import Role
    part_role = Role(name='Participante')
    db.session.add(part_role)
    db.session.commit()
    participant.role = part_role
    db.session.commit()

    login(participant)
    p = create_project(name='UIP')
    t = create_task(project_id=p['id'], title='UITask', estimated_hours=8)

    rv = client.get(f"/task/{t['id']}/edit")
    assert rv.status_code == 200
    soup = BeautifulSoup(rv.get_data(as_text=True), 'html.parser')

    # Estimated hours should be plaintext, not an input
    assert soup.find(attrs={'name': 'estimated_hours'}) is None
    assert soup.find('p', class_='form-control-plaintext')

    # Parent select should not be present
    assert soup.find('select', attrs={'name': 'parent_task_id'}) is None

    # Predecessor select should not be present
    assert soup.find('select', attrs={'name': 'predecessor_ids'}) is None

    # Checkbox should not be editable
    assert soup.find('input', attrs={'name': 'is_internal_only'}) is None
