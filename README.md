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

## 🟢 Novedades (2026-01-20)

Se añadieron las siguientes mejoras al módulo de Reportes y exportación:

- **Reportes por Proyecto**
  - Se agregó la columna **"Atraso (días)"** en el resumen por proyecto y en la exportación XLSX. El cálculo es simple: para tareas no completadas `max(0, hoy - due_date)`; tareas completadas reportan `0`.
  - La exportación **XLSX** incluye ahora la columna de atraso y se genera con `openpyxl`.
- **KPIs por Proyecto**
  - Al seleccionar un proyecto en la página de reportes, las tarjetas (cards) muestran métricas **del proyecto** (tareas totales y completadas, presupuesto, horas usadas y horas por usuario en los últimos 30 días) en lugar de los valores globales.
- **Tests**
  - `tests/test_reports_project_export.py` fue actualizado para validar la nueva columna y un valor de atraso de ejemplo.
  - Se añadió `tests/test_reports_project_cards.py` para asegurar que las tarjetas KPI reflejen las métricas del proyecto seleccionado.

**Notas operativas:**
- Asegúrate de que `openpyxl` esté instalado (`requirements.txt`) para habilitar exportación XLSX.
- Si al ejecutar tests ves `ModuleNotFoundError: No module named 'app'`, es probable que tu entorno de pruebas no tenga `PYTHONPATH`/runner configurado; esto es un issue de entorno y no de la lógica del repositorio.

---
