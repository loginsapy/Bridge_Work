"""separate parent-child from predecessors (conservative conversion)

Revision ID: 0a1b2c3d4e5f
Revises: 41457cd927c5
Create Date: 2025-12-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import csv
import io

# revision identifiers, used by Alembic.
revision = '0a1b2c3d4e5f'
down_revision = '41457cd927c5'
branch_labels = None
depends_on = None

# Toggle dry-run here (or pass via env var)
DRY_RUN = True
REPORT_PATH = 'migration_parent_conversion_report.csv'


def upgrade():
    bind = op.get_bind()
    # 1) Add index if missing
    try:
        op.create_index('ix_tasks_parent_task_id', 'tasks', ['parent_task_id'])
    except Exception:
        pass

    # 2) Data conversion (conservative)
    converted = []
    ambiguous = []

    # Find tasks with exactly one predecessor and same project
    q = sa.text("""
        SELECT c.id AS child_id, p.id AS pred_id, c.project_id
        FROM tasks c
        JOIN task_predecessors tp ON tp.task_id = c.id
        JOIN tasks p ON p.id = tp.predecessor_id
        WHERE (SELECT count(*) FROM task_predecessors WHERE task_id = c.id) = 1
          AND p.project_id = c.project_id
    """)
    rows = bind.execute(q).fetchall()

    for row in rows:
        child_id = row['child_id']
        pred_id = row['pred_id']

        # Check predecessor successors count (heuristic)
        sc = bind.execute(sa.text("SELECT count(*) AS cnt FROM task_predecessors WHERE predecessor_id = :pid"), {'pid': pred_id}).scalar()
        if sc and sc <= 1:
            # further cycle check: skip if pred is descendant of child (avoid cycle)
            cycle_q = sa.text("""
                WITH RECURSIVE children(id) AS (
                    SELECT id FROM tasks WHERE parent_task_id = :child
                    UNION
                    SELECT t.id FROM tasks t JOIN children c ON t.parent_task_id = c.id
                )
                SELECT 1 FROM children WHERE id = :pred LIMIT 1
            """)
            is_cycle = bind.execute(cycle_q, {'child': child_id, 'pred': pred_id}).fetchone()
            if is_cycle:
                ambiguous.append((child_id, pred_id, 'cycle'))
                continue
            # Candidate: convert
            converted.append((child_id, pred_id))
        else:
            ambiguous.append((child_id, pred_id, 'pred_has_many_successors'))

    # Write CSV report
    report_buf = io.StringIO()
    writer = csv.writer(report_buf)
    writer.writerow(['child_id', 'pred_id', 'status'])
    for (c, p) in converted:
        writer.writerow([c, p, 'converted_candidate'])
    for (c, p, reason) in ambiguous:
        writer.writerow([c, p, reason])
    # Persist report
    with open(REPORT_PATH, 'w', newline='') as f:
        f.write(report_buf.getvalue())

    if DRY_RUN:
        print("DRY RUN: conversions preview written to", REPORT_PATH)
        return

    # Apply conversions
    for (child_id, pred_id) in converted:
        bind.execute(sa.text("UPDATE tasks SET parent_task_id = :pred WHERE id = :child"), {'pred': pred_id, 'child': child_id})
        bind.execute(sa.text("DELETE FROM task_predecessors WHERE task_id = :child AND predecessor_id = :pred"), {'child': child_id, 'pred': pred_id})

    print(f"Applied {len(converted)} conversions. Report at {REPORT_PATH}")


def downgrade():
    raise sa.exc.NotImplementedError("Downgrade is not implemented for data migration. Manual revert needed.")
