import pytest
from app import create_app, db as _db
from sqlalchemy import event


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


@pytest.fixture(scope='session')
def app():
    # Create the Flask app using the TestConfig class so DB bindings are created
    # with the in-memory sqlite URI instead of the default Dev/Prod config.
    app = create_app(TestConfig)

    # Extra safety: ensure TESTING is enabled and the DB URI is local (sqlite or localhost)
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    testing_ok = app.config.get('TESTING', False)
    if not testing_ok or not (uri.startswith('sqlite') or 'localhost' in uri or '127.0.0.1' in uri):
        raise RuntimeError(f"Unsafe test DB URI detected: {uri!r}. Aborting tests to avoid data loss.")

    with app.app_context():
        yield app


@pytest.fixture(scope='function')
def db(app):
    _db.create_all()
    yield _db
    _db.session.remove()

    # Guard: refuse to drop tables on a non-testing or remote DB
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    if not app.config.get('TESTING', False) or not (uri.startswith('sqlite') or 'localhost' in uri or '127.0.0.1' in uri):
        raise RuntimeError(f"Refusing to drop DB for unsafe URI: {uri!r}")

    _db.drop_all()


@pytest.fixture(scope='function')
def client(app, db):
    return app.test_client()


# Factory helpers for tests
@pytest.fixture
def create_user(db):
    from app.models import User

    def _create_user(email='u@example.com', **kwargs):
        u = User(email=email, **kwargs)
        db.session.add(u)
        db.session.commit()
        # Assign default internal role for internal users if none provided
        from app.models import Role
        if getattr(u, 'is_internal', False) and not getattr(u, 'role', None):
            role = Role.query.filter_by(name='PMP').first()
            if not role:
                role = Role(name='PMP')
                db.session.add(role)
                db.session.commit()
            u.role = role
            db.session.commit()
        # Assign default client role for external users if none provided
        if not getattr(u, 'is_internal', True) and not getattr(u, 'role', None):
            role = Role.query.filter_by(name='Cliente').first()
            if not role:
                role = Role(name='Cliente')
                db.session.add(role)
                db.session.commit()
            u.role = role
            db.session.commit()
        return u

    return _create_user


@pytest.fixture
def login(client):
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

    return _login


@pytest.fixture
def create_project(client):
    def _create_project(name='P1', via_api=False, **kwargs):
        payload = {'name': name}
        payload.update(kwargs)
        if via_api:
            rv = client.post('/api/projects', json=payload)
            return rv.get_json()
        else:
            from app.models import Project
            from app import db
            p = Project(name=name, **kwargs)
            db.session.add(p)
            db.session.commit()
            return {'id': p.id, 'name': p.name}

    return _create_project


@pytest.fixture
def create_task(client):
    def _create_task(project_id, title='T1', via_api=False, **kwargs):
        payload = {'project_id': project_id, 'title': title}
        payload.update(kwargs)
        if via_api:
            rv = client.post('/api/tasks', json=payload)
            return rv.get_json()
        else:
            from app.models import Task
            from app import db
            t = Task(project_id=project_id, title=title, **kwargs)
            db.session.add(t)
            db.session.commit()
            return {
                'id': t.id,
                'project_id': t.project_id,
                'title': t.title,
                'is_external_visible': t.is_external_visible,
            }

    return _create_task
