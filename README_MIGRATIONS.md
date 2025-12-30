# Migraciones (Flask-Migrate / Alembic)

1. Exporta la app: `export FLASK_APP=run.py` (Windows: `set FLASK_APP=run.py`).
2. Inicializa la carpeta de migraciones (solo la primera vez): `flask db init`.
3. Crea una migración: `flask db migrate -m "Create initial schema"`.
4. Aplica migraciones: `flask db upgrade`.

Nota: asegúrate de que `DATABASE_URL` apunte a tu base de datos (p.ej. el servicio `db` en `docker-compose`).
