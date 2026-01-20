from datetime import datetime, timedelta


def test_kanban_shows_done_normalized_in_completed(client, db, create_user, create_project, create_task, login):
    u = create_user(email='kanban_admin@example.com', is_internal=True)
    login(u)

    p = create_project(name='KanbanNorm')
    t = create_task(project_id=p['id'], title='DoneToCompletedTask')

    # Patch to legacy 'DONE' via API -> should normalize
    rv = client.patch(f"/api/tasks/{t['id']}", json={'status': 'DONE'})
    assert rv.status_code == 200

    # Fetch Kanban page and ensure the task is in the COMPLETED column
    rv2 = client.get(f"/project/{p['id']}/kanban")
    html = rv2.get_data(as_text=True)

    assert '<div class="kanban-column" data-status="COMPLETED">' in html
    idx = html.find('<div class="kanban-column" data-status="COMPLETED">')
    assert idx != -1
    snippet = html[idx: idx + 2000]
    assert 'DoneToCompletedTask' in snippet


def test_gantt_shows_done_normalized_in_gantt_json(client, db, create_user, create_project, create_task, login):
    u = create_user(email='gantt_admin@example.com', is_internal=True)
    login(u)

    p = create_project(name='GanttNorm')
    start = datetime.now().date()
    due = start + timedelta(days=3)

    t = create_task(project_id=p['id'], title='GanttDoneTask', start_date=start, due_date=due)

    # Patch to legacy 'DONE' via API -> should normalize
    rv = client.patch(f"/api/tasks/{t['id']}", json={'status': 'DONE'})
    assert rv.status_code == 200

    rv2 = client.get(f"/project/{p['id']}/gantt")
    html = rv2.get_data(as_text=True)

    # The server embeds gantt_tasks as JSON; ensure the status is normalized to COMPLETED
    assert '"status":"COMPLETED"' in html or 'status-COMPLETED' in html
