from flask import render_template, redirect, url_for, request, flash, session, current_app
from werkzeug.security import check_password_hash
from . import auth_bp
from app.models import User
from .utils import get_msal_app
from flask_login import login_user, logout_user, current_user
from app import db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from flask import redirect, url_for, session, request
from msal import ConfidentialClientApplication
import json
import base64
import secrets
from msal import PublicClientApplication


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with local auth + Microsoft SSO"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        # Handle local login
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember_me'))
            next_page = request.args.get('next')
            if not next_page or url_has_allowed_host_and_scheme(next_page):
                next_page = url_for('main.dashboard')
            flash(f'Welcome {user.name}!', 'success')
            return redirect(next_page)
        else:
            flash('Invalid email or password.', 'danger')
    
    # For GET requests, prepare OAuth button
    microsoft_enabled = bool(current_app.config.get('AZURE_CLIENT_ID'))
    
    return render_template('auth/login.html', microsoft_enabled=microsoft_enabled)


@auth_bp.route('/login/microsoft')
def login_microsoft():
    """Initiate Microsoft OAuth flow"""
    try:
        # Logout any existing user to avoid session conflicts
        if current_user.is_authenticated:
            logout_user()
        
        if not current_app.config.get('AZURE_CLIENT_ID'):
            flash('Microsoft authentication is not configured', 'danger')
            return redirect(url_for('auth.login'))
        
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        # Store the page user was trying to access (if provided)
        next_page = request.args.get('next')
        if next_page:
            session['oauth_next'] = next_page
        
        # Initialize MSAL client
        client = ConfidentialClientApplication(
            client_id=current_app.config['AZURE_CLIENT_ID'],
            client_credential=current_app.config['AZURE_CLIENT_SECRET'],
            authority=current_app.config['AZURE_AUTHORITY']
        )
        
        # Generate authorization URL
        auth_url = client.get_authorization_request_url(
            scopes=current_app.config['AZURE_SCOPES'],
            state=state,
            redirect_uri=url_for('auth.callback', _external=True)
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        current_app.logger.exception(f'Microsoft login initiation error: {e}')
        flash(f'Authentication error: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/callback')
def callback():
    """Handle Microsoft Entra ID OAuth callback"""
    try:
        # Get authorization code from query params
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        error_description = request.args.get('error_description')
        
        # Handle errors from Microsoft
        if error:
            flash(f'Error de autenticación: {error_description or error}', 'danger')
            return redirect(url_for('auth.login'))
        
        if not code:
            flash('No se recibió código de autorización.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Verify state parameter (CSRF protection)
        stored_state = session.get('oauth_state')
        if not state or state != stored_state:
            flash('Invalid state parameter. CSRF attack prevented.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Initialize MSAL client
        client = ConfidentialClientApplication(
            client_id=current_app.config['AZURE_CLIENT_ID'],
            client_credential=current_app.config['AZURE_CLIENT_SECRET'],
            authority=current_app.config['AZURE_AUTHORITY']
        )
        
        # Get token using authorization code
        result = client.acquire_token_by_authorization_code(
            code=code,
            scopes=current_app.config['AZURE_SCOPES'],
            redirect_uri=url_for('auth.callback', _external=True)
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
        
        try:
            db.session.commit()
            current_app.logger.info(f'User saved/updated: id={user.id}, email={user.email}')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.exception(f'Database error saving user: {e}')
            flash('Error al guardar usuario en la base de datos', 'danger')
            return redirect(url_for('auth.login'))
        
        # Log the user in
        login_user(user, remember=True)
        current_app.logger.info(f'User logged in successfully: {user.email}')
        
        # Clear OAuth session data
        session.pop('oauth_state', None)
        
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
