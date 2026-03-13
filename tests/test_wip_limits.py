"""Tests for Kanban WIP limits API (PATCH /api/projects/<id>/wip-limits)."""
import pytest


def _make_pmp(create_user):
    return create_user(email='pmp@wip.test', is_internal=True)


def _make_project(create_project):
    return create_project(name='WIP Project')


# ── Happy path ────────────────────────────────────────────────────────────────

def test_set_wip_limits(client, db, create_user, create_project, login):
    user = _make_pmp(create_user)
    login(user)
    proj = _make_project(create_project)

    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'BACKLOG': None, 'IN_PROGRESS': 5, 'IN_REVIEW': 3, 'COMPLETED': None}
    })
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['wip_limits']['IN_PROGRESS'] == 5
    assert data['wip_limits']['IN_REVIEW'] == 3
    assert data['wip_limits']['BACKLOG'] is None


def test_wip_limits_persisted(client, db, create_user, create_project, login):
    """Limits saved in metadata_json and returned on next request."""
    user = _make_pmp(create_user)
    login(user)
    proj = _make_project(create_project)

    client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 7}
    })

    from app.models import Project
    p = Project.query.get(proj['id'])
    assert p.metadata_json['wip_limits']['IN_PROGRESS'] == 7


def test_clear_wip_limit(client, db, create_user, create_project, login):
    user = _make_pmp(create_user)
    login(user)
    proj = _make_project(create_project)

    # Set then clear
    client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 5}
    })
    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': None}
    })
    assert rv.status_code == 200
    assert rv.get_json()['wip_limits']['IN_PROGRESS'] is None


# ── Validation ────────────────────────────────────────────────────────────────

def test_wip_limit_zero_rejected(client, db, create_user, create_project, login):
    user = _make_pmp(create_user)
    login(user)
    proj = _make_project(create_project)

    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 0}
    })
    assert rv.status_code == 400


def test_wip_limit_non_int_rejected(client, db, create_user, create_project, login):
    user = _make_pmp(create_user)
    login(user)
    proj = _make_project(create_project)

    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 'muchas'}
    })
    assert rv.status_code == 400


# ── Auth / permissions ────────────────────────────────────────────────────────

def test_wip_limits_requires_login(client, db, create_project, create_user):
    proj = _make_project(create_project)
    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 3}
    })
    assert rv.status_code in (401, 302)


def test_wip_limits_participant_forbidden(client, db, create_user, create_project, login):
    from app.models import Role
    from app import db as _db

    proj = _make_project(create_project)
    part = create_user(email='part@wip.test', is_internal=True)
    role = Role.query.filter_by(name='Participante').first()
    if not role:
        role = Role(name='Participante')
        _db.session.add(role)
        _db.session.commit()
    part.role = role
    _db.session.commit()
    login(part)

    rv = client.patch(f'/api/projects/{proj["id"]}/wip-limits', json={
        'wip_limits': {'IN_PROGRESS': 3}
    })
    assert rv.status_code == 403
