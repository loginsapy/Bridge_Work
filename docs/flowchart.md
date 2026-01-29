# Flujograma del proyecto BridgeWork ✅

A continuación tienes un diagrama de alto nivel del flujo de la aplicación y los componentes principales. Está en formato Mermaid para que puedas visualizarlo en VS Code o exportarlo a PNG/SVG.

## Resumen (🔧 técnico)
- **Frontend / UI**: Blueprints `main`, templates, estático. Autenticación con `auth`.
- **API**: Blueprint `api` (/api) que expone endpoints para `projects`, `tasks`, `time_entries`, `users`.
- **Lógica / Servicios**: `app.services` (p. ej. `NotificationService`) que crea notificaciones y envía correos.
- **DB**: SQLAlchemy + Alembic (migrations). Modelos en `app.models`.
- **Background**: Celery (broker Redis) para tareas periódicas y envío asíncrono (`alerts`, `sender`, `monitor`).
- **Scripts / Dev**: `scripts/`, `seed.py`, `run.py` (crea `celery` con `make_celery(app)`).

---

```mermaid
flowchart TD
  subgraph CLIENTES
    U[Usuario (Browser / API client)]
  end

  subgraph WEB[Servidor Flask]
    direction LR
    UI[Blueprints: main, auth, templates] -->|requests| FlaskApp[Flask app / create_app]
    API[Blueprint: /api] -->|requests| FlaskApp
    FlaskApp -->|ORM queries| DB[Postgres / SQLAlchemy]
    FlaskApp -->|registers| Celery[Celery (make_celery)]
    FlaskApp -->|llama| Services[NotificationService & otros servicios]
  end

  U -->|HTTP / REST| UI
  U -->|HTTP / REST| API

  DB -->|migrations| Alembic[Alembic (migrations)]

  subgraph BACKGROUND[Worker / Scheduler]
    Redis[Redis (broker & result backend)]
    Worker[Celery worker]
    Beat[Celery beat (schedule)]
    Worker -->|ejecuta tareas| Tasks[alerts.*, sender.*, monitor.*]
    Beat -->|programa| Worker
    FlaskApp -->|.delay / .task| Worker
    Worker -->|acceso| DB
    Worker -->|usa| Services
  end

  Services -->|crea notificación en DB| DB
  Services -->|envía email| EmailProvider[Provedor SMTP/Sendgrid/etc.]
  Worker -->|envía email asíncrono| EmailProvider

  subgraph DEV
    Scripts[scripts/, seed.py, run.py] -->|seed, mantenimiento| DB
    Tests[tests/] -->|creación app (create_app TestConfig)| FlaskApp
  end

  %% Styling
  classDef infra fill:#f9f9f9,stroke:#333
  class DB,Alembic,Redis,EmailProvider infra
```

---

## Cómo usarlo
- Abre `docs/flowchart.md` en VS Code; si tienes la extensión de Markdown Preview Mermaid o la vista previa integrada de Mermaid, verás el diagrama.  
- Puedo exportarlo a PNG/SVG si prefieres un archivo de imagen listo para incluir en documentación o presentaciones.

## ¿Qué más quieres incluir? 💡
- Detalle de un endpoint concreto (p. ej. flujo de creación/actualización de `tasks`), o  
- Un flujograma de eventos internos (p. ej. notificaciones + aprobación de tareas), o  
- Generar versión en PNG/SVG para impresión.

---

Si quieres, genero también una imagen (PNG/SVG) y la agrego en `docs/`.
