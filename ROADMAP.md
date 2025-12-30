# ROADMAP: Plan de ejecución — Gestor de Proyectos y CRM 🚀

## Resumen ejecutivo
Este documento define el plan práctico para implementar el Gestor centralizado (backend Flask + PostgreSQL + Azure Entra ID + Celery). Incluye fases, entregables, estimados y criterios de aceptación (DoD) para cada etapa.

---

## Etapas y entregables (ordenadas)

1) **Scaffold y CI** ✅
   - Entregables: Estructura `app/`, `create_app`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `CI (GitHub Actions)`, test básico.
   - Estado: **Completado**
   - Criterio de aceptación: Repositorio arrancable con `docker-compose up --build` y `pytest` verde.
   - Nota: Entorno virtual local **`.venv`** creado y dependencias instaladas (`pip install -r requirements.txt`).

2) **Modelos y migraciones** ✅
   - Entregables: `app/models.py` (User, Project, Task, TimeEntry, NotificationRule, AlertLog), `README_MIGRATIONS.md`.
   - Estado: **Completado**
   - Criterio de aceptación: Migraciones aplicables (`flask db migrate && flask db upgrade`) y modelos reflejados en DB.

3) **Autenticación híbrida (Azure OIDC + Local)** ✅ (Completado)
   - Entregables: Integración MSAL (OIDC), rutas `/auth/login` y `/auth/callback`, JIT provisioning (crear/ligar `User`), decoradores `@client_required` y `@internal_required`.
   - Estimado: 2–4 días (implementación + tests de integración con mocks).
   - Criterio de aceptación: Usuarios internos pueden SSO; JIT crea o liga usuario; tests que mockean `msal` pasan.
   - Nota: Implementación completa y test `tests/test_auth_oidc.py` pasa en entorno local.

4) **Blueprints y APIs CRUD** ✅ **(Completado)**
   - Entregables: `auth_bp`, `admin_bp`, `portal_bp`, `api_bp`, endpoints CRUD para `projects`, `tasks`, `time_entries`, validación (Marshmallow), y paginación/filtros.
   - Estimado: 4–6 días.
   - Criterio de aceptación: Endpoints documentados, OpenAPI (`docs/openapi.yaml`) disponible, y cubiertos por tests (unitarios y de integración ligera).
   - Nota de implementación:
     - `app/api/routes.py`: CRUD + validación con `app/api/schemas.py` (Marshmallow).
     - Paginación y filtros añadidos a list endpoints (`page`, `per_page`, `status`, `project_id`, `assigned_to_id`, `task_id`, `user_id`).
     - Tests: `tests/test_api_projects.py`, `tests/test_api_tasks.py`, `tests/test_api_timeentries.py`, `tests/test_api_validation.py`, `tests/test_api_pagination.py` — **todas pasan** localmente.
     - OpenAPI spec: `docs/openapi.yaml` (ejemplos y esquemas de request/response).
     - Próximo sub-tarea: implementar reglas de visibilidad y autorización (en progreso).

5) **Motor de alertas (Celery + Redis)** ✅ **(Completado)**
   - Entregables: Worker Celery, `beat` schedule diario, agrupación de notificaciones, `alert_logs`, integración opcional con SendGrid/Azure.
   - Estado: **Completado** — scaffolding, periodic task, grouping, idempotency and sending implemented; tests and metrics added.
   - Estimado: 3–5 días.
   - Criterio de aceptación: Tarea periódica ejecutada localmente en `docker-compose` (`worker` + `beat`), grouped notifications sent (stubbed) and stored in `alert_logs`.
   - Acciones realizadas:
     - Añadido `app/celery_app.py` para crear la app Celery a partir de Flask.
     - Tarea `app/tasks/alerts.py` con `generate_alerts` (idempotency window) and dispatch to `alerts.send_grouped_alerts`.
     - `app/tasks/sender.py` implements `send_grouped_alerts` with retry/backoff and Celery autoretry.
     - Providers: `app/notifications/provider.py` (Stub + SendGrid) and templates `app/notifications/templates/` (text & HTML).
     - `run.py` exposes `celery` (so `celery -A run.celery` works).
     - `docker-compose.yml` updated to include `beat` service.
     - Metrics: Prometheus integration via `app/metrics.py`, `/metrics` endpoint exposed and counters incremented on send successes/failures.
     - Monitoring: `app/tasks/monitor.py` implements `check_failed_alerts` and a Celery task `alerts.check_failed_alerts` (scheduled via `beat`) to notify internal admins when failed sends exceed a threshold; tests added.
     - Tests added/updated: `tests/test_alerts.py`, `tests/test_notifications.py`, `tests/test_notifications_templates_and_metrics.py`, `tests/test_metrics_endpoint.py`, `tests/test_monitor.py`.
     - Integration notes: To enable real sending set `EMAIL_PROVIDER=sendgrid` and `SENDGRID_API_KEY` in environment.


