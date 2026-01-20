# Database Safety & Destructive Operations

This document explains the safeguards added to prevent accidental destructive operations (DROP, DROP SCHEMA, db.drop_all()) against remote/production databases.

Why this exists
- Running tests or maintenance scripts against a production database is dangerous and can delete data irreversibly.
- Some scripts in this repo perform destructive operations for migration or reset purposes; they must be executed intentionally.

Key safeguards added

1. tests/conftest.py
- Tests now create the app with an explicit TestConfig and validate that `TESTING` is enabled and that the configured `SQLALCHEMY_DATABASE_URI` points to a local/test database (sqlite, localhost, 127.0.0.1). Tests abort immediately if this check fails.
- The teardown step that calls `db.drop_all()` is refused when the DB URI is not local/test.

2. seed.py
- A reset now requires `ALLOW_DB_RESET=1`.
- Resetting a remote Postgres DB requires `CONFIRM_REMOTE_DB_RESET=YES` in addition to `ALLOW_DB_RESET=1`.

3. Migration/maintenance scripts
- Scripts that run DDL or drop/replace tables (e.g., `scripts/drop_backups.py`, `scripts/apply_parent_conversion.py`, `scripts/run_parent_conversion_dry_run.py`, `scripts/check_backups_and_report.py`) now refuse to run on remote DBs unless explicit environment confirmations are set:
  - `CONFIRM_DROP_BACKUPS=YES` for dropping backup tables
  - `CONFIRM_PARENT_CONVERSION=YES` for applying parent conversion
  - `ALLOW_REMOTE_DRY_RUN=YES` for dry-run conversions
  - `ALLOW_REMOTE_INSPECT=YES` for inspection scripts

4. Safety helper
- `app/utils/safety.py` centralizes the check `is_safe_db_uri(uri)` and `require_confirmation(env_var)` to keep logic consistent.

Recommendations
- Always run tests in an isolated environment (CI or local) with a local sqlite DB or a dedicated test Postgres instance on localhost.
- Never set `DATABASE_URL` to a production database on developer machines or CI runners running tests.
- For executing maintenance scripts against a remote DB, set the required confirmation environment variable and double-check the `DATABASE_URL` before running.

If you have a backup or snapshot, I can help evaluate and restore it safely; otherwise I can reseed critical data (roles, admin account, essential settings) so the app is usable while we determine recovery steps.
