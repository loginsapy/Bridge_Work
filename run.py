import os
from app import create_app

app = create_app()

# Create Celery app instance so docker-compose (and tests) can use `run.celery`
from app.celery_app import make_celery
celery = make_celery(app)

if __name__ == '__main__':
    # Usar puerto 8000 por defecto para coincidir con docker-compose y evitar errores de redirección
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Iniciando servidor en el puerto {port}...")
    app.run(host='0.0.0.0', port=port)
