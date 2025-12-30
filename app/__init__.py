import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_object="config.DevConfig"):
    # Load environment variables from .env if present (dev convenience)
    load_dotenv()
    # Determine the absolute path to the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    static_folder_path = os.path.join(project_root, 'static')

    app = Flask(__name__, static_folder=static_folder_path)
    app.config.from_object(config_object)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, inicia sesión para continuar.'
    login_manager.login_message_category = 'warning'

    # Initialize metrics helper (Prometheus if available, else simple counters)
    from .metrics import Metrics
    app.metrics = Metrics(app)

    # Provide a fallback in app.extensions for code that uses simple counters
    app.extensions.setdefault('metrics', {})
    app.extensions['metrics'].setdefault('alerts_sent', 0)

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

    # User loader for Flask-Login
    from .models import User, Role, SystemNotification, Task, Project, SystemSettings

    @login_manager.user_loader
    def load_user(user_id):
        try:
            uid = int(user_id)
            user = User.query.get(uid)
            print('DEBUG load_user: user_id=', user_id, 'found=', bool(user))
            return user
        except Exception as e:
            print('DEBUG load_user error:', e)
            return None

    # Filtro personalizado para fechas en español
    @app.template_filter('fecha_es')
    def fecha_es_filter(date, formato='corto'):
        if not date:
            return 'N/A'
        meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        meses_largo = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        if formato == 'largo':
            return f"{date.day} de {meses_largo[date.month - 1]} {date.year}"
        elif formato == 'corto_año':
            return f"{date.day} {meses[date.month - 1]} {date.year}"
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
        context = {
            'available_clients': [], 
            'unread_notifications_count': 0, 
            'pending_approvals_count': 0,
            # System settings (branding)
            'sys_app_name': SystemSettings.get('app_name', 'BridgeWork'),
            'sys_app_subtitle': SystemSettings.get('app_subtitle', 'Project Manager'),
            'sys_primary_color': SystemSettings.get('primary_color', '#0d6efd'),
            'sys_secondary_color': SystemSettings.get('secondary_color', '#6c757d'),
            'sys_sidebar_color': SystemSettings.get('sidebar_color', '#1a1d29'),
            'sys_logo_path': SystemSettings.get('logo_path'),
            'sys_favicon_path': SystemSettings.get('favicon_path'),
            # Content settings
            'sys_footer_text': SystemSettings.get('footer_text', ''),
            'sys_copyright_text': SystemSettings.get('copyright_text', '© 2025 BridgeWork'),
            'sys_support_email': SystemSettings.get('support_email', ''),
            'sys_support_phone': SystemSettings.get('support_phone', ''),
            # General settings
            'sys_default_currency': SystemSettings.get('default_currency', 'USD'),
            'sys_language': SystemSettings.get('language', 'es'),
            'sys_timezone': SystemSettings.get('timezone', 'America/Asuncion'),
        }
        
        if current_user.is_authenticated:
            # Notificaciones no leídas
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
                # Para clientes, contar aprobaciones pendientes
                client_projects = Project.query.filter(Project.clients.contains(current_user)).all()
                if client_projects:
                    project_ids = [p.id for p in client_projects]
                    context['pending_approvals_count'] = Task.query.filter(
                        Task.project_id.in_(project_ids),
                        Task.status == 'COMPLETED',
                        Task.is_external_visible == True,
                        Task.approval_status == 'PENDING'
                    ).count()
        
        return context

    # Additional blueprints will be registered here

    return app
