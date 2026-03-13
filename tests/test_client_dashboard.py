"""Tests for the client portal dashboard (/client/dashboard)."""
import pytest
from app.models import Task, Project
from app import db as _db


def _setup_client(create_user):
    return create_user(email='cliente@portal.test', is_internal=False)


def _setup_pmp(create_user):
    return create_user(email='pmp@portal.test', is_internal=True)


# ── Access control ────────────────────────────────────────────────────────────

def test_dashboard_requires_login(client, db):
    rv = client.get('/client/dashboard', follow_redirects=False)
    assert rv.status_code in (302, 401)


def test_internal_user_redirected(client, db, create_user, login):
    pmp = _setup_pmp(create_user)
    login(pmp)
    rv = client.get('/client/dashboard', follow_redirects=False)
    # Internal users get redirected away from client portal
    assert rv.status_code == 302
    assert '/projects' in rv.headers['Location'] or '/dashboard' in rv.headers['Location']


def test_client_can_access_dashboard(client, db, create_user, login):
    cliente = _setup_client(create_user)
    login(cliente)
    rv = client.get('/client/dashboard')
    assert rv.status_code == 200
    assert b'Portal' in rv.data or b'portal' in rv.data


# ── Content ───────────────────────────────────────────────────────────────────

def test_dashboard_shows_kpi_cards(client, db, create_user, login):
    cliente = _setup_client(create_user)
    login(cliente)
    rv = client.get('/client/dashboard')
    html = rv.get_data(as_text=True)
    assert 'Proyectos' in html
    assert 'aprobaci' in html.lower()
    assert 'Atrasadas' in html or 'atrasadas' in html


def test_assigned_task_appears_in_table(client, db, create_user, create_project, login):
    pmp = _setup_pmp(create_user)
    cliente = _setup_client(create_user)

    proj = create_project(name='Proj Cliente')
    # Manually associate client with project and create assigned task
    p = Project.query.get(proj['id'])
    p.clients.append(cliente)
    _db.session.commit()

    task = Task(project_id=proj['id'], title='Tarea asignada al cliente',
                assigned_client_id=cliente.id, status='IN_PROGRESS')
    _db.session.add(task)
    _db.session.commit()

    login(cliente)
    rv = client.get('/client/dashboard')
    assert rv.status_code == 200
    assert 'Tarea asignada al cliente' in rv.get_data(as_text=True)


def test_pending_approval_section_shown(client, db, create_user, create_project, login):
    cliente = _setup_client(create_user)
    proj = create_project(name='Proj Aprobacion')
    p = Project.query.get(proj['id'])
    p.clients.append(cliente)
    _db.session.commit()

    task = Task(project_id=proj['id'], title='Necesita aprobacion',
                assigned_client_id=cliente.id, requires_approval=True,
                approval_status='PENDING', status='IN_REVIEW')
    _db.session.add(task)
    _db.session.commit()

    login(cliente)
    rv = client.get('/client/dashboard')
    html = rv.get_data(as_text=True)
    assert 'Necesita aprobacion' in html
    assert 'Aprobar' in html
    assert 'Rechazar' in html


def test_no_internal_only_tasks_shown(client, db, create_user, create_project, login):
    """Client should NOT see tasks marked is_internal_only even if assigned_client matches."""
    cliente = _setup_client(create_user)
    proj = create_project(name='Proj Interno')
    p = Project.query.get(proj['id'])
    p.clients.append(cliente)
    _db.session.commit()

    # Internal-only task — should NOT appear in client's assigned tasks
    internal_task = Task(project_id=proj['id'], title='Tarea solo interna',
                         is_internal_only=True, status='BACKLOG')
    # Client-assigned task — should appear
    client_task = Task(project_id=proj['id'], title='Tarea del cliente',
                       assigned_client_id=cliente.id, status='BACKLOG')
    _db.session.add_all([internal_task, client_task])
    _db.session.commit()

    login(cliente)
    rv = client.get('/client/dashboard')
    html = rv.get_data(as_text=True)
    assert 'Tarea del cliente' in html
    assert 'Tarea solo interna' not in html


# ── Approval API ──────────────────────────────────────────────────────────────

def test_client_can_approve_own_task(client, db, create_user, create_project, login):
    cliente = _setup_client(create_user)
    proj = create_project(name='Proj Approval')

    task = Task(project_id=proj['id'], title='Para aprobar',
                assigned_client_id=cliente.id, requires_approval=True,
                approval_status='PENDING', status='IN_REVIEW')
    _db.session.add(task)
    _db.session.commit()

    login(cliente)
    rv = client.patch(f'/api/tasks/{task.id}', json={'approval_status': 'APPROVED'})
    assert rv.status_code == 200

    _db.session.refresh(task)
    assert task.approval_status == 'APPROVED'
    assert task.approved_by_id == cliente.id


def test_client_cannot_approve_other_client_task(client, db, create_user, create_project, login):
    cliente_a = _setup_client(create_user)
    cliente_b = create_user(email='clienteb@portal.test', is_internal=False)
    proj = create_project(name='Proj Other')

    task = Task(project_id=proj['id'], title='De otro cliente',
                assigned_client_id=cliente_b.id, requires_approval=True,
                approval_status='PENDING', status='IN_REVIEW')
    _db.session.add(task)
    _db.session.commit()

    login(cliente_a)
    rv = client.patch(f'/api/tasks/{task.id}', json={'approval_status': 'APPROVED'})
    assert rv.status_code == 403


def test_client_cannot_edit_title(client, db, create_user, create_project, login):
    cliente = _setup_client(create_user)
    proj = create_project(name='Proj Edit')

    task = Task(project_id=proj['id'], title='Original',
                assigned_client_id=cliente.id, status='BACKLOG')
    _db.session.add(task)
    _db.session.commit()

    login(cliente)
    rv = client.patch(f'/api/tasks/{task.id}', json={'title': 'Hackeado'})
    assert rv.status_code == 403
