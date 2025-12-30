"""
Script para probar el sistema de notificaciones.
Ejecutar: python scripts/test_notifications.py

Para usar SendGrid:
1. Configura las variables de entorno:
   - EMAIL_PROVIDER=sendgrid
   - SENDGRID_API_KEY=tu_api_key
   - EMAIL_FROM=noreply@tudominio.com
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Task, Project
from app.services import NotificationService

def test_notifications():
    app = create_app()
    
    with app.app_context():
        # Buscar un usuario para pruebas
        user = User.query.filter_by(is_internal=True).first()
        if not user:
            print("❌ No se encontró un usuario interno para pruebas")
            return
        
        print(f"📧 Probando notificaciones para: {user.email}")
        print(f"🔧 Provider de email: {app.config.get('EMAIL_PROVIDER', 'stub')}")
        print("-" * 50)
        
        # 1. Crear notificación simple (solo in-app)
        print("\n1️⃣ Creando notificación in-app...")
        notif = NotificationService.create(
            user_id=user.id,
            title="Prueba de notificación",
            message="Esta es una notificación de prueba del sistema",
            notification_type="general"
        )
        print(f"   ✅ Notificación creada con ID: {notif.id}")
        
        # 2. Buscar una tarea para probar notificaciones relacionadas
        task = Task.query.filter_by(assigned_to_id=user.id).first()
        if task:
            print(f"\n2️⃣ Probando notificación de tarea asignada...")
            print(f"   Tarea: {task.title}")
            
            # Simular asignación (sin email para prueba rápida)
            notif = NotificationService.notify_task_assigned(
                task=task,
                assigned_by_user=None,
                send_email=False  # Cambiar a True para probar email
            )
            if notif:
                print(f"   ✅ Notificación de asignación creada")
            
            # 3. Probar notificación de cambio de estado
            print(f"\n3️⃣ Probando notificación de cambio de estado...")
            notif = NotificationService.notify_task_status_changed(
                task=task,
                old_status="BACKLOG",
                changed_by_user=None,
                send_email=False
            )
            if notif:
                print(f"   ✅ Notificación de cambio de estado creada")
        else:
            print("\n⚠️ No se encontró una tarea asignada al usuario para pruebas")
        
        # 4. Verificar conteo de notificaciones
        print("\n4️⃣ Estadísticas de notificaciones:")
        unread = NotificationService.get_unread_count(user.id)
        recent = NotificationService.get_recent(user.id, limit=5)
        print(f"   📬 No leídas: {unread}")
        print(f"   📋 Recientes: {len(recent)}")
        
        # 5. Probar envío de email (si está configurado)
        if app.config.get('EMAIL_PROVIDER') == 'sendgrid' and app.config.get('SENDGRID_API_KEY'):
            print("\n5️⃣ Probando envío de email con SendGrid...")
            success = NotificationService.send_email(
                user_id=user.id,
                subject="Prueba de email desde BridgeWork",
                notification_type="general",
                context={
                    'message': 'Este es un correo de prueba del sistema de notificaciones.',
                    'title': 'Prueba de email'
                }
            )
            if success:
                print(f"   ✅ Email enviado exitosamente a {user.email}")
            else:
                print(f"   ❌ Error al enviar email")
        else:
            print("\n5️⃣ SendGrid no configurado - usando stub provider (solo logs)")
            print("   Para probar emails reales, configura:")
            print("   - EMAIL_PROVIDER=sendgrid")
            print("   - SENDGRID_API_KEY=tu_api_key")
        
        print("\n" + "=" * 50)
        print("✅ Pruebas completadas")
        
        # Mostrar notificaciones recientes
        print("\n📋 Notificaciones recientes del usuario:")
        for n in recent[:5]:
            status = "🔵" if not n.is_read else "⚪"
            print(f"   {status} [{n.notification_type}] {n.title}")


if __name__ == '__main__':
    test_notifications()
