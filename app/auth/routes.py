from flask import render_template, redirect, url_for, request, flash, session, current_app
from werkzeug.security import check_password_hash
from urllib.parse import urlparse, urlencode
from . import auth_bp
from app.models import User, AuditLog, SystemSettings
from .utils import get_msal_app
from flask_login import login_user, logout_user, current_user
from app import db, limiter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from msal import ConfidentialClientApplication
import json
import base64
import secrets
from datetime import datetime
import requests
from msal import PublicClientApplication
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


def is_safe_url(target):
    """Verifica que la URL de redirección sea segura (local al servidor)."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ('', 'http', 'https') and ref_url.netloc == test_url.netloc


def _password_reset_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='local-password-reset')


def generate_password_reset_token(user: User) -> str:
    return _password_reset_serializer().dumps({'user_id': user.id, 'email': user.email})


def verify_password_reset_token(token: str, max_age: int = 3600) -> User | None:
    try:
        data = _password_reset_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    user = User.query.get(data.get('user_id')) if data else None
    if not user or user.email != data.get('email'):
        return None
    if not user.password_hash or not user.is_active:
        return None
    return user


def send_password_reset_email(user: User) -> bool:
    from app.notifications.provider import get_provider

    provider = get_provider(current_app)
    token = generate_password_reset_token(user)
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    app_name = SystemSettings.get('app_name', 'BridgeWork')
    support_email = SystemSettings.get('support_email', '')
    html = render_template(
        'auth/password_reset_email.html',
        user=user,
        reset_url=reset_url,
        app_name=app_name,
        support_email=support_email,
    )
    text = (
        f'Hola {user.first_name or user.email},\n\n'
        f'Recibimos una solicitud para restablecer tu contraseña en {app_name}.\n'
        f'Usa este enlace dentro de la próxima hora:\n{reset_url}\n\n'
        'Si no solicitaste este cambio, puedes ignorar este mensaje.'
    )
    return provider.send_email(user.id, f'{app_name}: restablecer contraseña', text, html=html)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("15/minute", methods=["POST"])
def login():
    """Login page with local auth + Microsoft SSO"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    local_auth_enabled = SystemSettings.get('enable_local_auth', True)
    azure_auth_enabled = SystemSettings.get('enable_azure_auth', True)

    # Safety net: never lock everyone out — if both are disabled, re-enable local auth
    if not local_auth_enabled and not azure_auth_enabled:
        local_auth_enabled = True

    if request.method == 'POST':
        if not local_auth_enabled:
            flash('El acceso con email y contraseña está deshabilitado. Use Entra ID.', 'warning')
            return redirect(url_for('auth.login'))

        # Handle local login
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Email o contraseña inválidos.', 'danger')
        elif not user.password_hash:
            # Usuario sin contraseña local (probablemente SSO)
            flash('Esta cuenta no tiene contraseña local. Por favor use Entra ID para iniciar sesión.', 'warning')
        elif not user.check_password(password):
            flash('Email o contraseña inválidos.', 'danger')
        elif not user.is_active:
            flash('Tu cuenta está desactivada. Contacta al administrador.', 'danger')
        else:
            # Login exitoso
            login_user(user, remember=request.form.get('remember_me'))
            next_page = request.args.get('next')
            if not next_page or not is_safe_url(next_page):
                next_page = url_for('main.dashboard')
            flash(f'¡Bienvenido {user.name}!', 'success')
            return redirect(next_page)

    # Azure button is shown only when configured AND enabled in settings
    microsoft_enabled = bool(current_app.config.get('AZURE_CLIENT_ID')) and bool(azure_auth_enabled)

    return render_template('auth/login.html',
                           microsoft_enabled=microsoft_enabled,
                           local_auth_enabled=bool(local_auth_enabled))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5/minute", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        user = User.query.filter(func.lower(User.email) == email).first() if email else None

        if user and user.password_hash and user.is_active:
            try:
                send_password_reset_email(user)
            except Exception as exc:
                current_app.logger.exception('Failed to send password reset email: %s', exc)

        flash('Si el correo corresponde a un usuario local activo, enviaremos instrucciones para restablecer la contraseña.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10/minute", methods=["POST"])
def reset_password(token):
    if current_user.is_authenticated:
        logout_user()

    user = verify_password_reset_token(token)
    if not user:
        flash('El enlace de restablecimiento es inválido o ha expirado.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if len(password) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres.', 'danger')
        elif password != confirm_password:
            flash('La confirmación de contraseña no coincide.', 'danger')
        else:
            user.set_password(password)
            try:
                audit = AuditLog(
                    entity_type='User',
                    entity_id=user.id,
                    action='UPDATE',
                    user_id=user.id,
                    changes={'password_reset': {'old': None, 'new': 'completed'}}
                )
                db.session.add(audit)
                db.session.commit()
                flash('Tu contraseña fue actualizada. Ya puedes iniciar sesión.', 'success')
                return redirect(url_for('auth.login'))
            except SQLAlchemyError:
                db.session.rollback()
                flash('No fue posible actualizar la contraseña. Intenta nuevamente.', 'danger')

    return render_template('auth/reset_password.html', token=token, reset_user=user)


@auth_bp.route('/login/microsoft')
def login_microsoft():
    """Initiate Microsoft OAuth flow"""
    try:
        if current_user.is_authenticated:
            logout_user()

        if not current_app.config.get('AZURE_CLIENT_ID'):
            flash('Microsoft authentication is not configured', 'danger')
            return redirect(url_for('auth.login'))

        if not SystemSettings.get('enable_azure_auth', True):
            flash('El acceso con Entra ID está deshabilitado por el administrador.', 'warning')
            return redirect(url_for('auth.login'))

        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state

        next_page = request.args.get('next')
        if next_page:
            session['oauth_next'] = next_page

        redirect_uri = current_app.config.get('AZURE_REDIRECT_URI') or url_for('auth.callback', _external=True)

        # Use MSAL to build the authorization URL — it handles nonce,
        # response_mode and scope formatting correctly for the tenant.
        client = ConfidentialClientApplication(
            client_id=current_app.config['AZURE_CLIENT_ID'],
            client_credential=current_app.config['AZURE_CLIENT_SECRET'],
            authority=current_app.config['AZURE_AUTHORITY'],
        )
        auth_url = client.get_authorization_request_url(
            scopes=current_app.config['AZURE_SCOPES'],
            state=state,
            redirect_uri=redirect_uri,
        )
        return redirect(auth_url)

    except Exception as e:
        current_app.logger.exception(f'Microsoft login initiation error: {e}')
        flash(f'Error de autenticación: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/callback', methods=['GET', 'POST'])
def callback():
    """Handle Microsoft Entra ID OAuth callback"""
    try:
        # Enforce admin setting — reject the callback if Azure auth is disabled
        if not SystemSettings.get('enable_azure_auth', True):
            flash('El acceso con Entra ID está deshabilitado por el administrador.', 'warning')
            return redirect(url_for('auth.login'))

        code = request.values.get('code')
        state = request.values.get('state')
        error = request.values.get('error')
        error_description = request.values.get('error_description')

        # Handle errors from Microsoft
        if error:
            flash(f'Error de autenticación: {error_description or error}', 'danger')
            return redirect(url_for('auth.login'))

        if not code:
            flash('No se recibió código de autorización.', 'danger')
            return redirect(url_for('auth.login'))

        # Verify state parameter (CSRF protection)
        stored_state = session.pop('oauth_state', None)
        if not state or state != stored_state:
            flash('Invalid state parameter. CSRF attack prevented.', 'danger')
            return redirect(url_for('auth.login'))

        redirect_uri = current_app.config.get('AZURE_REDIRECT_URI') or url_for('auth.callback', _external=True)
        
        # Initialize MSAL client
        client = ConfidentialClientApplication(
            client_id=current_app.config['AZURE_CLIENT_ID'],
            client_credential=current_app.config['AZURE_CLIENT_SECRET'],
            authority=current_app.config['AZURE_AUTHORITY'],
        )
        
        # Get token using authorization code
        result = client.acquire_token_by_authorization_code(
            code=code,
            scopes=current_app.config['AZURE_SCOPES'],
            redirect_uri=current_app.config.get('AZURE_REDIRECT_URI') or url_for('auth.callback', _external=True)
        )
        
        if 'error' in result:
            flash(f'Error en la adquisición del token: {result.get("error_description", "Error desconocido")}', 'danger')
            return redirect(url_for('auth.login'))
        
        # Extract user info from token
        access_token = result.get('access_token')
        id_token = result.get('id_token')
        
        # Decode ID token to get user info (JWT format)
        if id_token:
            # ID token is JWT: header.payload.signature
            parts = id_token.split('.')
            if len(parts) == 3:
                # Decode payload (add padding if needed)
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                try:
                    user_info = json.loads(base64.urlsafe_b64decode(payload))
                except Exception as e:
                    current_app.logger.error(f'Error decoding JWT: {e}')
                    user_info = {}
            else:
                user_info = {}
        else:
            user_info = {}
        
        # Extract claims
        azure_oid = user_info.get('oid')  # Object ID (unique identifier)
        email = user_info.get('email') or user_info.get('upn') or user_info.get('preferred_username')  # Email or UPN
        name = user_info.get('name', '')
        given_name = user_info.get('given_name', '')
        family_name = user_info.get('family_name', '')
        azure_department = (user_info.get('department') or '').strip()  # Azure AD department claim
        
        current_app.logger.info(f'OAuth user_info: oid={azure_oid}, email={email}, name={name}')
        
        if not email:
            current_app.logger.error(f'No email found in token. user_info keys: {user_info.keys()}')
            flash('No se encontró email en la respuesta de Microsoft', 'danger')
            return redirect(url_for('auth.login'))
        
        # Find or create user
        user = User.query.filter_by(azure_oid=azure_oid).first()
        
        if not user:
            # Check if email already exists (local account)
            user = User.query.filter_by(email=email).first()
            
            if user and user.azure_oid:
                # User already has Azure login
                pass
            elif user and not user.azure_oid:
                # Upgrade local account to Azure SSO
                user.azure_oid = azure_oid
            else:
                # Create new user from Azure
                user = User(
                    email=email,
                    azure_oid=azure_oid,
                    first_name=given_name or name.split()[0] if name else '',
                    last_name=family_name or (name.split()[-1] if len(name.split()) > 1 else ''),
                    is_internal=True,  # Azure users are internal by default
                    is_active=True
                )
                db.session.add(user)
        else:
            # Update user info if needed
            if given_name:
                user.first_name = given_name
            if family_name:
                user.last_name = family_name

        # Sync department from Entra ID claim if present
        if azure_department:
            try:
                from app.models import Department
                dept = Department.query.filter_by(name=azure_department).first()
                if not dept:
                    dept = Department(name=azure_department)
                    db.session.add(dept)
                    db.session.flush()
                user.department_id = dept.id
                current_app.logger.info(f'User department synced from Entra ID: {azure_department}')
            except Exception as e:
                current_app.logger.warning(f'Failed to sync department from Entra ID: {e}')

        try:
            db.session.commit()
            current_app.logger.info(f'User saved/updated: id={user.id}, email={user.email}')

            # Try to fetch the user's Entra ID profile photo (delegated token available right after login)
            try:
                if access_token:
                    graph_resp = requests.get(
                        'https://graph.microsoft.com/v1.0/me/photo/$value',
                        headers={'Authorization': f'Bearer {access_token}'},
                        timeout=5
                    )
                    if graph_resp.status_code == 200 and graph_resp.content:
                        user.photo = graph_resp.content
                        user.photo_mime = graph_resp.headers.get('Content-Type', 'image/jpeg') or 'image/jpeg'
                        user.photo_updated_at = datetime.now()
                        db.session.add(user)
                        db.session.commit()
                        current_app.logger.info(f'User photo saved for user id={user.id}')
                    else:
                        current_app.logger.debug(f'No photo returned for Azure user oid={azure_oid} (status={graph_resp.status_code})')
            except Exception as e:
                current_app.logger.warning(f'Failed to fetch/save Azure profile photo: {e}')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception(f'Database error saving user: {e}')
            flash('Error al guardar usuario en la base de datos', 'danger')
            return redirect(url_for('auth.login'))
        
        # Log the user in
        login_user(user, remember=True)
        current_app.logger.info(f'User logged in successfully: {user.email}')
        
        # Redirect to original page or dashboard
        next_page = session.get('oauth_next', url_for('main.dashboard'))
        session.pop('oauth_next', None)
        
        flash(f'Bienvenido {user.first_name or user.email}!', 'success')
        return redirect(next_page)
        
    except Exception as e:
        current_app.logger.exception(f'Error en el callback de OAuth: {e}')
        flash(f'Error de autenticación: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('auth.login'))
