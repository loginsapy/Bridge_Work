"""Apply the conservative parent<-predecessor conversions.

Steps:
- Create backup tables tasks_backup and task_predecessors_backup (drop existing backups first)
- Detect candidate conversions using the same heuristics as dry-run
- Write report CSV (migration_parent_conversion_report.csv) listing converted and ambiguous
- Apply conversions (update tasks.parent_task_id, delete task_predecessors rows) within a transaction
- Print summary of actions
"""
import os
import csv
import io
import sqlalchemy as sa

DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
REPORT_PATH = 'migration_parent_conversion_report.csv'

# Safety: require explicit confirmation to run on a remote DB
from app.utils.safety import is_safe_db_uri, require_confirmation
if not is_safe_db_uri(DATABASE_URL):
    if not require_confirmation('CONFIRM_PARENT_CONVERSION'):
        print("Refusing to run parent conversion on remote DB. Set CONFIRM_PARENT_CONVERSION=YES to proceed.")
        raise SystemExit(1)

engine = sa.create_engine(DATABASE_URL)

with engine.begin() as conn:
    print('Creating backups: tasks_backup, task_predecessors_backup (if exist: replaced)')
    conn.execute(sa.text('DROP TABLE IF EXISTS task_predecessors_backup'))
    conn.execute(sa.text('DROP TABLE IF EXISTS tasks_backup'))
    conn.execute(sa.text('CREATE TABLE tasks_backup AS TABLE tasks'))
    conn.execute(sa.text('CREATE TABLE task_predecessors_backup AS TABLE task_predecessors'))
    print('Backups created')

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

    # Write CSV report
    report_buf = io.StringIO()
    writer = csv.writer(report_buf)
    writer.writerow(['child_id', 'pred_id', 'status'])
    for (c, p) in converted:
        writer.writerow([c, p, 'will_be_converted'])
    for (c, p, reason) in ambiguous:
        writer.writerow([c, p, reason])
    with open(REPORT_PATH, 'w', newline='') as f:
        f.write(report_buf.getvalue())

    print('Report written to', REPORT_PATH)

    if not converted:
        print('No candidate conversions found. Nothing to apply.')
    else:
        print('Applying conversions:', len(converted))
        for (child_id, pred_id) in converted:
            conn.execute(sa.text('UPDATE tasks SET parent_task_id = :pred WHERE id = :child'), {'pred': pred_id, 'child': child_id})
            conn.execute(sa.text('DELETE FROM task_predecessors WHERE task_id = :child AND predecessor_id = :pred'), {'child': child_id, 'pred': pred_id})
        print('Applied conversions.')

print('Done')
