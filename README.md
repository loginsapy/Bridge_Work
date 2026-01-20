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
## 📘 Funcionalidades del sistema (Resumen)
A continuación se documentan las funcionalidades principales que el proyecto ofrece actualmente. Esta sección está pensada como referencia rápida para desarrolladores y usuarios avanzados.

- Panel / Dashboard
  - KPI cards (proyectos activos, horas, tareas completadas, velocidad del equipo).
  - Kanban resumido por estado y tarjetas de proyectos recientes con clientes y progreso.

- Proyectos
  - Vistas en lista y grid, filtros por estado, paginación y vista detallada del proyecto.
  - Asociar uno o más clientes a un proyecto; se muestra un icono de edificio con tooltip "Nombre (Cliente Externo)" en varias vistas (Board, Projects, Dashboard, Reports).

- Tareas (Board / Task Detail)
  - Vista estilo Monday/kanban y tabla/board con WBS soportado (numeración jerárquica).
  - Soporte de **multi-assignees** (many-to-many). Interfaz con avatares compactos, overflow +N y tooltip con nombre completo.
  - Predecesoras bloquean avance / registro de tiempo: la UI y la API manejan bloqueos, mostrando modal/alerta cuando aplica.
  - Normalización de estados: `DONE` → `COMPLETED` canonizado en DB y API.
  - Minimal lock icon para tareas bloqueadas (UI accesible y limpia).

- Asignaciones
  - Modal "+ Asignar" que añade (no reemplaza) a la lista de `assignees` del task.
  - Solo **PMP/Admin** ven y usan el dropdown de asignación en el Board; Participantes/Clientes no lo ven.

- Registros de Tiempo (Time Entries)
  - Crear registro con: tarea, fecha, horas, descripción y flag `is_billable`.
  - Preselección de tarea cuando se abre desde una tarea (`?task_id=...`) — funciona para PMP, Admin y Participantes asignados (incluye multi-asignaciones).
  - **Permisos de edición**:
    - El autor del registro puede editar su propio registro.
    - **PMP y Admin** pueden editar cualquier registro (incluyendo marcar `is_billable`).
    - **Clientes** no pueden editar registros; el botón de edición no se muestra ni la ruta permite cambios.

- Exportes y Reportes
  - Página de reportes por proyecto con columnas (incluye **Atraso (días)**) y exportación **XLSX** generada con `openpyxl`.
  - Paginación en el reporte y KPI locales al proyecto seleccionado.

- Archivos y adjuntos
  - Validación de extensiones tanto en cliente como en servidor; los adjuntos inválidos se ignoran/alertan y no _vacían_ otros campos del formulario.
  - UI muestra advertencias y evita submit cuando hay ficheros inválidos detectados en cliente.

- Notificaciones
  - Badge y toasts en navbar; notificaciones por asignación y por otras acciones (configurable via SystemSettings)
  - Envío de emails controlado por configuración (habilitado/deshabilitado y con retry/diagnostics según SDK).

- API
  - Endpoints RESTful para proyectos, tareas y registros de tiempo (`/api/projects`, `/api/tasks`, `/api/time_entries`).
  - Reglas de permiso server-side: participantes/clientes limitados en campos (por ejemplo solo `status`), PMP/Admin con permisos extendidos.

- Tests y Calidad
  - Suite de tests `pytest` con tests unitarios e integrados para permisos, exportes, reportes, UI templates y manejo de adjuntos.
  - Archivos de pruebas clave: `tests/test_reports_project_export.py`, `tests/test_board_assignees.py`, `tests/test_time_entry_task_preselect.py`, etc.

- Notas operativas y dependencias
  - Asegúrate de instalar dependencias desde `requirements.txt` (`openpyxl` incluido para exportes XLSX).
  - Lee `docs/DB-SAFETY.md` antes de ejecutar tests en entornos con DB remota.

---

## 🛠️ Cambios recientes importantes
- 2026-01-20: Añadida columna **Atraso (días)** y exportación XLSX de reportes por proyecto (implementada con `openpyxl`).
- 2026-01-20: **Permisos de edición en Registros de Tiempo**: ahora **PMP y Admin** pueden editar cualquier registro; participantes pueden editar solo sus propios registros; clientes no pueden editar registros.
- Se añadieron múltiples tests para validar los cambios de UI y permisos mencionados arriba.

---

> Si quieres que documente más en detalle alguna sección específica (por ejemplo, endpoints de la API con ejemplos cURL, o un diagrama de permisos por rol), dime cuál y lo añado.