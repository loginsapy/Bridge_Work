from app import create_app

app = create_app()

# Create Celery app instance so docker-compose (and tests) can use `run.celery`
from app.celery_app import make_celery
celery = make_celery(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
