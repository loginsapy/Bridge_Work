from app import create_app
from flask import render_template_string


def test_safe_url_for_returns_hash_when_missing():
    app = create_app()
    with app.app_context():
        # Render a small template that calls safe_url_for for a non-existent endpoint
        out = render_template_string("{{ safe_url_for('non_existent.endpoint') }}")
        assert out.strip() == '#'
