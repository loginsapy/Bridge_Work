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


class SMTPProvider(NotificationProvider):
    """SMTP Provider using settings from SystemSettings (admin/settings)"""
    
    def send_email(self, recipient_id: int, subject: str, body: str, html: str = None) -> bool:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from app.models import User, SystemSettings
        
        try:
            user = User.query.get(recipient_id)
            if not user or not user.email:
                current_app.logger.warning('SMTPProvider: no email for recipient %s', recipient_id)
                return False
            
            # Get SMTP settings from SystemSettings
            host = SystemSettings.get('smtp_host', '')
            port = int(SystemSettings.get('smtp_port', '587'))
            username = SystemSettings.get('smtp_username', '')
            password = SystemSettings.get('smtp_password', '')
            use_tls = SystemSettings.get('smtp_use_tls', 'true') == 'true'
            from_email = SystemSettings.get('email_from', username)
            from_name = SystemSettings.get('app_name', 'BridgeWork')
            
            if not host or not username:
                current_app.logger.warning('SMTPProvider: SMTP not configured')
                return False
            
            # Build message
            if html:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(body, 'plain', 'utf-8'))
                msg.attach(MIMEText(html, 'html', 'utf-8'))
            else:
                msg = MIMEText(body, 'plain', 'utf-8')
            
            msg['Subject'] = subject
            msg['From'] = f'{from_name} <{from_email}>'
            msg['To'] = user.email
            
            # Send email
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                if use_tls:
                    server.starttls()
            
            if password:
                server.login(username, password)
            
            server.sendmail(from_email, [user.email], msg.as_string())
            server.quit()
            
            current_app.logger.info('SMTPProvider: Email sent to %s (%s)', recipient_id, user.email)
            return True
            
        except Exception as e:
            current_app.logger.exception('SMTPProvider exception: %s', e)
            return False

    def render_alert(self, recipient_id: int, task_ids: list) -> tuple:
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
    """Get email provider - uses SMTP settings from SystemSettings by default"""
    from app.models import SystemSettings
    
    # Check if SMTP is configured in SystemSettings
    smtp_host = SystemSettings.get('smtp_host', '')
    if smtp_host:
        return SMTPProvider()
    
    # Fallback to config-based providers
    from flask import current_app as _cap
    cfg = (app.config if app else _cap.config)
    provider_name = cfg.get('EMAIL_PROVIDER', 'stub')
    if provider_name == 'sendgrid':
        api_key = cfg.get('SENDGRID_API_KEY')
        from_email = cfg.get('EMAIL_FROM', 'noreply@example.com')
        return SendGridProvider(api_key, from_email)
    
    return StubProvider()
