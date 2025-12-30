from typing import List, Dict, Any
from flask import current_app


class NotificationProvider:
    def send_email(self, recipient_id: int, subject: str, body: str, html: str = None) -> bool:
        """Send an email to recipient_id (application is expected to resolve recipient email). Returns True on success."""
        raise NotImplementedError

    def render_alert(self, recipient_id: int, task_ids: list) -> tuple:
        """Return (subject, text_body, html_body) rendered for the recipient and tasks."""
        raise NotImplementedError


class StubProvider(NotificationProvider):
    def send_email(self, recipient_id: int, subject: str, body: str, html: str = None) -> bool:
        current_app.logger.info("StubProvider sending email to recipient %s: %s", recipient_id, subject)
        return True

    def render_alert(self, recipient_id: int, task_ids: list) -> tuple:
        # Use Jinja2 templates under templates/notifications/
        from flask import render_template
        subject = f"{len(task_ids)} pending tasks due soon"
        text = render_template('notifications/alert_email.txt', count=len(task_ids), tasks=task_ids)
        html = render_template('notifications/alert_email.html', count=len(task_ids), tasks=task_ids)
        return subject, text, html


class SendGridProvider(NotificationProvider):
    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email

    def send_email(self, recipient_id: int, subject: str, body: str, html: str = None) -> bool:
        # Real implementation would resolve recipient email from DB and call SendGrid API
        try:
            from app.models import User
            user = User.query.get(recipient_id)
            if not user or not user.email:
                current_app.logger.warning('SendGridProvider: no email for recipient %s', recipient_id)
                return False

            # Lazy import to avoid hard dependency during tests
            import requests
            sg_url = 'https://api.sendgrid.com/v3/mail/send'
            content = [{'type': 'text/plain', 'value': body}]
            if html:
                content.append({'type': 'text/html', 'value': html})
            payload = {
                'personalizations': [{'to': [{'email': user.email}], 'subject': subject}],
                'from': {'email': self.from_email},
                'content': content,
            }
            headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
            r = requests.post(sg_url, json=payload, headers=headers, timeout=10)
            if r.status_code in (200, 202):
                return True
            current_app.logger.warning('SendGridProvider failed: %s %s', r.status_code, r.text)
            return False
        except Exception as e:
            current_app.logger.exception('SendGridProvider exception: %s', e)
            return False

    def render_alert(self, recipient_id: int, task_ids: list) -> tuple:
        from flask import render_template
        subject = f"{len(task_ids)} pending tasks due soon"
        text = render_template('notifications/alert_email.txt', count=len(task_ids), tasks=task_ids)
        html = render_template('notifications/alert_email.html', count=len(task_ids), tasks=task_ids)
        return subject, text, html


def get_provider(app=None) -> NotificationProvider:
    from flask import current_app as _cap
    cfg = (app.config if app else _cap.config)
    provider_name = cfg.get('EMAIL_PROVIDER', 'stub')
    if provider_name == 'sendgrid':
        api_key = cfg.get('SENDGRID_API_KEY')
        from_email = cfg.get('EMAIL_FROM', 'noreply@example.com')
        return SendGridProvider(api_key, from_email)
    return StubProvider()
