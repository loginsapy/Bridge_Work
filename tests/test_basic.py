from app import create_app


def test_app_create():
    app = create_app('config.DevConfig')
    assert app is not None
