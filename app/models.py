from datetime import datetime
from sqlalchemy import Enum as SAEnum
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = {'sqlite_autoincrement': True}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    azure_oid = db.Column(db.String(36), unique=True, nullable=True, index=True)
    is_internal = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
    role = db.relationship('Role', backref='users')
    first_name = db.Column(db.String(128))
    last_name = db.Column(db.String(128))

    created_at = db.Column(db.DateTime, default=datetime.now)

    @property
    def name(self):
        """Devuelve el nombre completo del usuario o el email si no tiene nombre"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email.split('@')[0]

    def __repr__(self):
        return f"<User {self.email}>"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# Simple RBAC
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

# Association table for Project-Client many-to-many
project_clients = db.Table('project_clients',
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

# Association table for Project-Member (participante) many-to-many
project_members = db.Table('project_members',
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

# Association table for Task predecessors (self-referential many-to-many)
task_predecessors = db.Table('task_predecessors',
    db.Column('task_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True),
    db.Column('predecessor_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True)
)


# Core domain
class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Legacy, kept for compatibility
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    client = db.relationship('User', foreign_keys=[client_id], backref='client_projects')
    clients = db.relationship('User', secondary=project_clients, backref='associated_projects')  # Multiple clients
    # Internal members (Participantes)
    members = db.relationship('User', secondary=project_members, backref='member_projects')
    status = db.Column(db.String(32), nullable=False, default='PLANNING')
    project_type = db.Column(db.String(32), nullable=False, default='APP_DEVELOPMENT')
    metadata_json = db.Column(db.JSON, nullable=True)
    budget_hours = db.Column(db.Numeric, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    manager = db.relationship('User', foreign_keys=[manager_id], backref='managed_projects')


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    parent_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    assigned_to_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    # Assigned client (customer) separate from internal assignee
    assigned_client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='BACKLOG')

    # Relationships for convenience
    assigned_client = db.relationship('User', foreign_keys=[assigned_client_id], backref='client_assigned_tasks')
    priority = db.Column(db.String(16), nullable=False, default='MEDIUM')
    due_date = db.Column(db.DateTime, nullable=True)
    is_external_visible = db.Column(db.Boolean, default=False, index=True)
    estimated_hours = db.Column(db.Numeric, nullable=True)
    # Position within project for manual ordering
    position = db.Column(db.Integer, nullable=True, index=True)
    
    # Client approval fields
    requires_approval = db.Column(db.Boolean, default=True)  # Si requiere aprobación del cliente
    approval_status = db.Column(db.String(32), nullable=True)  # PENDING, APPROVED, REJECTED
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)

    project = db.relationship('Project', backref='tasks')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], backref='tasks')
    approved_by = db.relationship('User', foreign_keys=[approved_by_id], backref='approved_tasks')

    # Self-referential many-to-many for task predecessors/successors
    predecessors = db.relationship(
        'Task',
        secondary=task_predecessors,
        primaryjoin=(id == task_predecessors.c.task_id),
        secondaryjoin=(id == task_predecessors.c.predecessor_id),
        backref=db.backref('successors', lazy='select'),
        lazy='select'
    )

    def reachable_to(self, target_task_id, visited=None):
        """Return True if there is a path from self to task with id target_task_id via successors."""
        if visited is None:
            visited = set()
        if self.id == target_task_id:
            return True
        visited.add(self.id)
        # successors may be a list or a selectable collection
        try:
            successors_iter = self.successors
        except Exception:
            successors_iter = []
        for succ in successors_iter:
            if succ.id in visited:
                continue
            if succ.id == target_task_id:
                return True
            if succ.reachable_to(target_task_id, visited):
                return True
        return False

    def descendants(self):
        """Return list of all descendant tasks reachable via successors (predecessor edges) OR via hierarchical parent-child (parent_task_id). Excludes self."""
        result = []
        visited = set()
        def dfs(node):
            # successors via predecessors table
            try:
                succs = node.successors
            except Exception:
                succs = []
            for s in succs:
                if s.id in visited or s.id == self.id:
                    continue
                visited.add(s.id)
                result.append(s)
                dfs(s)
            # hierarchical children (parent_task_id)
            try:
                children = Task.query.filter_by(parent_task_id=node.id).all()
            except Exception:
                children = []
            for c in children:
                if c.id in visited or c.id == self.id:
                    continue
                visited.add(c.id)
                result.append(c)
                dfs(c)
        dfs(self)
        return result

    def validate_predecessor_ids(self, predecessor_ids):
        """Validate a list of predecessor IDs before assignment.

        Raises ValueError with a descriptive message if invalid (self-contained or would create cycle).
        """
        # cannot be own predecessor
        if self.id in predecessor_ids:
            raise ValueError('A task cannot be its own predecessor')

        for pid in predecessor_ids:
            if pid == self.id:
                raise ValueError('A task cannot be its own predecessor')
            pred = Task.query.get(pid)
            if not pred:
                raise ValueError(f'Predecessor task id {pid} not found')
            # Must be in same project
            if hasattr(self, 'project_id') and pred.project_id != self.project_id:
                raise ValueError(f'Predecessor {pred.id} belongs to a different project')
            # Adding pred as a predecessor for self implies an edge pred -> self
            # If self can reach pred already, adding this edge would create a cycle
            if self.reachable_to(pred.id):
                raise ValueError(f'Adding predecessor {pred.id} would create a cycle')
        return True


class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    hours = db.Column(db.Numeric, nullable=False)
    description = db.Column(db.Text)
    is_billable = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    task = db.relationship('Task', backref='time_entries')
    user = db.relationship('User', backref='time_entries')


class NotificationRule(db.Model):
    __tablename__ = 'notification_rules'
    id = db.Column(db.Integer, primary_key=True)
    trigger_event = db.Column(db.String(64), nullable=False)
    parameters = db.Column(db.JSON, nullable=True)
    channel = db.Column(db.String(32), nullable=False, default='EMAIL')


class AlertLog(db.Model):
    __tablename__ = 'alert_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # task_id intentionally NOT a ForeignKey to allow logging failed IDs that may not have a Task record
    task_id = db.Column(db.Integer, nullable=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('notification_rules.id'), nullable=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(32), nullable=False, default='CREATED')
    created_at = db.Column(db.DateTime, default=datetime.now)
    sent_at = db.Column(db.DateTime, nullable=True)

    # keep relationships for convenience
    task = db.relationship('Task', primaryjoin='foreign(AlertLog.task_id)==Task.id', viewonly=True)
    rule = db.relationship('NotificationRule')
    recipient = db.relationship('User')


class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # Original filename
    stored_filename = db.Column(db.String(255), nullable=False)  # Stored filename (unique)
    file_size = db.Column(db.Integer, nullable=True)  # Size in bytes
    mime_type = db.Column(db.String(128), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    task = db.relationship('Task', backref='attachments')
    uploaded_by = db.relationship('User', backref='uploaded_attachments')


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    entity_type = db.Column(db.String(64), nullable=False)  # 'Project', 'Task', etc.
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(32), nullable=False)  # 'CREATE', 'UPDATE', 'DELETE'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    changes = db.Column(db.JSON, nullable=True)  # {field: {old: x, new: y}}
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='audit_logs')


class SystemNotification(db.Model):
    """Notificaciones en el sistema para usuarios"""
    __tablename__ = 'system_notifications'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(32), nullable=False)  # TASK_APPROVAL, INFO, WARNING
    related_entity_type = db.Column(db.String(64), nullable=True)  # 'Task', 'Project'
    related_entity_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref='notifications')


class SystemSettings(db.Model):
    """Configuraciones globales del sistema"""
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(16), default='string')  # string, number, boolean, json
    category = db.Column(db.String(32), nullable=False)  # branding, billing, general, notifications
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    updated_by = db.relationship('User', backref='updated_settings')
    
    @staticmethod
    def get(key, default=None):
        """Obtiene el valor de una configuración"""
        try:
            setting = SystemSettings.query.filter_by(key=key).first()
            if not setting:
                return default
            
            if setting.value_type == 'number':
                try:
                    return float(setting.value) if '.' in setting.value else int(setting.value)
                except:
                    return default
            elif setting.value_type == 'boolean':
                return setting.value.lower() in ('true', '1', 'yes')
            elif setting.value_type == 'json':
                import json
                try:
                    return json.loads(setting.value)
                except:
                    return default
            return setting.value
        except Exception:
            # Si hay un error de transacción, hacer rollback y devolver el default
            from . import db
            db.session.rollback()
            return default
    
    @staticmethod
    def set(key, value, category='general', description=None, value_type='string', user_id=None):
        """Establece el valor de una configuración"""
        setting = SystemSettings.query.filter_by(key=key).first()
        if not setting:
            setting = SystemSettings(key=key, category=category, description=description)
            db.session.add(setting)
        
        if value_type == 'json':
            import json
            setting.value = json.dumps(value)
        else:
            setting.value = str(value) if value is not None else None
        
        setting.value_type = value_type
        setting.updated_by_id = user_id
        if description:
            setting.description = description
        
        return setting


class HourlyRate(db.Model):
    """Tarifas por hora para diferentes roles o tipos de trabajo"""
    __tablename__ = 'hourly_rates'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)  # Ej: "Senior Developer", "Junior", "Consulting"
    rate = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD')  # ISO 4217
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    @staticmethod
    def get_default():
        """Obtiene la tarifa por defecto"""
        return HourlyRate.query.filter_by(is_default=True, is_active=True).first()

