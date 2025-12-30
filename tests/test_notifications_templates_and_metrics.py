from app.tasks.sender import send_grouped_alerts
from app.notifications.provider import StubProvider


def test_render_and_metrics(monkeypatch, app):
    # Use real StubProvider which renders templates
    groups = {1: [100, 101]}
    with app.app_context():
        # Ensure metrics counters start at 0
        app.extensions['metrics']['alerts_sent'] = 0
        app.extensions['metrics']['alerts_failed'] = 0

        res = send_grouped_alerts(groups, retries=1, backoff_factor=0)
        assert res['failed'] == []
        assert set(res['success']) == {1}
        assert app.extensions['metrics']['alerts_sent'] == 1
        assert app.extensions['metrics']['alerts_failed'] == 0
