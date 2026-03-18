import os
from app import create_app

app = create_app()

# Create Celery app instance so docker-compose (and tests) can use `run.celery`
from app.celery_app import make_celery
celery = make_celery(app)


# ── Flask CLI commands ────────────────────────────────────────────────────────
import click

@app.cli.command('send-reminders')
@click.option('--days', default=None, type=int, help='Override cutoff days from settings')
def send_reminders(days):
    """Send due-date reminder emails for tasks due soon.

    Can be run directly (no Celery needed) via:
        flask send-reminders
        flask send-reminders --days 3

    Ideal for scheduling with cron or Windows Task Scheduler.
    """
    from app.tasks.alerts import generate_alerts
    result = generate_alerts(cutoff_days=days)
    sent = len(result.get('created', []))
    click.echo(f'Reminders sent: {sent} notification(s) for {len(result.get("groups", {}))} recipient(s).')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port)
