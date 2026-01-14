# Gestor de Proyectos y CRM

Proyecto base para el Gestor centralizado descrito en `implementation plan.md`.

Rápido inicio (dev):

- Copia `.env.example` a `.env` y ajusta variables.
- Crea y activa el entorno virtual (PowerShell):
  - `python -m venv .venv`
  - `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (si PowerShell bloquea scripts)
  - `. \.venv\Scripts\Activate.ps1`
  - `pip install -r requirements.txt`
- `docker-compose up --build` (levanta web, postgres y redis)
- `flask db init && flask db migrate && flask db upgrade` para crear las tablas
- `pytest` para ejecutar tests (¡cuidado! Revisa la sección de seguridad de base de datos en `docs/DB-SAFETY.md` antes de ejecutar tests en entornos con DB remota).
