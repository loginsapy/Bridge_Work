"""
Script para corregir el typo en el rol "Particpante" -> "Participante"
Ejecutar una sola vez: python scripts/fix_role_typo.py
"""
from run import app
from app import db
from app.models import Role

with app.app_context():
    print('Buscando rol con typo "Particpante"...')
    
    # Buscar el rol con el typo
    role_with_typo = Role.query.filter_by(name='Particpante').first()
    
    if role_with_typo:
        # Verificar si ya existe un rol "Participante" correcto
        correct_role = Role.query.filter_by(name='Participante').first()
        
        if correct_role:
            # Si ya existe el correcto, migrar usuarios y eliminar el incorrecto
            print(f'Ya existe el rol "Participante" (id={correct_role.id})')
            print(f'Migrando usuarios del rol incorrecto (id={role_with_typo.id})...')
            
            from app.models import User
            users_to_migrate = User.query.filter_by(role_id=role_with_typo.id).all()
            for user in users_to_migrate:
                user.role_id = correct_role.id
                print(f'  - Migrado: {user.email}')
            
            db.session.delete(role_with_typo)
            db.session.commit()
            print(f'Rol incorrecto eliminado. {len(users_to_migrate)} usuarios migrados.')
        else:
            # Si no existe el correcto, simplemente renombrar
            print(f'Corrigiendo nombre del rol (id={role_with_typo.id})...')
            role_with_typo.name = 'Participante'
            db.session.commit()
            print('¡Rol corregido exitosamente!')
    else:
        # Verificar si ya está correcto
        correct_role = Role.query.filter_by(name='Participante').first()
        if correct_role:
            print('El rol "Participante" ya existe y está correcto. No se requieren cambios.')
        else:
            print('No se encontró ningún rol "Particpante" ni "Participante".')
            print('Creando rol "Participante"...')
            new_role = Role(name='Participante')
            db.session.add(new_role)
            db.session.commit()
            print('Rol "Participante" creado.')
    
    # Mostrar roles actuales
    print('\nRoles actuales en la base de datos:')
    for role in Role.query.all():
        user_count = len(role.users)
        print(f'  - {role.name} (id={role.id}, {user_count} usuarios)')
