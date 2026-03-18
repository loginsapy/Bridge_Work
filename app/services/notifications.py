"""
Notification Service
====================
Central service for creating system notifications and sending emails.

Usage:
    from app.services import NotificationService
    
    # Create notification only (in-app)
    NotificationService.create(
        user_id=1,
        title="Nueva tarea asignada",
        message="Se te ha asignado la tarea 'Diseño de logo'",
        notification_type="task_assigned",
        related_entity_type="task",
        related_entity_id=123
    )
    
    # Create notification AND send email
    NotificationService.notify(
        user_id=1,
        title="Nueva tarea asignada",
        message="Se te ha asignado la tarea 'Diseño de logo'",
        notification_type="task_assigned",
        related_entity_type="task",
        related_entity_id=123,
        send_email=True
    )
"""

from datetime import datetime
from flask import current_app, render_template, url_for, request as flask_request
from .. import db
from ..models import SystemNotification, User, Task, Project
from ..models import AuditLog


class NotificationService:
    """Service for managing notifications and sending emails."""
    
    # Notification types
    TASK_ASSIGNED = 'task_assigned'
    TASK_COMPLETED = 'task_completed'
    TASK_STATUS_CHANGED = 'task_status_changed'
    TASK_APPROVAL_REQUESTED = 'task_approval_requested'
    TASK_APPROVED = 'task_approved'
    TASK_REJECTED = 'task_rejected'
    TASK_COMMENT = 'task_comment'
    TASK_DUE_SOON = 'task_due_soon'
    PROJECT_CREATED = 'project_created'
    PROJECT_UPDATED = 'project_updated'
    MENTION = 'mention'
    GENERAL = 'general'
    
    # Email templates mapping
    EMAIL_TEMPLATES = {
        'task_assigned': 'notifications/task_assigned.html',
        'task_completed': 'notifications/task_completed.html',
        'task_status_changed': 'notifications/task_status_changed.html',
        'task_approval_requested': 'notifications/task_approval_requested.html',
        'task_approved': 'notifications/task_approved.html',
        'task_rejected': 'notifications/task_rejected.html',
        'task_comment': 'notifications/general.html',
        'task_due_soon': 'notifications/task_due_soon.html',
        'project_created': 'notifications/project_created.html',
        'general': 'notifications/general.html',
    }
    
    @classmethod
    def create(cls, user_id: int, title: str, message: str, 
               notification_type: str = 'general',
               related_entity_type: str = None,
               related_entity_id: int = None,
               send_email: bool = None,
               email_context: dict = None) -> SystemNotification:
        """
        Create a system notification in the database.
        
        Args:
            user_id: ID of the user to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification (task_assigned, task_completed, etc.)
            related_entity_type: Type of related entity ('task', 'project', etc.)
            related_entity_id: ID of the related entity
            
        Returns:
            Created SystemNotification object
        """
        notification = SystemNotification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            is_read=False,
            created_at=datetime.now()
        )
        db.session.add(notification)
        db.session.commit()
        
        current_app.logger.info(
            f"Notification created: {title} for user {user_id} (type: {notification_type})"
        )

        # Audit the creation of the notification
        try:
            audit = AuditLog(
                user_id=user_id if user_id is not None else 0,
                action='CREATE_NOTIFICATION',
                entity_type='notification',
                entity_id=notification.id,
                changes={
                    'title': title,
                    'notification_type': notification_type,
                    'related_entity_type': related_entity_type,
                    'related_entity_id': related_entity_id,
                }
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            current_app.logger.exception('Failed to write AuditLog for notification create')
        
        # Decide if we should send an email for this notification
        try:
            from ..models import SystemSettings

            def _setting_enabled(key, default=True):
                v = SystemSettings.get(key, default)
                if isinstance(v, str):
                    return v.lower() in ('true', '1', 'yes')
                return bool(v)

            # Map notification_type -> system setting key
            nt_to_setting = {
                cls.TASK_ASSIGNED: 'notify_task_assigned',
                cls.TASK_COMPLETED: 'notify_task_completed',
                cls.TASK_APPROVED: 'notify_task_approved',
                cls.TASK_REJECTED: 'notify_task_rejected',
                cls.TASK_COMMENT: 'notify_task_comment',
                cls.TASK_DUE_SOON: 'notify_due_date_reminder'
            }

            should_send = False
            if send_email is True:
                should_send = True
            elif send_email is False:
                should_send = False
            else:
                # send_email is None: consult system settings mapping; default to True for notification keys
                key = nt_to_setting.get(notification_type)
                if key:
                    should_send = _setting_enabled(key, True)
                else:
                    should_send = False
        except Exception as e:
            current_app.logger.exception(f"Error deciding/sending notification email: {e}")

        return notification
    
    @classmethod
    def notify(cls, user_id: int, title: str, message: str,
               notification_type: str = 'general',
               related_entity_type: str = None,
               related_entity_id: int = None,
               send_email: bool = True,
               email_context: dict = None) -> SystemNotification:
        """
        Create a notification AND optionally send an email.
        
        Args:
            user_id: ID of the user to notify
            title: Notification title  
            message: Notification message
            notification_type: Type of notification
            related_entity_type: Type of related entity
            related_entity_id: ID of the related entity
            send_email: Whether to send email notification
            email_context: Additional context for email template
            
        Returns:
            Created SystemNotification object
        """
        # Create in-app notification (do NOT auto-send here; notify will handle sending to avoid duplicates)
        notification = cls.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            send_email=False,
            email_context=email_context
        )
        
        # Send email if requested by caller
        if send_email:
            cls.send_email(
                user_id=user_id,
                subject=title,
                notification_type=notification_type,
                context=email_context or {'message': message, 'title': title},
                notification_id=notification.id
            )
        
        return notification
    
    @classmethod
    def send_email(cls, user_id: int, subject: str, 
                   notification_type: str = 'general',
                   context: dict = None,
                   notification_id: int = None) -> bool:
        """
        Send an email notification to a user.
        
        Args:
            user_id: ID of the user to email
            subject: Email subject
            notification_type: Type of notification (determines template)
            context: Context for email template
            
        Returns:
            True if email sent successfully, False otherwise
        """
        from ..notifications.provider import get_provider
        
        try:
            user = User.query.get(user_id)
            if not user or not user.email:
                current_app.logger.warning(
                    f"Cannot send email: user {user_id} not found or has no email"
                )
                return False
            
            # Check if user wants email notifications (could add preference field later)
            # For now, always send
            
            # Get email template
            template_name = cls.EMAIL_TEMPLATES.get(
                notification_type, 
                'notifications/general.html'
            )
            
            # Get app name from system settings
            from ..models import SystemSettings
            app_name = SystemSettings.get('app_name', 'BridgeWork')
            
            # Build dashboard URL from actual request host
            try:
                dashboard_url = flask_request.url_root  # e.g. "https://myserver.com/"
            except RuntimeError:
                # Outside request context: use configured base_url or Flask config
                base_url = SystemSettings.get('base_url')
                if base_url:
                    dashboard_url = base_url.rstrip('/') + '/'
                else:
                    host = current_app.config.get('SERVER_NAME') or current_app.config.get('BASE_URL')
                    scheme = current_app.config.get('PREFERRED_URL_SCHEME', 'https')
                    dashboard_url = f"{scheme}://{host}/" if host else ''

            # Build context
            email_context = {
                'user': user,
                'subject': subject,
                'app_name': app_name,
                'dashboard_url': dashboard_url,
                **(context or {})
            }

            # Auto-build task_url if a task is in context but task_url was not provided
            if 'task_url' not in email_context and email_context.get('task'):
                email_context['task_url'] = cls._build_task_url(email_context['task'])
            
            # Render templates using Jinja environment directly to avoid request-only context processors
            try:
                tmpl = current_app.jinja_env.get_or_select_template(template_name)
                html_body = tmpl.render(**email_context)
            except Exception as e:
                current_app.logger.warning(f"Template {template_name} render failed, using general: {e}")
                try:
                    tmpl = current_app.jinja_env.get_or_select_template('notifications/general.html')
                    html_body = tmpl.render(**email_context)
                except Exception as e2:
                    current_app.logger.exception(f"Failed to render fallback email template: {e2}")
                    html_body = f"{subject}\n\n{email_context.get('message','')}"

            # Create text version
            text_body = cls._html_to_text(html_body, subject, context)

            # Send via provider
            provider = get_provider()
            current_app.logger.info(f"Using email provider {type(provider).__name__} to send to {user.email}")
            success = provider.send_email(
                recipient_id=user_id,
                subject=f"[BridgeWork] {subject}",
                body=text_body,
                html=html_body
            )
            
            if success:
                current_app.logger.info(
                    f"Email sent to user {user_id} ({user.email}): {subject}"
                )
            else:
                current_app.logger.warning(
                    f"Failed to send email to user {user_id}: {subject}"
                )
            # Audit the email send result
            try:
                audit = AuditLog(
                    user_id=user_id if user_id is not None else 0,
                    action='EMAIL_SENT' if success else 'EMAIL_FAILED',
                    entity_type='notification',
                    entity_id=notification_id if notification_id is not None else 0,
                    changes={
                        'subject': subject,
                        'notification_type': notification_type,
                        'provider': type(provider).__name__,
                        'recipient_email': user.email,
                        'success': bool(success)
                    }
                )
                db.session.add(audit)
                db.session.commit()
            except Exception:
                current_app.logger.exception('Failed to write AuditLog for email send')

            return success
            
        except Exception as e:
            current_app.logger.exception(f"Error sending email: {e}")
            return False
    
    @classmethod
    def _html_to_text(cls, html: str, subject: str, context: dict = None) -> str:
        """Convert HTML email to plain text fallback."""
        message = context.get('message', '') if context else ''
        return f"{subject}\n\n{message}\n\n---\nBridgeWork - Sistema de Gestión de Proyectos"

    @classmethod
    def _build_task_url(cls, task: Task) -> str:
        """Build an external URL to the task detail page.

        Priority:
          1. request.url_root — actual incoming HTTP request host (no SERVER_NAME issues)
          2. SystemSettings.base_url — fallback for background tasks / cron jobs
          3. Relative path — last resort
        """
        # 1. Best: read the real scheme+host directly from the current HTTP request
        try:
            return flask_request.url_root.rstrip('/') + f'/task/{task.id}'
        except RuntimeError:
            pass  # No active request context (background task, cron, CLI)

        # 2. Admin-configured public base URL (outside request context)
        try:
            from ..models import SystemSettings
            base = SystemSettings.get('base_url')
        except Exception:
            base = None

        if base:
            return f"{base.rstrip('/')}/task/{task.id}"

        # 3. Flask SERVER_NAME / BASE_URL config
        host = current_app.config.get('SERVER_NAME') or current_app.config.get('BASE_URL')
        if host:
            return f"{host.rstrip('/')}/task/{task.id}"

        return f"/task/{task.id}"
    
    # ============================================
    # Convenience methods for specific events
    # ============================================
    
    @classmethod
    def notify_task_assigned(cls, task: Task, assigned_by_user: User = None, 
                            send_email: bool = True, notify_client: bool = False) -> SystemNotification:
        """Notify user when a task is assigned to them.
        
        Args:
            task: The task that was assigned
            assigned_by_user: The user who made the assignment
            send_email: Whether to send email notification
            notify_client: If True, notify assigned_client_id instead of assigned_to_id
        """
        # Determine which user to notify
        if notify_client:
            user_id = task.assigned_client_id
            current_app.logger.info(f"notify_task_assigned: notificando a CLIENTE id={user_id}")
        else:
            user_id = task.assigned_to_id
            current_app.logger.info(f"notify_task_assigned: notificando a INTERNO id={user_id}")
            
        if not user_id:
            current_app.logger.warning(f"notify_task_assigned: user_id es None, no se envía notificación")
            return None
            
        assignee = User.query.get(user_id)
        if not assignee:
            current_app.logger.warning(f"notify_task_assigned: usuario {user_id} no encontrado")
            return None
        
        current_app.logger.info(f"notify_task_assigned: enviando a {assignee.email}, send_email={send_email}")
        
        project = Project.query.get(task.project_id) if task.project_id else None
        
        title = "Nueva tarea asignada"
        message = f"Se te ha asignado la tarea '{task.title}'"
        if project:
            message += f" en el proyecto '{project.name}'"
        if assigned_by_user:
            message += f" por {assigned_by_user.name or assigned_by_user.username}"

        task_url = cls._build_task_url(task)

        current_app.logger.info(f"notify_task_assigned: enviando a {assignee.email}, send_email={send_email}, notify_client={notify_client}")
        
        return cls.notify(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=cls.TASK_ASSIGNED,
            related_entity_type='task',
            related_entity_id=task.id,
            send_email=send_email,
            email_context={
                'task': task,
                'project': project,
                'assigned_by': assigned_by_user,
                'message': message,
                'title': title,
                'task_url': task_url
            }
        )
    
    @classmethod
    def notify_task_completed(cls, task: Task, completed_by_user: User = None,
                             notify_client: bool = True,
                             send_email: bool = True) -> list:
        """
        Notify relevant users when a task is completed.
        Notifies: Project managers/creators and optionally clients.
        """
        notifications = []
        
        project = Project.query.get(task.project_id) if task.project_id else None
        if not project:
            return notifications
        
        title = "Tarea completada"
        message = f"La tarea '{task.title}' ha sido marcada como completada"
        if completed_by_user:
            message += f" por {completed_by_user.name or completed_by_user.username}"

        task_url = cls._build_task_url(task)

        # Notify project creator/manager
        if project.created_by and project.created_by != (completed_by_user.id if completed_by_user else None):
            n = cls.notify(
                user_id=project.created_by,
                title=title,
                message=message,
                notification_type=cls.TASK_COMPLETED,
                related_entity_type='task',
                related_entity_id=task.id,
                send_email=send_email,
                email_context={
                    'task': task,
                    'project': project,
                    'completed_by': completed_by_user,
                    'message': message,
                    'title': title,
                    'task_url': task_url,
                }
            )
            notifications.append(n)

        # Notify clients if task requires approval
        if notify_client and task.requires_client_approval:
            # Get clients associated with the project
            from ..models import project_clients
            client_ids = db.session.query(project_clients.c.user_id).filter(
                project_clients.c.project_id == project.id
            ).all()

            for (client_id,) in client_ids:
                n = cls.notify(
                    user_id=client_id,
                    title="Tarea pendiente de aprobación",
                    message=f"La tarea '{task.title}' está lista para tu revisión",
                    notification_type=cls.TASK_APPROVAL_REQUESTED,
                    related_entity_type='task',
                    related_entity_id=task.id,
                    send_email=send_email,
                    email_context={
                        'task': task,
                        'project': project,
                        'completed_by': completed_by_user,
                        'message': f"La tarea '{task.title}' está lista para tu revisión",
                        'title': "Tarea pendiente de aprobación",
                        'task_url': task_url,
                    }
                )
                notifications.append(n)
        
        return notifications
    
    @classmethod
    def notify_task_status_changed(cls, task: Task, old_status: str, 
                                   changed_by_user: User = None,
                                   send_email: bool = False) -> SystemNotification:
        """Notify assignee when task status changes (email disabled by default)."""
        if not task.assigned_to_id:
            return None
        
        # Don't notify if the assignee made the change
        if changed_by_user and task.assigned_to_id == changed_by_user.id:
            return None
        
        title = "Estado de tarea actualizado"
        message = f"La tarea '{task.title}' cambió de '{old_status}' a '{task.status}'"
        
        return cls.notify(
            user_id=task.assigned_to_id,
            title=title,
            message=message,
            notification_type=cls.TASK_STATUS_CHANGED,
            related_entity_type='task',
            related_entity_id=task.id,
            send_email=send_email,
            email_context={
                'task': task,
                'old_status': old_status,
                'new_status': task.status,
                'changed_by': changed_by_user,
                'message': message,
                'title': title,
                'task_url': cls._build_task_url(task),
            }
        )
    
    @classmethod
    def notify_task_approved(cls, task: Task, approved_by_user: User,
                            send_email: bool = True) -> SystemNotification:
        """Notify task assignee when their task is approved by client."""
        if not task.assigned_to_id:
            return None
        
        title = "¡Tarea aprobada!"
        message = f"Tu tarea '{task.title}' ha sido aprobada"
        if approved_by_user:
            message += f" por {approved_by_user.name or approved_by_user.username}"
        
        return cls.notify(
            user_id=task.assigned_to_id,
            title=title,
            message=message,
            notification_type=cls.TASK_APPROVED,
            related_entity_type='task',
            related_entity_id=task.id,
            send_email=send_email,
            email_context={
                'task': task,
                'approved_by': approved_by_user,
                'message': message,
                'title': title,
                'task_url': cls._build_task_url(task),
            }
        )
    
    @classmethod
    def notify_task_rejected(cls, task: Task, rejected_by_user: User,
                            rejection_reason: str = None,
                            send_email: bool = True) -> SystemNotification:
        """Notify task assignee when their task is rejected by client."""
        if not task.assigned_to_id:
            return None
        
        title = "Tarea requiere revisión"
        message = f"Tu tarea '{task.title}' no fue aprobada"
        if rejected_by_user:
            message += f" por {rejected_by_user.name or rejected_by_user.username}"
        if rejection_reason:
            message += f". Motivo: {rejection_reason}"
        
        return cls.notify(
            user_id=task.assigned_to_id,
            title=title,
            message=message,
            notification_type=cls.TASK_REJECTED,
            related_entity_type='task',
            related_entity_id=task.id,
            send_email=send_email,
            email_context={
                'task': task,
                'rejected_by': rejected_by_user,
                'rejection_reason': rejection_reason,
                'message': message,
                'title': title,
                'task_url': cls._build_task_url(task),
            }
        )
    
    @classmethod
    def notify_task_due_soon(cls, task: Task, days_until_due: int,
                            send_email: bool = True) -> SystemNotification:
        """Notify assignee that task is due soon."""
        if not task.assigned_to_id:
            return None
        
        if days_until_due <= 0:
            title = "⚠️ Tarea vencida"
            message = f"La tarea '{task.title}' ya venció"
        elif days_until_due == 1:
            title = "⏰ Tarea vence mañana"
            message = f"La tarea '{task.title}' vence mañana"
        else:
            title = f"📅 Tarea vence en {days_until_due} días"
            message = f"La tarea '{task.title}' vence en {days_until_due} días"
        
        project = Project.query.get(task.project_id) if task.project_id else None
        
        return cls.notify(
            user_id=task.assigned_to_id,
            title=title,
            message=message,
            notification_type=cls.TASK_DUE_SOON,
            related_entity_type='task',
            related_entity_id=task.id,
            send_email=send_email,
            email_context={
                'task': task,
                'project': project,
                'days_until_due': days_until_due,
                'message': message,
                'title': title,
                'task_url': cls._build_task_url(task),
            }
        )
    
    @classmethod
    def mark_as_read(cls, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        notification = SystemNotification.query.filter_by(
            id=notification_id,
            user_id=user_id
        ).first()
        
        if notification:
            notification.is_read = True
            db.session.commit()
            return True
        return False
    
    @classmethod
    def mark_all_as_read(cls, user_id: int) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        count = SystemNotification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        return count
    
    @classmethod
    def get_unread_count(cls, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return SystemNotification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()
    
    @classmethod
    def get_recent(cls, user_id: int, limit: int = 10) -> list:
        """Get recent notifications for a user."""
        return SystemNotification.query.filter_by(
            user_id=user_id
        ).order_by(
            SystemNotification.is_read,
            SystemNotification.created_at.desc()
        ).limit(limit).all()
