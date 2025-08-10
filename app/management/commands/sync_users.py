"""
Comando per sincronizzare gli utenti tra tutti i database
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction


class Command(BaseCommand):
    help = 'Sincronizza gli utenti tra tutti i database'

    def handle(self, *args, **options):
        databases = ['default', 'goldbet_db', 'better_db']
        
        self.stdout.write('🔄 Sincronizzando utenti tra database...')
        
        # Ottieni tutti gli utenti dal database principale
        users_default = User.objects.using('default').all()
        
        for db_name in ['goldbet_db', 'better_db']:
            self.stdout.write(f'📊 Sincronizzando con {db_name}...')
            
            for user in users_default:
                try:
                    # Controlla se l'utente esiste già nel database target
                    existing_user = User.objects.using(db_name).filter(username=user.username).first()
                    
                    if not existing_user:
                        # Crea l'utente nel database target
                        User.objects.using(db_name).create(
                            id=user.id,  # Mantieni lo stesso ID
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name,
                            email=user.email,
                            password=user.password,
                            is_staff=user.is_staff,
                            is_active=user.is_active,
                            is_superuser=user.is_superuser,
                            date_joined=user.date_joined,
                            last_login=user.last_login,
                        )
                        self.stdout.write(f'✅ Creato utente {user.username} in {db_name}')
                    else:
                        # Aggiorna l'utente esistente se necessario
                        if (existing_user.email != user.email or 
                            existing_user.first_name != user.first_name or
                            existing_user.last_name != user.last_name):
                            
                            existing_user.email = user.email
                            existing_user.first_name = user.first_name
                            existing_user.last_name = user.last_name
                            existing_user.password = user.password
                            existing_user.is_staff = user.is_staff
                            existing_user.is_active = user.is_active
                            existing_user.is_superuser = user.is_superuser
                            existing_user.save(using=db_name)
                            self.stdout.write(f'🔄 Aggiornato utente {user.username} in {db_name}')
                        else:
                            self.stdout.write(f'⚠️ Utente {user.username} già sincronizzato in {db_name}')
                            
                except Exception as e:
                    self.stdout.write(f'❌ Errore sincronizzando {user.username} in {db_name}: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Sincronizzazione utenti completata!')
        )