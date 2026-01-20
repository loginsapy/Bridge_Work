#!/usr/bin/env python3
"""
Normalize task statuses in DB: convert legacy 'DONE' to 'COMPLETED'.
Idempotent.
"""
from app import create_app, db
from app.models import Task

app = create_app()
with app.app_context():
    done_tasks = Task.query.filter(Task.status == 'DONE').all()
    print(f'Found {len(done_tasks)} tasks with status DONE')
    for t in done_tasks:
        print(f'  Updating task {t.id} "{t.title}" -> COMPLETED')
        t.status = 'COMPLETED'
    if done_tasks:
        db.session.commit()
        print('Updated statuses and committed.')
    else:
        print('No changes needed.')
