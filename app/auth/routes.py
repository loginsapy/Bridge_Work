from flask import render_template, redirect, url_for, request, flash, session, current_app
from werkzeug.security import check_password_hash
from . import auth_bp
from app.models import User
from .utils import get_msal_app
from flask_login import login_user, logout_user
from app import db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'local':
            email = request.form.get('email') or ''
            password = request.form.get('password') or ''
            # Normalizar email para evitar problemas por mayúsculas/espacios
            email_norm = email.strip().lower()
            user = User.query.filter_by(email=email_norm).first()
            current_app.logger.info(f"Local login attempt: email={email!r} normalized={email_norm!r} user_found={bool(user)} pwd_hash_present={bool(getattr(user,'password_hash',None))}")
            if user and user.password_hash:
                try:
                    pwd_hash = user.password_hash
                    hash_prefix = pwd_hash.split(':', 1)[0] if pwd_hash else None
                    current_app.logger.info(f"Stored password hash prefix for {email_norm!r}: {hash_prefix}, len={len(pwd_hash)}")
                    check = user.check_password(password)
                except Exception as e:
                    current_app.logger.exception('Password check failed')
                    check = False
                current_app.logger.info(f"Password check result for {email_norm!r}: {check} (hash_prefix={hash_prefix})")
            else:
                check = False

            if check:
                login_user(user)
                flash('Inicio de sesión correcto.', 'success')
                # Redirección post-login
                next_url = request.args.get('next') or session.pop('post_auth_redirect', None) or url_for('main.projects')
                return redirect(next_url)
            # Detallar el motivo cuando sea posible
            if user and not user.password_hash:
                flash('Este usuario no tiene contraseña local (solo SSO).', 'warning')
            elif user and user.password_hash and not check:
                flash('Credenciales inválidas (contraseña incorrecta).', 'danger')
            else:
                flash('Credenciales inválidas', 'danger')
        elif action == 'sso':
            # Inicio de flujo SSO con MSAL
            msal_app = get_msal_app()
            if not msal_app:
                flash('SSO no configurado. Contáctate con tu administrador.', 'warning')
                return redirect(url_for('auth.login'))
            try:
                scopes = current_app.config.get('AZURE_SCOPES', ['openid', 'profile', 'email'])
                redirect_uri = url_for('auth.callback', _external=True)
                try:
                    auth_url = msal_app.get_authorization_request_url(scopes, redirect_uri=redirect_uri)
                    scopes_used = scopes
                except ValueError as e:
                    # Some Azure tenants forbid passing certain reserved scope names; retry with a safer default
                    current_app.logger.warning(f"SSO scopes rejected, retrying with fallback. error={e}")
                    fallback = current_app.config.get('AZURE_FALLBACK_SCOPES', ['User.Read'])
                    auth_url = msal_app.get_authorization_request_url(fallback, redirect_uri=redirect_uri)
                    scopes_used = fallback
                    flash('Nota: la configuración SSO ha requerido un ajuste automático de scopes.', 'warning')

                # Optionally store state in session for validation
                session['oauth_state'] = True
                # Store desired redirect after auth
                session['post_auth_redirect'] = request.args.get('next') or url_for('main.projects')
                # Remember which scopes were used so callback can reuse them
                session['azure_scopes_used'] = scopes_used
                return redirect(auth_url)
            except ValueError as e:
                flash(f'Error de configuración SSO: {str(e)}', 'danger')
                return redirect(url_for('auth.login'))
    return render_template('auth/login.html')


@auth_bp.route('/callback')
def callback():
    msal_app = get_msal_app()
    if not msal_app:
        flash('SSO no configurado')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('No se recibió código de autorización.')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('auth.callback', _external=True)
    # Reuse the same scopes that were used during the authorization request (fallback stored in session)
    scopes_for_token = session.pop('azure_scopes_used', None) or current_app.config.get('AZURE_SCOPES', ['openid', 'profile', 'email'])
    token_response = msal_app.acquire_token_by_authorization_code(code, scopes=scopes_for_token, redirect_uri=redirect_uri)

    current_app.logger.info(f"token_response: {token_response}")
    claims = (token_response.get('id_token_claims') if isinstance(token_response, dict) else None) or {}
    current_app.logger.info(f"claims: {claims}")
    oid = claims.get('oid') or claims.get('sub')
    email = claims.get('preferred_username') or claims.get('email')
    # Try to get separate name fields first, then fall back to 'name' (full name)
    given = claims.get('given_name') or None
    family = claims.get('family_name') or None
    full_name = claims.get('name') or None

    if not oid:
        flash('No se encontró OID en el token.')
        return redirect(url_for('auth.login'))

    # Helper to split full name into first/last
    def split_full_name(name):
        if not name:
            return (None, None)
        parts = name.strip().split()
        if len(parts) == 1:
            return (parts[0], None)
        return (parts[0], ' '.join(parts[1:]))

    # Determine final first/last values with fallbacks
    first = given
    last = family
    if not first and not last and full_name:
        f, l = split_full_name(full_name)
        first = f
        last = l

    # JIT provisioning
    user = User.query.filter_by(azure_oid=oid).first()
    if not user and email:
        user = User.query.filter_by(email=email).first()
        if user:
            user.azure_oid = oid
            user.is_internal = True
            # Update names if available
            if first and user.first_name != first:
                user.first_name = first
            if last and user.last_name != last:
                user.last_name = last
    if not user:
        user = User(email=email, azure_oid=oid, is_internal=True, first_name=first, last_name=last)
        # For SQLite testing where INTEGER PRIMARY KEY may not be created as autoincrement
        if current_app.config.get('SQLALCHEMY_DATABASE_URI', '').startswith('sqlite'):
            max_id = db.session.query(func.max(User.id)).scalar() or 0
            user.id = int(max_id) + 1
        db.session.add(user)
    else:
        # If user exists (found by oid), ensure names are up-to-date
        changed = False
        if first and user.first_name != first:
            current_app.logger.info(f"Updating first_name for user {user.email}: {user.first_name} -> {first}")
            user.first_name = first
            changed = True
        if last and user.last_name != last:
            current_app.logger.info(f"Updating last_name for user {user.email}: {user.last_name} -> {last}")
            user.last_name = last
            changed = True
        if changed:
            db.session.add(user)

    current_app.logger.info('About to commit user to DB')
    try:
        db.session.flush()
        current_app.logger.info(f'Flushed user id (before commit): {getattr(user, "id", None)}')
        db.session.commit()
        current_app.logger.info('Commit completed')
    except SQLAlchemyError as exc:
        current_app.logger.exception('Error committing user')
        db.session.rollback()
        flash('Error al crear/actualizar usuario')
        return redirect(url_for('auth.login'))

    current_app.logger.info(f'Created/updated user: {user.email} (id={user.id})')
    login_user(user)
    flash('Autenticación SSO correcta.', 'success')
    next_url = session.pop('post_auth_redirect', None) or url_for('main.projects')
    return redirect(next_url)


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('auth.login'))
