import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from sqlalchemy import func

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=[])


_WEAK_KEYS = {'dev-secret', 'changeme', 'secret', 'development', 'insecure', ''}


def _validate_config(app):
    """Warn at startup if critical settings are insecure or missing."""
    key = app.config.get('SECRET_KEY', '')
    if not key or key.lower() in _WEAK_KEYS or len(key) < 24:
        app.logger.warning(
            'SECURITY: SECRET_KEY is weak or default. Set a strong random value via the SECRET_KEY env var.'
        )
    if not app.config.get('TESTING') and app.debug:
        app.logger.warning('SECURITY: DEBUG mode is ON. Do not use DEBUG=True in production.')
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri:
        app.logger.warning('CONFIG: SQLALCHEMY_DATABASE_URI is not set. Check DATABASE_URL env var.')


def create_app(config_object="config.DevConfig"):
    # Load environment variables from .env if present (dev convenience)
    load_dotenv()
    # Determine the absolute path to the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    # Prefer serving static files from the package's `app/static` so assets
    # (images, css, js) live with the app. Fall back to top-level `static/`
    # when `app/static` does not exist (legacy).
    package_static = os.path.join(os.path.dirname(__file__), 'static')
    static_folder_path = package_static if os.path.isdir(package_static) else os.path.join(project_root, 'static')

    app = Flask(__name__, static_folder=static_folder_path)
    # Load base defaults first so lightweight test configs inherit essentials like ALLOWED_EXTENSIONS
    try:
        app.config.from_object('config.Config')
    except Exception:
        pass
    app.config.from_object(config_object)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, inicia sesión para continuar.'
    login_manager.login_message_category = 'warning'

    # Initialize metrics helper (Prometheus if available, else simple counters)
    from .metrics import Metrics
    app.metrics = Metrics(app)

    _validate_config(app)

    # Provide a fallback in app.extensions for code that uses simple counters
    app.extensions.setdefault('metrics', {})
    app.extensions['metrics'].setdefault('alerts_sent', 0)

    # Add a global SQLAlchemy error handler to rollback sessions on DB errors
    from sqlalchemy.exc import SQLAlchemyError

    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(error):
        app.logger.exception('Unhandled SQLAlchemyError: %s', error)
        try:
            db.session.rollback()
        except Exception:
            app.logger.exception('Error rolling back DB session after SQLAlchemyError')
        return ("Database error", 500)

    # Expose /metrics endpoint
    @app.route('/metrics')
    def metrics_endpoint():
        data = app.metrics.registry_metrics()
        return (data, 200, {'Content-Type': app.metrics.content_type()})

    # Register blueprints (stubs)
    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    from .main import main_bp
    app.register_blueprint(main_bp)

    # API blueprint
    from .api import api_bp
    app.register_blueprint(api_bp)

    # License check middleware
    @app.before_request
    def check_license():
        from flask import request, redirect, url_for, flash
        from flask_login import current_user
        from .services import license_service
        
        # Skip license check for static files, login, logout, and license endpoints
        skip_paths = [
            '/static/', '/login', '/logout', '/callback', '/metrics',
            '/api/license/', '/admin/settings', '/auth/'
        ]
        
        if any(request.path.startswith(p) for p in skip_paths):
            return None

        # Skip license check in test environment
        if app.config.get('TESTING'):
            return None

        # Skip for unauthenticated users (they'll be redirected to login)
        if not current_user.is_authenticated:
            return None
        
        # Check license status
        try:
            license_status = license_service.check_license_status()
            if not license_status.get('is_valid', False):
                # Admin can access settings to activate license
                if current_user.role and current_user.role.name == 'Admin':
                    # Allow admin to access admin routes
                    if request.path.startswith('/admin'):
                        return None
                    flash('El sistema no tiene una licencia válida. Por favor active una licencia.', 'warning')
                    return redirect(url_for('main.admin_settings_page'))
                else:
                    # Non-admin users see a blocking message
                    from flask import render_template_string
                    return render_template_string('''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Sistema Bloqueado</title>
                        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                    </head>
                    <body class="bg-light">
                        <div class="container mt-5">
                            <div class="row justify-content-center">
                                <div class="col-md-6">
                                    <div class="card shadow">
                                        <div class="card-body text-center py-5">
                                            <i class="fa-solid fa-lock text-danger" style="font-size: 4rem;"></i>
                                            <h3 class="mt-4">Sistema Bloqueado</h3>
                                            <p class="text-muted">El sistema no tiene una licencia activa.</p>
                                            <p>Por favor, contacte al administrador del sistema.</p>
                                            <a href="{{ url_for('auth.logout') }}" class="btn btn-secondary mt-3">
                                                <i class="fa-solid fa-sign-out-alt me-2"></i>Cerrar Sesión
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
                    </body>
                    </html>
                    '''), 403
        except Exception as e:
            app.logger.warning('Error checking license in middleware: %s', e)
            # Allow access if there's an error checking (avoid blocking users on DB issues)
            pass
        
        return None

    # User loader for Flask-Login
    from .models import User, Role, SystemNotification, Task, Project, SystemSettings

    @login_manager.user_loader
    def load_user(user_id):
        try:
            uid = int(user_id)
            # Use db.session.get() to get a session-bound instance
            return db.session.get(User, uid)
        except Exception as e:
            app.logger.debug('load_user error for user_id=%s: %s', user_id, e)
            return None

    # Filtro personalizado para fechas en español
    @app.template_filter('fecha_es')
    def fecha_es_filter(date, formato='corto'):
        if not date:
            return 'N/A'
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        meses_largo = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        if formato == 'largo':
            return f"{date.day} de {meses_largo[date.month - 1]} {date.year}"
        elif formato == 'corto_año':
            return f"{date.day} {meses[date.month - 1]} {date.year}"
        elif formato == 'completo':
            return f"{dias[date.weekday()]}, {date.day} {meses[date.month - 1]} {date.year}"
        elif formato == 'dia_semana':
            return dias[date.weekday()]
        else:  # corto
            return f"{date.day} {meses[date.month - 1]}"

    # Filtro para formatear fechas según configuración del sistema
    @app.template_filter('sys_date')
    def sys_date_filter(date):
        if not date:
            return 'N/A'
        date_format = SystemSettings.get('date_format', 'DD/MM/YYYY')
        if date_format == 'DD/MM/YYYY':
            return date.strftime('%d/%m/%Y')
        elif date_format == 'MM/DD/YYYY':
            return date.strftime('%m/%d/%Y')
        elif date_format == 'YYYY-MM-DD':
            return date.strftime('%Y-%m-%d')
        return date.strftime('%d/%m/%Y')
    
    # Filtro para formatear hora según configuración del sistema
    @app.template_filter('sys_time')
    def sys_time_filter(time):
        if not time:
            return 'N/A'
        time_format = SystemSettings.get('time_format', '24h')
        if time_format == '12h':
            return time.strftime('%I:%M %p')
        return time.strftime('%H:%M')
    
    # Filtro para formatear moneda
    @app.template_filter('currency')
    def currency_filter(value, show_symbol=True):
        if value is None:
            return 'N/A'
        currency = SystemSettings.get('default_currency', 'USD')
        symbols = {
            'USD': '$', 'EUR': '€', 'GBP': '£', 'MXN': '$', 
            'COP': '$', 'ARS': '$', 'BRL': 'R$', 'CLP': '$',
            'PEN': 'S/', 'PYG': '₲'
        }
        symbol = symbols.get(currency, currency + ' ')
        try:
            formatted = f"{float(value):,.2f}"
            if show_symbol:
                return f"{symbol}{formatted}"
            return formatted
        except (ValueError, TypeError):
            return str(value)

    # Filtro de traducción
    @app.template_filter('naive')
    def naive_dt_filter(dt):
        """Strip tzinfo so templates can safely compare datetimes."""
        if dt is None:
            return None
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    @app.template_filter('t')
    def translate_filter(key):
        from .translations import t
        return t(key)
    
    # Función de traducción disponible en templates
    @app.context_processor
    def inject_translate_function():
        from .translations import t, TRANSLATIONS
        lang = SystemSettings.get('language', 'es')
        return {
            '_': lambda key: t(key, lang),
            't': lambda key: t(key, lang),
            'translations': TRANSLATIONS.get(lang, TRANSLATIONS['es'])
        }

    # Context processor to inject global template variables
    @app.context_processor
    def inject_global_vars():
        from flask_login import current_user
        from .auth.decorators import _get_user_from_session
        from flask import url_for
        from werkzeug.routing import BuildError
        from .services import license_service
        # Prefer a DB-bound user object for templates to avoid accessing detached proxy attributes
        user = _get_user_from_session() or current_user
        
        # Check license status (cached for performance)
        try:
            license_status = license_service.check_license_status()
            license_valid = license_status.get('is_valid', False)
        except Exception as e:
            app.logger.warning('Error checking license status: %s', e)
            license_valid = False
            license_status = {'has_license': False, 'is_valid': False}
        
        # helper for validating that a logo path actually corresponds to a file in uploads
        def _validate_logo(lp):
            if not lp:
                return None
            rel = lp.lstrip('/')
            parts = rel.split('/')
            if parts and parts[0] == 'uploads':
                parts = parts[1:]
            fs = os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), *parts)
            return lp if os.path.exists(fs) else None

        context = {
            'current_user': user,
            'available_clients': [], 
            'unread_notifications_count': 0, 
            'pending_approvals_count': 0,
            # License status
            'license_valid': license_valid,
            'license_status': license_status, 
            # System settings (branding)
            # Use org_name if set, otherwise fall back to app_name, then 'BridgeWork'
            'sys_app_name': SystemSettings.get('org_name') or SystemSettings.get('app_name', 'BridgeWork'),
            'sys_app_subtitle': SystemSettings.get('app_subtitle', 'Project Manager'),
            'sys_primary_color': SystemSettings.get('primary_color', '#E86A33'),
            'sys_secondary_color': SystemSettings.get('secondary_color', '#6c757d'),
            'sys_sidebar_color': SystemSettings.get('sidebar_color', '#1a1d29'),
            # if logo_path points to missing file, ignore so frontend shows default
            'sys_logo_path': _validate_logo(SystemSettings.get('logo_path')),
            'sys_favicon_path': SystemSettings.get('favicon_path'),
            # Content settings
            'sys_footer_text': SystemSettings.get('footer_text', ''),
            'sys_copyright_text': SystemSettings.get('copyright_text', '© 2025 BridgeWork'),
            'sys_support_email': SystemSettings.get('support_email', ''),
            'sys_support_phone': SystemSettings.get('support_phone', ''),
            # General settings
            'sys_default_currency': SystemSettings.get('default_currency', 'USD'),
            'sys_language': SystemSettings.get('language', 'es'),
            # Global alert banner (visible in header if enabled)
            # Normalize stored value which may be string or boolean
            'sys_global_alert_enabled': (lambda v: (v.lower() not in ('false', '0', 'no')) if isinstance(v, str) else bool(v))(
                SystemSettings.get('global_alert_enabled', 'false')
            ),
            'sys_global_alert_message': SystemSettings.get('global_alert_message', ''),
            'sys_portfolio_enabled': (lambda v: (v.lower() not in ('false', '0', 'no')) if isinstance(v, str) else bool(v))(
                SystemSettings.get('portfolio_enabled', 'true')
            ),
            'sys_budget_tracking_enabled': (lambda v: (v.lower() not in ('false', '0', 'no')) if isinstance(v, str) else bool(v))(
                SystemSettings.get('budget_tracking_enabled', 'true')
            ),
            'sys_risks_enabled': (lambda v: (v.lower() not in ('false', '0', 'no')) if isinstance(v, str) else bool(v))(
                SystemSettings.get('risks_enabled', 'true')
            ),
            # Utility: safe url_for that returns '#' if endpoint can't be built (prevents BuildError in templates)
            'safe_url_for': lambda endpoint, **kwargs: _safe_url_for(endpoint, **kwargs)
        }

        def _safe_url_for(endpoint, **kwargs):
            try:
                return url_for(endpoint, **kwargs)
            except Exception as e:
                # Catch BuildError and other url_for related RuntimeErrors (e.g., no SERVER_NAME in non-request contexts)
                app.logger.warning('safe_url_for: could not build endpoint %s: %s', endpoint, e)
                return '#'

        if current_user.is_authenticated:
            try:
                context['unread_notifications_count'] = SystemNotification.query.filter_by(
                    user_id=current_user.id, 
                    is_read=False
                ).count()

                # Para usuarios internos, mostrar clientes disponibles
                if current_user.is_internal:
                    client_role = Role.query.filter_by(name='Cliente').first()
                    if client_role:
                        context['available_clients'] = User.query.filter_by(role_id=client_role.id).order_by(User.first_name).all()
                else:
                    # Para clientes, contar aprobaciones pendientes: tareas en sus proyectos O tareas asignadas directamente al cliente
                    client_projects = Project.query.filter(Project.clients.contains(current_user)).all()
                    project_ids = [p.id for p in client_projects]
                    # If client has no projects, avoid empty IN() by using a sentinel that doesn't match
                    if not project_ids:
                        project_ids = [-1]
                    # Count tasks that are completed, pending approval, AND either belong to a client project (and are externally visible) OR are assigned to this client
                    context['pending_approvals_count'] = Task.query.filter(
                        Task.status == 'COMPLETED',
                        Task.requires_approval == True,
                        ((Task.approval_status.is_(None) & (Task.requires_approval == True)) | (func.lower(Task.approval_status) == 'pending')),
                        (
                            (Task.project_id.in_(project_ids) & (Task.is_external_visible == True))
                            | (Task.assigned_client_id == current_user.id)
                        )
                    ).count()
            except Exception as e:
                # Log and fall back to safe defaults to avoid breaking template rendering
                app.logger.exception('Error in inject_global_vars: %s', e)
                context['unread_notifications_count'] = 0
                context['available_clients'] = []
                context['pending_approvals_count'] = 0
        
        # Compute DB name for display in UI footer/sidebar
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_uri)
            db_name = parsed.path.lstrip('/') or parsed.netloc
        except Exception:
            db_name = db_uri
        context['sys_db_name'] = db_name

        # Ensure we return the context dict for Flask to update the template context
        return context
    # Additional blueprints will be registered here

    return app
