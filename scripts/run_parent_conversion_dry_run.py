"""Run the conservative parent<-predecessor detection used by the migration as a standalone dry-run.
This writes 'migration_parent_conversion_report.csv' to the repo root.
"""
import os
import csv
import io
import sqlalchemy as sa

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
REPORT_PATH = 'migration_parent_conversion_report.csv'

engine = sa.create_engine(DATABASE_URL)
with engine.connect() as conn:
    converted = []
    ambiguous = []

    q = sa.text("""
        SELECT c.id AS child_id, p.id AS pred_id, c.project_id
        FROM tasks c
        JOIN task_predecessors tp ON tp.task_id = c.id
        JOIN tasks p ON p.id = tp.predecessor_id
        WHERE (SELECT count(*) FROM task_predecessors WHERE task_id = c.id) = 1
          AND p.project_id = c.project_id
    """)
    rows = conn.execute(q).fetchall()

    for row in rows:
        child_id = row['child_id']
        pred_id = row['pred_id']

        sc = conn.execute(sa.text("SELECT count(*) AS cnt FROM task_predecessors WHERE predecessor_id = :pid"), {'pid': pred_id}).scalar()
        if sc and sc <= 1:
            cycle_q = sa.text("""
                WITH RECURSIVE children(id) AS (
                    SELECT id FROM tasks WHERE parent_task_id = :child
                    UNION
                    SELECT t.id FROM tasks t JOIN children c ON t.parent_task_id = c.id
                )
                SELECT 1 FROM children WHERE id = :pred LIMIT 1
            """)
            is_cycle = conn.execute(cycle_q, {'child': child_id, 'pred': pred_id}).fetchone()
            if is_cycle:
                ambiguous.append((child_id, pred_id, 'cycle'))
                continue
            converted.append((child_id, pred_id))
        else:
            ambiguous.append((child_id, pred_id, 'pred_has_many_successors'))

    report_buf = io.StringIO()
    writer = csv.writer(report_buf)
    writer.writerow(['child_id', 'pred_id', 'status'])
    for (c, p) in converted:
        writer.writerow([c, p, 'converted_candidate'])
    for (c, p, reason) in ambiguous:
        writer.writerow([c, p, reason])

    with open(REPORT_PATH, 'w', newline='') as f:
        f.write(report_buf.getvalue())

print('DRY RUN: conversions preview written to', REPORT_PATH)
