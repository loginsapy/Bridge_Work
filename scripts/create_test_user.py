"""Script simple para crear/actualizar un usuario local (desarrollo).

- Imprime la URI de la DB para confirmar a qué base de datos está apuntando (Postgres/SQLite).
- Si el usuario ya existe, actualiza su contraseña en lugar de intentar insertarlo de nuevo.
"""
from app import create_app, db
from app.models import User

app = create_app('config.DevConfig')

with app.app_context():
    # Mostrar qué URI de BD está usando la app para evitar confusiones
    print('Usando DB:', app.config.get('SQLALCHEMY_DATABASE_URI'))

    email = 'client@example.com'
    password = 'password'

    # Normalizar email por seguridad
    email_norm = (email or '').strip().lower()

    user = User.query.filter_by(email=email_norm).first()
    if user:
        print('Usuario existente encontrado:', user.email, '-> Actualizando contraseña.')
        user.set_password(password)
        db.session.add(user)
    else:
        u = User(email=email_norm, is_internal=False)
        u.set_password(password)
        db.session.add(u)
        print('Usuario creado:', email_norm)

    try:
        db.session.commit()
        print('Commit completado correctamente')
    except Exception as e:
        db.session.rollback()
        print('Error al commitear usuario:', e)
