import sqlalchemy as sa
from app.models import Task, Project, db


def test_migration_detection_of_candidates(create_project, create_task):
    p = create_project('MigTest')
    parent = create_task(project_id=p['id'], title='ParentMig')
    child = create_task(project_id=p['id'], title='ChildMig', parent_task_id=None)

    parent_obj = Task.query.get(parent['id'])
    child_obj = Task.query.get(child['id'])

    # link predecessor -> child
    child_obj.predecessors = [parent_obj]
    db.session.commit()

    # Run the same detection SQL as migration to find candidate conversions
    q = sa.text("""
        SELECT c.id AS child_id, p.id AS pred_id, c.project_id
        FROM tasks c
        JOIN task_predecessors tp ON tp.task_id = c.id
        JOIN tasks p ON p.id = tp.predecessor_id
        WHERE (SELECT count(*) FROM task_predecessors WHERE task_id = c.id) = 1
          AND p.project_id = c.project_id
    """)
    rows = db.session.execute(q).fetchall()

    # rows may be Row objects or tuples depending on SQLAlchemy version
    assert any((r['child_id'] == child_obj.id and r['pred_id'] == parent_obj.id) if hasattr(r, 'keys') else (r[0] == child_obj.id and r[1] == parent_obj.id) for r in rows)

    # Check heuristic that predecessor has <=1 successors
    sc = db.session.execute(sa.text("SELECT count(*) AS cnt FROM task_predecessors WHERE predecessor_id = :pid"), {'pid': parent_obj.id}).scalar()
    assert sc <= 1
