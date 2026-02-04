from datetime import datetime, timedelta
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
    company = db.Column(db.String(255), nullable=True)  # For clients
    phone = db.Column(db.String(50), nullable=True)  # Contact phone

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

# Association table for Task assignees (many-to-many: tasks <-> users)
task_assignees = db.Table('task_assignees',
    db.Column('task_id', db.Integer, db.ForeignKey('tasks.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
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
    # Hierarchical parent pointer (WBS)
    parent_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    assigned_to_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=True)
    # Assigned client (customer) separate from internal assignee
    assigned_client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='BACKLOG')

    # Relationships for convenience
    assigned_client = db.relationship('User', foreign_keys=[assigned_client_id], backref='client_assigned_tasks')
    priority = db.Column(db.String(16), nullable=False, default='MEDIUM')
    start_date = db.Column(db.DateTime, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    is_external_visible = db.Column(db.Boolean, default=False, index=True)
    is_internal_only = db.Column(db.Boolean, default=False, index=True)  # Solo visible para PMP/Admin
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
    # Multiple assigned internal users (many-to-many)
    assignees = db.relationship('User', secondary=task_assignees, backref='assigned_tasks', lazy='select')
    approved_by = db.relationship('User', foreign_keys=[approved_by_id], backref='approved_tasks')

    @property
    def assignee_list(self):
        """Returns a list of assigned users: prefer explicit `assignees` but fallback to the legacy `assigned_to`."""
        if getattr(self, 'assignees', None):
            return list(self.assignees)
        if getattr(self, 'assigned_to', None):
            return [self.assigned_to]
        return []

    # Hierarchical parent/children relationship (WBS)
    parent = db.relationship('Task', remote_side=[id], backref=db.backref('children', lazy='select'))

    # Self-referential many-to-many for task predecessors/successors
    predecessors = db.relationship(
        'Task',
        secondary=task_predecessors,
        primaryjoin=(id == task_predecessors.c.task_id),
        secondaryjoin=(id == task_predecessors.c.predecessor_id),
        backref=db.backref('successors', lazy='select'),
        lazy='select'
    )

    @property
    def days_late(self):
        """Calculate days late using completion_date if available, else due_date"""
        if not self.due_date:
            return 0
        
        # Use completed_at if task is completed, otherwise use today's date
        reference_date = self.completed_at if self.completed_at else datetime.utcnow()
        days = (reference_date.date() - self.due_date.date()).days
        return max(0, days)  # Don't show negative delays

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
        """Return list of all descendant tasks reachable via hierarchy (children) and dependency (successors)."""
        result = []
        visited = set()

        def dfs(node):
            # traverse hierarchical children first
            for c in getattr(node, 'children', []) or []:
                if c.id in visited or c.id == self.id:
                    continue
                visited.add(c.id)
                result.append(c)
                dfs(c)
            # then traverse successor dependency edges
            for s in getattr(node, 'successors', []) or []:
                if s.id in visited or s.id == self.id:
                    continue
                visited.add(s.id)
                result.append(s)
                dfs(s)

        dfs(self)
        return result

    def incomplete_predecessors(self):
        """Return list of predecessor Task objects that are not completed.
        
        PREDECESORAS = Dependencias de secuencia (no jerarquía).
        Una tarea NO puede iniciar/completarse hasta que sus predecesoras estén completas.
        Esto es diferente a la jerarquía padre-hijo.
        """
        return [p for p in getattr(self, 'predecessors', []) or [] if p.status != 'COMPLETED']

    def incomplete_children(self):
        """Return list of direct child tasks (via parent_task_id) that are not completed.
        
        HIJOS = Jerarquía WBS (subtareas).
        Una tarea padre NO puede completarse hasta que todas sus subtareas estén completas.
        """
        return [c for c in getattr(self, 'children', []) or [] if c.status != 'COMPLETED']

    def incomplete_hierarchical_descendants(self):
        """Return list of ALL hierarchical descendant tasks (children recursively via parent_task_id) that are not completed."""
        result = []
        visited = set()

        def dfs(node):
            for c in getattr(node, 'children', []) or []:
                if c.id in visited or c.id == self.id:
                    continue
                visited.add(c.id)
                if c.status != 'COMPLETED':
                    result.append(c)
                dfs(c)

        dfs(self)
        return result

    def all_incomplete_children(self):
        """Return list of ALL incomplete child tasks (direct + descendants via hierarchy).
        
        Combina hijos directos e indirectos para validación de cierre.
        """
        result = []
        visited = set()

        def dfs(node):
            for c in getattr(node, 'children', []) or []:
                if c.id in visited or c.id == self.id:
                    continue
                visited.add(c.id)
                result.append(c)
                dfs(c)

        dfs(self)
        return [c for c in result if c.status != 'COMPLETED']

    def can_complete(self):
        """Check if this task can be marked as completed.
        
        Returns (bool, str): (can_complete, reason_if_not)
        
        Reglas:
        1. No se puede completar si tiene predecesoras incompletas (dependencias)
        2. No se puede completar si tiene subtareas incompletas (jerarquía)
        """
        # Verificar predecesoras (dependencias de secuencia)
        incomplete_preds = self.incomplete_predecessors()
        if incomplete_preds:
            titles = ', '.join([p.title for p in incomplete_preds[:3]])
            if len(incomplete_preds) > 3:
                titles += f' y {len(incomplete_preds) - 3} más'
            return False, f'Predecesoras incompletas: {titles}'
        
        # Verificar subtareas (jerarquía)
        incomplete_kids = self.all_incomplete_children()
        if incomplete_kids:
            titles = ', '.join([c.title for c in incomplete_kids[:3]])
            if len(incomplete_kids) > 3:
                titles += f' y {len(incomplete_kids) - 3} más'
            return False, f'Subtareas incompletas: {titles}'
        
        return True, None

    def get_completion_blockers(self):
        """Return dict with lists of incomplete tasks that block completion.
        
        Sistema de gestión de proyectos:
        - incomplete_predecessors: Tareas que deben completarse ANTES (dependencias de secuencia)
        - incomplete_children: Subtareas que deben completarse ANTES (jerarquía WBS)
        """
        incomplete_preds = self.incomplete_predecessors()
        incomplete_kids = self.all_incomplete_children()
        
        return {
            'incomplete_predecessors': [{'id': p.id, 'title': p.title} for p in incomplete_preds],
            'incomplete_children': [{'id': c.id, 'title': c.title} for c in incomplete_kids]
        }

    @staticmethod
    def normalize_status(status: str) -> str:
        """Normalize status values to canonical set.
        Accept legacy synonyms like 'DONE' and normalize to 'COMPLETED'."""
        if status is None:
            return None
        if isinstance(status, str) and status.upper() == 'DONE':
            return 'COMPLETED'
        return status

    def set_status(self, new_status: str):
        """Set task status normalizing legacy values."""
        self.status = Task.normalize_status(new_status)
        
        # Update completed_at timestamp
        if self.status == 'COMPLETED':
            self.completed_at = datetime.now()
        elif self.status != 'COMPLETED':
            self.completed_at = None
    
    def is_blocked(self):
        """Check if task is blocked by incomplete predecessors.
        
        Una tarea está bloqueada si tiene predecesoras sin completar.
        """
        return len(self.incomplete_predecessors()) > 0

    def has_incomplete_subtasks(self):
        """Check if task has any incomplete child tasks."""
        return len(self.all_incomplete_children()) > 0
    
    def can_advance_status(self, new_status):
        """Check if task can advance to a new status.
        
        Reglas:
        - Una tarea con predecesoras incompletas NO puede avanzar a ningún estado
          (debe permanecer en BACKLOG hasta que sus predecesoras se completen)
        - Una tarea padre NO puede completarse si tiene subtareas incompletas
        - Siempre se puede retroceder (mover a BACKLOG)
        
        Returns:
            tuple: (can_advance: bool, error_message: str or None, blockers: dict or None)
        """
        STATUS_ORDER = {'BACKLOG': 0, 'IN_PROGRESS': 1, 'IN_REVIEW': 2, 'COMPLETED': 3, 'DONE': 3}
        current_order = STATUS_ORDER.get(self.status, 0)
        new_order = STATUS_ORDER.get(new_status, 0)
        
        # Si está retrocediendo (ej: de IN_PROGRESS a BACKLOG), siempre permitir
        if new_order <= current_order:
            return (True, None, None)
        
        # Para cualquier avance, verificar predecesoras incompletas
        incomplete_preds = self.incomplete_predecessors()
        if incomplete_preds:
            pred_titles = ', '.join([p.title for p in incomplete_preds[:3]])
            if len(incomplete_preds) > 3:
                pred_titles += f' (+{len(incomplete_preds) - 3} más)'
            return (
                False,
                f'No se puede avanzar la tarea: tiene predecesoras incompletas ({pred_titles})',
                {'incomplete_predecessors': [{'id': p.id, 'title': p.title, 'status': p.status} for p in incomplete_preds]}
            )
        
        # Si intenta completar, también verificar subtareas
        if new_status in ('COMPLETED', 'DONE'):
            incomplete_children = self.all_incomplete_children()
            if incomplete_children:
                child_titles = ', '.join([c.title for c in incomplete_children[:3]])
                if len(incomplete_children) > 3:
                    child_titles += f' (+{len(incomplete_children) - 3} más)'
                return (
                    False,
                    f'No se puede completar: tiene subtareas incompletas ({child_titles})',
                    {'incomplete_children': [{'id': c.id, 'title': c.title, 'status': c.status} for c in incomplete_children]}
                )
        
        return (True, None, None)

    def validate_predecessor_ids(self, predecessor_ids):
        """Validate a list of predecessor IDs before assignment.

        Raises ValueError with a descriptive message if invalid (self-contained, project mismatch, or would create cycles across dependency/hierarchy).
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

            # Dependency-cycle: if self already reaches pred via successors, adding pred -> self would create a cycle
            if self.reachable_to(pred.id):
                raise ValueError(f'Adding predecessor {pred.id} would create a cycle')

            # Only check hierarchy (parent/children) for ancestor/descendant; do not conflate with dependency edges.
            # Check if pred is an ancestor of self by walking parent pointers up from self.
            cur = getattr(self, 'parent', None)
            while cur:
                if cur.id == pred.id:
                    raise ValueError(f'Predecessor {pred.id} is an ancestor of this task in the hierarchy')
                cur = getattr(cur, 'parent', None)

            # Check if pred is a descendant of self by walking up from pred and seeing if we reach self.
            cur = getattr(pred, 'parent', None)
            while cur:
                if cur.id == self.id:
                    raise ValueError(f'Predecessor {pred.id} is a descendant of this task in the hierarchy')
                cur = getattr(cur, 'parent', None)

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


class License(db.Model):
    """Modelo para almacenar información de licencia del sistema"""
    __tablename__ = 'licenses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    license_key = db.Column(db.String(64), nullable=False)
    product_code = db.Column(db.String(64), default='BRIDGEWORK')
    hardware_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(32), default='PENDING')  # PENDING, ACTIVE, EXPIRED, INVALID
    activated_at = db.Column(db.DateTime, nullable=True)
    last_validated_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    license_type = db.Column(db.String(32), nullable=True)  # TRIAL, STANDARD, ENTERPRISE
    max_users = db.Column(db.Integer, nullable=True)
    features = db.Column(db.JSON, nullable=True)  # Features enabled by license
    customer_name = db.Column(db.String(255), nullable=True)
    customer_email = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    @staticmethod
    def get_active():
        """Obtiene la licencia activa del sistema"""
        return License.query.filter_by(status='ACTIVE').first()
    
    @staticmethod
    def get_current():
        """Obtiene la licencia actual (activa o la más reciente)"""
        active = License.get_active()
        if active:
            return active
        return License.query.order_by(License.created_at.desc()).first()
    
    def is_valid(self):
        """Verifica si la licencia es válida"""
        if self.status != 'ACTIVE':
            return False
        if self.expires_at and self.expires_at < datetime.now():
            return False
        return True
    
    def needs_validation(self, days=15):
        """Verifica si la licencia necesita revalidación"""
        if not self.last_validated_at:
            return True
        from datetime import timedelta
        return (datetime.now() - self.last_validated_at) > timedelta(days=days)
