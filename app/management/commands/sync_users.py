"""
Comando per sincronizzare gli utenti tra database (per agenzia specifica)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from app.models import ProfiloUtente

# Mapping agenzia -> database
AGENZIA_DATABASE_MAP = {
    'goldbet': 'goldbet_db',
    'better': 'better_db',
}

class Command(BaseCommand):
    help = 'Sincronizza gli utenti nel database della loro agenzia specifica'

    def handle(self, *args, **options):
        self.stdout.write('🔄 Sincronizzando utenti per agenzia specifica...')
        
        # Ottieni tutti gli utenti dal database principale con i loro profili
        users_with_profiles = User.objects.using('default').select_related('profiloutente__agenzia').all()
        
        for user in users_with_profiles:
            try:
                # Verifica se l'utente ha un profilo e un'agenzia
                profilo = getattr(user, 'profiloutente', None)
                if not profilo or not profilo.agenzia:
                    self.stdout.write(f'⚠️ Utente {user.username} non ha profilo o agenzia associata - saltato')
                    continue
                
                # Determina il database target basato sull'agenzia
                agenzia_nome = profilo.agenzia.nome.lower()
                target_db = AGENZIA_DATABASE_MAP.get(agenzia_nome)
                
                if not target_db:
                    self.stdout.write(f'⚠️ Nessun database configurato per l\'agenzia {agenzia_nome} - utente {user.username} saltato')
                    continue
                
                self.stdout.write(f'📊 Sincronizzando {user.username} con {target_db} (agenzia: {agenzia_nome})...')
                
                # Controlla se l'utente esiste già nel database target
                existing_user = User.objects.using(target_db).filter(id=user.id).first()
                
                if not existing_user:
                    # Crea l'utente nel database target
                    User.objects.using(target_db).create(
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
                    self.stdout.write(f'✅ Creato utente {user.username} in {target_db}')
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
                        existing_user.save(using=target_db)
                        self.stdout.write(f'🔄 Aggiornato utente {user.username} in {target_db}')
                    else:
                        self.stdout.write(f'⚠️ Utente {user.username} già sincronizzato in {target_db}')
                        
            except Exception as e:
                self.stdout.write(f'❌ Errore sincronizzando {user.username}: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Sincronizzazione utenti completata!')
        )