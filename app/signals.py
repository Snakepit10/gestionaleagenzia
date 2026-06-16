"""
Segnali per sincronizzazione automatica degli utenti tra database (per agenzia specifica)
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import Sum
from django.contrib.auth.models import User
from app.models import ProfiloUtente, Cliente, Movimento, MovimentoConti
from app import telegram_utils
import logging

logger = logging.getLogger(__name__)

# Mapping agenzia -> database
AGENZIA_DATABASE_MAP = {
    'goldbet': 'goldbet_db',
    'better': 'better_db',
    'planet': 'planet_db',
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


# ===========================================================================
# Notifiche Telegram
# ===========================================================================

@receiver(pre_save, sender=Cliente)
def cliente_memorizza_fido_precedente(sender, instance, using, update_fields=None, **kwargs):
    """Salva il fido attuale (da DB) sull'istanza per rilevare un eventuale aumento."""
    instance._old_fido = None
    if instance.pk is None:
        return
    # Se il salvataggio non tocca il fido (es. aggiorna_saldo usa update_fields=['saldo']),
    # evita la query: il fido non può essere cambiato.
    if update_fields is not None and 'fido_massimo' not in update_fields:
        return
    try:
        precedente = Cliente.objects.using(using).filter(pk=instance.pk).first()
        instance._old_fido = precedente.fido_massimo if precedente else None
    except Exception as e:
        logger.error(f"Telegram: errore lettura fido precedente cliente {instance.pk}: {e}")
        instance._old_fido = None


@receiver(post_save, sender=Cliente)
def cliente_notifica_telegram(sender, instance, created, using, **kwargs):
    """Trigger #4 (nuovo cliente) e #3 (aumento fido)."""
    try:
        if created:
            testo = telegram_utils.msg_nuovo_cliente(instance, using)
            transaction.on_commit(lambda: telegram_utils.notifica(using, testo), using=using)
            return

        old_fido = getattr(instance, '_old_fido', None)
        if old_fido is not None and instance.fido_massimo > old_fido:
            testo = telegram_utils.msg_aumento_fido(instance, old_fido, instance.fido_massimo, using)
            transaction.on_commit(lambda: telegram_utils.notifica(using, testo), using=using)
    except Exception as e:
        logger.error(f"Telegram: errore notifica cliente {instance.pk}: {e}")


@receiver(post_save, sender=Movimento)
def movimento_notifica(sender, instance, created, using, **kwargs):
    """
    Trigger #1: cliente sopra il fido (a ogni movimento finché resta sopra).
    Trigger #5: cliente monitorato (ogni movimento creato, anche senza fido superato).
    """
    try:
        cliente = instance.cliente
        # In Movimento.save() il post_save scatta PRIMA di aggiorna_saldo(): ricalcolo qui.
        saldo = Movimento.objects.using(using).filter(
            cliente=cliente, saldato=False
        ).aggregate(tot=Sum('importo'))['tot'] or 0

        # Cliente monitorato: notifica ogni nuovo movimento, indipendentemente dal fido.
        if created and getattr(cliente, 'notifica_movimenti', False):
            testo = telegram_utils.msg_movimento_cliente(instance, saldo, using)
            transaction.on_commit(lambda t=testo: telegram_utils.notifica(using, t), using=using)

        # Fido superato: esclude i movimenti di compensazione/saldo (non sono nuovo debito).
        is_compensazione = instance.saldato or instance.movimento_origine_id
        if not is_compensazione and saldo < 0 and abs(saldo) > cliente.fido_massimo:
            testo = telegram_utils.msg_fido_superato(cliente, saldo, instance, using)
            transaction.on_commit(lambda t=testo: telegram_utils.notifica(using, t), using=using)
    except Exception as e:
        logger.error(f"Telegram: errore notifica movimento {instance.pk}: {e}")


@receiver(post_save, sender=MovimentoConti)
def movimento_conti_notifica_telegram(sender, instance, created, using, **kwargs):
    """Trigger #2: notifica i movimenti dei conti marcati con notifica_telegram."""
    try:
        if not created:
            return
        origine = instance.conto_origine
        destinazione = instance.conto_destinazione
        if (origine and origine.notifica_telegram) or (destinazione and destinazione.notifica_telegram):
            testo = telegram_utils.msg_movimento_conto(instance, using)
            transaction.on_commit(lambda: telegram_utils.notifica(using, testo), using=using)
    except Exception as e:
        logger.error(f"Telegram: errore notifica movimento conti {instance.pk}: {e}")