"""List existing tables and row counts for core tables."""
import os
import sqlalchemy as sa

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
engine = sa.create_engine(DATABASE_URL)

core_tables = ['users','projects','tasks','task_predecessors','alembic_version']

with engine.connect() as conn:
    print('Existing tables (information_schema):')
    rows = conn.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
    tables = [r[0] for r in rows.fetchall()]
    print(', '.join(tables))

    print('\nCore table existence and counts:')
    for t in core_tables:
        exists = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"), {'t': t}).scalar()
        if exists:
            try:
                cnt = conn.execute(sa.text(f"SELECT count(*) FROM {t}")).scalar()
            except Exception:
                cnt = 'N/A'
        else:
            cnt = 'missing'
        print(f" - {t}: {cnt}")
