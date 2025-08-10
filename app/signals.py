"""
Segnali per sincronizzazione automatica degli utenti tra database
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

# Lista dei database dove sincronizzare gli utenti
TARGET_DATABASES = ['goldbet_db', 'better_db']

@receiver(post_save, sender=User)
def sync_user_on_save(sender, instance, created, using, **kwargs):
    """
    Sincronizza automaticamente l'utente quando viene creato o aggiornato
    """
    # Evita loop infiniti: sincronizza solo se la modifica viene dal database 'default'
    if using != 'default':
        return
    
    try:
        for db_name in TARGET_DATABASES:
            # Controlla se l'utente esiste già nel database target
            existing_user = User.objects.using(db_name).filter(id=instance.id).first()
            
            if existing_user:
                # Aggiorna l'utente esistente
                existing_user.username = instance.username
                existing_user.first_name = instance.first_name
                existing_user.last_name = instance.last_name
                existing_user.email = instance.email
                existing_user.password = instance.password
                existing_user.is_staff = instance.is_staff
                existing_user.is_active = instance.is_active
                existing_user.is_superuser = instance.is_superuser
                existing_user.date_joined = instance.date_joined
                existing_user.last_login = instance.last_login
                existing_user.save(using=db_name)
                logger.info(f"Aggiornato utente {instance.username} in {db_name}")
            else:
                # Crea nuovo utente nel database target
                User.objects.using(db_name).create(
                    id=instance.id,
                    username=instance.username,
                    first_name=instance.first_name,
                    last_name=instance.last_name,
                    email=instance.email,
                    password=instance.password,
                    is_staff=instance.is_staff,
                    is_active=instance.is_active,
                    is_superuser=instance.is_superuser,
                    date_joined=instance.date_joined,
                    last_login=instance.last_login,
                )
                logger.info(f"Creato utente {instance.username} in {db_name}")
                
    except Exception as e:
        logger.error(f"Errore sincronizzando utente {instance.username}: {str(e)}")


@receiver(post_delete, sender=User)
def sync_user_on_delete(sender, instance, using, **kwargs):
    """
    Elimina automaticamente l'utente da tutti i database quando viene eliminato
    """
    # Evita loop infiniti: sincronizza solo se la cancellazione viene dal database 'default'
    if using != 'default':
        return
    
    try:
        for db_name in TARGET_DATABASES:
            # Elimina l'utente dal database target se esiste
            User.objects.using(db_name).filter(id=instance.id).delete()
            logger.info(f"Eliminato utente {instance.username} da {db_name}")
            
    except Exception as e:
        logger.error(f"Errore eliminando utente {instance.username}: {str(e)}")