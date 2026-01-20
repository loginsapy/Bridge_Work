from datetime import date


def test_project_kpi_cards_update(client, db, create_user, create_project, create_task, create_time_entry, login):
    u = create_user(email='cards@example.com', is_internal=True)
    login(u)

    # Create project with budget and two tasks (one completed, one not)
    p = create_project(name='CardsP', budget_hours=100)
    t1 = create_task(project_id=p['id'], title='T1', status='COMPLETED')
    t2 = create_task(project_id=p['id'], title='T2', status='BACKLOG')

    # Add time entries for project tasks
    create_time_entry(task_id=t1['id'], user_id=u.id, date=date.today(), hours=2)
    create_time_entry(task_id=t2['id'], user_id=u.id, date=date.today(), hours=3)

    rv = client.get(f"/reports?project_id={p['id']}")
    assert rv.status_code == 200
    data = rv.get_data(as_text=True)

    # KPIs should reflect project (2 tasks, 1 completed -> 50% completion) and budget 100h
    assert '50%' in data
    assert '100h' in data
    # Ensure the total tasks number (2) appears near the KPI area; this is a simple sanity check
    assert ('>2<' in data) or ('> 2<' in data) or ("\n    2\n" in data)