6) **Frontend y dashboards** 🔝 **(Prioridad Alta — En progreso)**
   - Entregables: Templates Jinja2 + Bootstrap 5, dashboards interno/cliente con diseño profesional, componentes reutilizables (navbar/sidebar/cards/modals), endpoints para Chart.js (KPIs: uso de presupuesto, burn-down, SV), iconografía (Font Awesome/Feather), y soporte responsive + accesibilidad.
   - Estimado: 4–8 días (inicial + refinamientos de diseño).
   - Estado actual: **En progreso** — paleta del logo extraída y aplicada a `static/css/app.css`; diseño base (navbar/sidebar/cards) implementado y pruebas unitarias básicas verdes.
   - Acciones recientes:
     - Paleta extraída desde `app/static/images/bwlogo.png` y variables CSS añadidas (`--brand`, `--brand-dark`, `--accent`, `--brand-contrast`, `--bg`).
     - Previsualización de la paleta añadida en `dashboard.html`.
     - Mockups pulidos creados en `app/templates/mockups/` (`dashboard_mockup.html`, `project_mockup.html`); estilos en `static/css/mockups.css` y comportamiento de ejemplo en `static/js/mockups.js`.
     - Rutas de previsualización disponibles: `/mock/dashboard` y `/mock/project`.
   - Próximos pasos (prioritarios):
     1. Iterar diseño (tipografía, espaciado, contrastes WCAG AA) y aplicar variantes de color (hover, active, disabled).
     2. Crear 2 mockups: **Dashboard principal** y **Panel de proyecto**; validar responsive y accesibilidad. **Estado: En progreso (creación iniciada — prototipo HTML/CSS en `app/templates/mockups/` y estilos en `app/static/css/mockups.css`).**
     3. Decidir si importamos un tema admin (p.ej. Tabler, AdminLTE) y adaptamos la paleta, o si continuamos con diseño personalizado.
     4. Implementar endpoints y fixtures que alimenten gráficos con datos reales (para QA visual).
   - Criterios de aceptación específicos para esta etapa:
     - UI audit: contraste mínimo WCAG AA para textos y botones importantes.
     - Layouts responsivos en breakpoints comunes (mobile/tablet/desktop).
     - 2 mockups revisados y aprobados por el equipo o por tí.
     - Tests básicos de renderizado de templates y paths estáticos pasan en CI.


7) **Pruebas y mocking**
   - Entregables: Tests unitarios e integración, mocks para `msal`, pruebas para tareas Celery.
   - Estimado: 3–5 días.
   - Criterio de aceptación: Cobertura mínima acordada (p.ej. tests críticos) y pipelines CI que ejecutan tests.

8) **Dockerización & Despliegue (Azure)**
   - Entregables: Optimización de `Dockerfile`, Helm/ARM/Bicep o guías para Azure App Service/ACR, runbook de secrets.
   - Estimado: 2–4 días.
   - Criterio de aceptación: Imagen publicada en registro, despliegue básico en Azure de prueba.

9) **Documentación y runbooks**
   - Entregables: README ampliado, runbooks de incidentes, guía de seguridad y recuperación, documentación de API.
   - Estimado: 2–3 días.
   - Criterio de aceptación: Documentación suficiente para un dev new hire reproducir entorno local.

10) **Integraciones y mejoras futuras (Backlog)**
   - Webhooks de repo/CI, facturación, permisos granular (fine-grained), métricas predictivas.

---

## Dependencias críticas
- Azure: registro de App (Client ID, Client Secret, Redirect URIs) para OIDC.
- Infra: PostgreSQL con JSONB, Redis para broker.
- Secrets: gestionados por Azure Key Vault o variables de entorno en CI/CD.

## Riesgos y mitigaciones
- Riesgo: Exposición accidental de datos a clientes → Mitigación: `is_external_visible` por defecto `False`; tests de autorización y validación por proyecto.
- Riesgo: OIDC misconfigurado → Mitigación: pruebas con mocks y entorno de staging en Azure.

---

## Cronograma sugerido (macro)
- Sprint 0 (1 semana): Scaffold, Models, Migrations, CI (ya completado)
- Sprint 1 (2 semanas): Auth híbrida + tests
- Sprint 2 (2 semanas): APIs CRUD + primeros dashboards
- Sprint 3 (2 semanas): Celery alerts + integración de mails
- Sprint 4 (1–2 semanas): Tests, Docker/Deploy, documentación

(Estimados sujetos a priorización y disponibilidad)

---

## Primeros pasos que ejecutaré ahora
1. Blueprints y CRUD (autenticación ya implementada) — crear endpoints para `projects`, `tasks`, `time_entries` y políticas de visibilidad. **Estado: En progreso.**
2. UI & Diseño (paleta aplicada) — iterar diseño, crear 2 mockups (Dashboard y Panel de proyecto), revisar contrastes y accesibilidad; decidir entre tema admin importado o diseño personalizado. **Estado: En progreso (paleta aplicada).**
3. Documentar variables de entorno necesarias (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_AUTHORITY`, `DATABASE_URL`).
4. Añadir pruebas de integración para los endpoints y pruebas adicionales de seguridad/visibilidad.
5. Planificar motor de alertas (Celery) y crear tareas iniciales con `beat` para pruebas locales.

---

### Notas
- Archivo de referencia: `implementation plan.md` (detalla la arquitectura y decisiones técnicas).
- Si deseas, puedo convertir las etapas en issues de GitHub y/o en milestones en el repo.

---

> Si confirmas, continuaré con la **implementación del flujo OIDC (MSAL) y las pruebas JIT de autenticación**.
