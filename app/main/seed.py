from app import create_app, db
from app.models import User, Project, Task, TimeEntry, Role
from datetime import datetime, timedelta
import random

app = create_app()

def seed_database():
    with app.app_context():
        # Opcional: Descomenta las siguientes lineas si quieres borrar todo antes de crear
        # db.drop_all()
        # db.create_all()
        
        # 0. Crear Roles (Necesario para que los usuarios tengan permisos)
        roles_list = ['Admin', 'PMP', 'Participante', 'Cliente']
        roles_map = {}
        for r_name in roles_list:
            role = Role.query.filter_by(name=r_name).first()
            if not role:
                role = Role(name=r_name)
                db.session.add(role)
            roles_map[r_name] = role
        db.session.commit()

        if User.query.first():
            print("⚠️  La base de datos ya tiene datos. Si quieres reiniciar, usa db.drop_all() en el script.")
            return

        print("🌱 Generando datos de prueba...")

        # 1. Usuarios
        admin = User(email='admin@bridgework.com', first_name='Admin', last_name='System', is_internal=True, role=roles_map['Admin'])
        admin.set_password('admin123')
        
        dev1 = User(email='ana@bridgework.com', first_name='Ana', last_name='García', is_internal=True, role=roles_map['Participante'])
        dev1.set_password('password')
        
        dev2 = User(email='carlos@bridgework.com', first_name='Carlos', last_name='Ruiz', is_internal=True, role=roles_map['Participante'])
        dev2.set_password('password')
        
        users = [admin, dev1, dev2]
        db.session.add_all(users)
        db.session.commit()

        # 2. Proyectos
        projects_data = [
            {'name': 'Rediseño Portal Corporativo', 'desc': 'Modernización del sitio web público con React y nueva identidad.', 'budget': 120, 'status': 'ACTIVE'},
            {'name': 'API de Pagos', 'desc': 'Integración con Stripe y PayPal para pasarela de pagos.', 'budget': 80, 'status': 'IN_PROGRESS'},
            {'name': 'Migración Cloud', 'desc': 'Mover infraestructura on-premise a Azure Kubernetes Service.', 'budget': 200, 'status': 'ON_HOLD'},
            {'name': 'App Móvil Interna', 'desc': 'App para gestión de vacaciones de empleados.', 'budget': 60, 'status': 'COMPLETED'},
        ]

        projects = []
        for p_data in projects_data:
            p = Project(
                name=p_data['name'],
                description=p_data['desc'],
                budget_hours=p_data['budget'],
                status=p_data['status'],
                start_date=datetime.now() - timedelta(days=random.randint(1, 60))
            )
            db.session.add(p)
            projects.append(p)
        db.session.commit()

        # 3. Tareas
        tasks = []
        statuses = ['BACKLOG', 'IN_PROGRESS', 'IN_REVIEW', 'COMPLETED']
        
        for project in projects:
            num_tasks = random.randint(3, 8)
            for i in range(num_tasks):
                task = Task(
                    title=f'Tarea {i+1} - {project.name[:10]}...',
                    project_id=project.id,
                    assigned_to_id=random.choice(users).id,
                    status=random.choice(statuses) if project.status == 'ACTIVE' else 'COMPLETED' if project.status == 'COMPLETED' else 'BACKLOG',
                    due_date=datetime.now() + timedelta(days=random.randint(-5, 15))
                )
                db.session.add(task)
                tasks.append(task)
        db.session.commit()

        # 4. Registros de Tiempo
        for task in tasks:
            if task.status in ['IN_PROGRESS', 'IN_REVIEW', 'COMPLETED']:
                for _ in range(random.randint(1, 5)):
                    entry = TimeEntry(
                        user_id=task.assigned_to_id,
                        task_id=task.id,
                        hours=round(random.uniform(0.5, 4.0), 1),
                        date=datetime.now() - timedelta(days=random.randint(0, 30)),
                        description=f'Trabajo en {task.title}'
                    )
                    db.session.add(entry)
        
        db.session.commit()
        print("✅ ¡Datos de prueba insertados correctamente!")

if __name__ == '__main__':
    seed_database()