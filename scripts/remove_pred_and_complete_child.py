"""Remove predecessor edge (pred_id -> child_id) and set child status to COMPLETED.
This is a safe dev-only action to unblock testing.
"""
from app import create_app, db
from app.models import Task

app = create_app()

CHILD_ID = 2
PRED_ID = 3

with app.app_context():
    child = Task.query.get(CHILD_ID)
    pred = Task.query.get(PRED_ID)
    if not child:
        print('Child task not found')
    if not pred:
        print('Predecessor task not found')

    # Check current predecessors
    print('Before: child.predecessors =', [t.id for t in child.predecessors])

    # Remove predecessor edge if present
    if pred in child.predecessors:
        child.predecessors.remove(pred)
        db.session.commit()
        print(f'Removed predecessor {PRED_ID} from child {CHILD_ID}')
    else:
        print('No predecessor edge to remove')

    # Verify removal
    child = Task.query.get(CHILD_ID)
    print('After removal: child.predecessors =', [t.id for t in child.predecessors])

    # Try to set child to COMPLETED
    try:
        child.status = 'COMPLETED'
        db.session.commit()
        print(f'Child task {CHILD_ID} set to COMPLETED')
    except Exception as e:
        db.session.rollback()
        print('Error setting child to COMPLETED:', e)

    # Final state
    child = Task.query.get(CHILD_ID)
    print('Final child status:', child.status)
