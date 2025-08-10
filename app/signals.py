"""
Segnali per sincronizzazione automatica degli utenti tra database (per agenzia specifica)
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from app.models import ProfiloUtente
import logging

logger = logging.getLogger(__name__)

# Mapping agenzia -> database
AGENZIA_DATABASE_MAP = {
    'goldbet': 'goldbet_db',
    'better': 'better_db',
    # Aggiungi altre agenzie qui se necessario
}

@receiver(post_save, sender=User)
def sync_user_on_save(sender, instance, created, using, **kwargs):
    """
    Sincronizza automaticamente l'utente SOLO nel database della sua agenzia
    """
    # Evita loop infiniti: sincronizza solo se la modifica viene dal database 'default'
    if using != 'default':
        return
    
    try:
        # Trova l'agenzia dell'utente tramite il profilo
        profilo = ProfiloUtente.objects.using('default').filter(user=instance).first()
        if not profilo or not profilo.agenzia:
            logger.warning(f"Utente {instance.username} non ha un profilo o agenzia associata")
            return
        
        # Determina il database target basato sull'agenzia
        agenzia_nome = profilo.agenzia.nome.lower()
        target_db = AGENZIA_DATABASE_MAP.get(agenzia_nome)
        
        if not target_db:
            logger.warning(f"Nessun database configurato per l'agenzia {agenzia_nome}")
            return
        
        # Sincronizza SOLO nel database dell'agenzia dell'utente
        existing_user = User.objects.using(target_db).filter(id=instance.id).first()
        
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
            existing_user.save(using=target_db)
            logger.info(f"Aggiornato utente {instance.username} in {target_db} (agenzia: {agenzia_nome})")
        else:
            # Crea nuovo utente nel database target
            User.objects.using(target_db).create(
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
            logger.info(f"Creato utente {instance.username} in {target_db} (agenzia: {agenzia_nome})")
                
    except Exception as e:
        logger.error(f"Errore sincronizzando utente {instance.username}: {str(e)}")


@receiver(post_delete, sender=User)
def sync_user_on_delete(sender, instance, using, **kwargs):
    """
    Elimina automaticamente l'utente SOLO dal database della sua agenzia quando viene eliminato
    """
    # Evita loop infiniti: sincronizza solo se la cancellazione viene dal database 'default'
    if using != 'default':
        return
    
    try:
        # Trova l'agenzia dell'utente tramite il profilo (se ancora esiste)
        profilo = ProfiloUtente.objects.using('default').filter(user=instance).first()
        if not profilo or not profilo.agenzia:
            # Se non abbiamo il profilo, prova a eliminare da tutti i database per sicurezza
            logger.warning(f"Eliminazione utente {instance.username}: profilo non trovato, eliminando da tutti i database")
            for db_name in AGENZIA_DATABASE_MAP.values():
                User.objects.using(db_name).filter(id=instance.id).delete()
                logger.info(f"Eliminato utente {instance.username} da {db_name}")
            return
        
        # Determina il database target basato sull'agenzia
        agenzia_nome = profilo.agenzia.nome.lower()
        target_db = AGENZIA_DATABASE_MAP.get(agenzia_nome)
        
        if not target_db:
            logger.warning(f"Nessun database configurato per l'agenzia {agenzia_nome}")
            return
        
        # Elimina SOLO dal database dell'agenzia dell'utente
        User.objects.using(target_db).filter(id=instance.id).delete()
        logger.info(f"Eliminato utente {instance.username} da {target_db} (agenzia: {agenzia_nome})")
            
    except Exception as e:
        logger.error(f"Errore eliminando utente {instance.username}: {str(e)}")