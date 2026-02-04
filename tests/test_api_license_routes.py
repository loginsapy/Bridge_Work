import pytest
from unittest.mock import patch

from app.services import license_service


class MockResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or (payload and str(payload)) or ''

    def json(self):
        return self._payload


def test_activate_route_handles_404(client, db, create_user, login):
    # Create admin user and login
    admin = create_user(email='admin-route@example.com', is_internal=True)
    from app.models import Role
    r = Role.query.filter_by(name='Admin').first()
    if not r:
        r = Role(name='Admin')
        db.session.add(r)
        db.session.commit()
    admin.role = r
    db.session.commit()

    login(admin)

    with patch('app.services.license_service.requests.post') as mock_post:
        mock_post.return_value = MockResponse(status_code=404, payload={'message': 'Recurso no encontrado'}, text='Recurso no encontrado')
        res = client.post('/api/license/activate', json={'license_key': 'SNT6-EHU5-YVHC-3HJQ-RVPG'})

    assert res.status_code == 404
    data = res.get_json()
    assert data is not None
    assert data.get('error_code') == 'resource_not_found' or data.get('message') == 'Recurso no encontrado'
