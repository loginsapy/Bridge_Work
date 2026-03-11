from io import BytesIO

def test_navbar_displays_org_name(client, db, create_user, login):
    from app.models import SystemSettings

    # Set the organization name in settings
    s = SystemSettings(key='org_name', value='Acme Corp', category='general', value_type='string')
    db.session.add(s)
    db.session.commit()

    u = create_user(email='branduser@example.com', is_internal=True)
    login(u)
    rv = client.get('/')
    html = rv.get_data(as_text=True)

    # before uploading logo, default static image should appear
    assert '/static/images/sbwlogo.png' in html

    # simulate stored logo path but file missing; header should still show default
    from app.models import SystemSettings
    bad = SystemSettings(key='logo_path', value='/uploads/branding/missing.png', category='branding', value_type='string')
    db.session.add(bad)
    db.session.commit()
    rv_bad = client.get('/')
    html_bad = rv_bad.get_data(as_text=True)
    assert '/static/images/sbwlogo.png' in html_bad
    assert 'missing.png' not in html_bad

    # navbar should show the custom name and not the hardcoded default text
    assert 'Acme Corp' in html
    assert 'Login S.A.' not in html

    # footer should also reflect the name
    assert 'Acme Corp' in html

    # now simulate uploading a new logo via admin settings
    data = {
        'section': 'branding',
        'app_name': 'Acme Corp'
    }
    files = {
        'logo': (BytesIO(b'fakeimage'), 'newlogo.png')
    }
    rv2 = client.post('/admin/settings', data={**data, **files}, content_type='multipart/form-data', follow_redirects=True)
    assert rv2.status_code == 200

    # after upload, header should reference the new logo path
    rv3 = client.get('/')
    html3 = rv3.get_data(as_text=True)
    assert '/uploads/branding/logo_newlogo.png' in html3

    # ensure the file is actually served
    rv_file = client.get('/uploads/branding/logo_newlogo.png')
    assert rv_file.status_code == 200
    assert rv_file.data == b'fakeimage'

    # also check that admin settings branding tab shows the new logo preview
    rv4 = client.get('/admin/settings#branding')
    html4 = rv4.get_data(as_text=True)
    assert '/uploads/branding/logo_newlogo.png' in html4
