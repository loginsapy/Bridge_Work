def test_admin_notifications_rejects_invalid_base_url(client, db, create_user, login):
    admin = create_user(email='base_admin@example.com', is_internal=True)
    login(admin)

    # POST invalid base_url
    rv = client.post('/admin/notifications', data={'base_url': 'ftp://invalid-url', 'email_provider': 'smtp'}, follow_redirects=True)
    assert b'La Base URL debe comenzar con http:// o https://' in rv.data

    # Ensure setting not saved
    from app.models import SystemSettings
    assert SystemSettings.get('base_url') != 'ftp://invalid-url'
