"""
Servizio di notifiche Telegram per il gestionale.

Invio asincrono (thread daemon, fire-and-forget): le notifiche non rallentano né
fanno fallire le operazioni del gestionale. Se il token o la chat non sono
configurati, tutte le funzioni diventano no-op silenziose.

Routing: ogni agenzia ha la propria chat Telegram. A partire dall'alias del
database (`using`) si risale all'Agenzia corrispondente e al suo `telegram_chat_id`.
"""
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _get_chat_id(using):
    """
    Dato l'alias del database (es. 'goldbet_db', 'default'), ritorna il
    telegram_chat_id dell'agenzia corrispondente, oppure None se non configurato.
    """
    from .models import Agenzia

    try:
        # L'anagrafica delle agenzie vive sempre nel database 'default'.
        agenzia = Agenzia.objects.using('default').filter(database_name=using).first()
        if agenzia and agenzia.telegram_chat_id:
            return agenzia.telegram_chat_id.strip()
    except Exception as e:
        logger.error(f"Telegram: errore nel recupero chat_id per db '{using}': {e}")
    return None


def _nome_agenzia(using):
    """Nome leggibile dell'agenzia a partire dall'alias del database."""
    from .models import Agenzia

    try:
        agenzia = Agenzia.objects.using('default').filter(database_name=using).first()
        if agenzia:
            return agenzia.nome
    except Exception:
        pass
    return using


def _invia(chat_id, testo):
    """Esegue la chiamata HTTP a Telegram. Da eseguire in un thread separato."""
    import requests

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=token),
            json={
                'chat_id': chat_id,
                'text': testo,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            },
            timeout=5,
        )
        if response.status_code != 200:
            logger.error(
                f"Telegram: invio fallito (status {response.status_code}): {response.text}"
            )
    except Exception as e:
        logger.error(f"Telegram: eccezione durante l'invio: {e}")


def invia_messaggio(chat_id, testo):
    """
    Invia un messaggio Telegram in background. No-op se notifiche disattivate,
    token assente o chat_id mancante.
    """
    if not getattr(settings, 'TELEGRAM_NOTIFICHE_ATTIVE', True):
        return
    if not getattr(settings, 'TELEGRAM_BOT_TOKEN', ''):
        return
    if not chat_id:
        return

    thread = threading.Thread(target=_invia, args=(chat_id, testo), daemon=True)
    thread.start()


def notifica(using, testo):
    """
    Risolve la chat dell'agenzia associata al database `using` e invia `testo`.
    Pensata per essere chiamata dentro transaction.on_commit(...).
    """
    chat_id = _get_chat_id(using)
    if chat_id:
        invia_messaggio(chat_id, testo)


# ---------------------------------------------------------------------------
# Costruttori dei messaggi
# ---------------------------------------------------------------------------

def msg_nuovo_cliente(cliente, using):
    return (
        f"🆕 <b>Nuovo cliente</b> ({_nome_agenzia(using)})\n"
        f"Cliente: <b>{cliente.nome_completo}</b>\n"
        f"Fido massimo: {cliente.fido_massimo:.2f} €"
    )


def msg_aumento_fido(cliente, vecchio_fido, nuovo_fido, using):
    return (
        f"⬆️ <b>Fido aumentato</b> ({_nome_agenzia(using)})\n"
        f"Cliente: <b>{cliente.nome_completo}</b>\n"
        f"Da {vecchio_fido:.2f} € a {nuovo_fido:.2f} €"
    )


def msg_fido_superato(cliente, saldo, movimento, using):
    sforamento = abs(saldo) - cliente.fido_massimo
    return (
        f"⚠️ <b>Fido superato</b> ({_nome_agenzia(using)})\n"
        f"Cliente: <b>{cliente.nome_completo}</b>\n"
        f"Saldo: {saldo:.2f} € | Fido: {cliente.fido_massimo:.2f} €\n"
        f"Sforamento: <b>{sforamento:.2f} €</b>\n"
        f"Ultimo movimento: {movimento.get_tipo_display()} {movimento.importo:.2f} €"
    )


def msg_movimento_conto(movimento, using):
    return (
        f"💸 <b>Movimento conto</b> ({_nome_agenzia(using)})\n"
        f"{movimento}"
    )


def msg_movimento_cliente(movimento, saldo, using):
    cliente = movimento.cliente
    return (
        f"📝 <b>Movimento cliente</b> ({_nome_agenzia(using)})\n"
        f"Cliente: <b>{cliente.nome_completo}</b>\n"
        f"Operazione: {movimento.get_tipo_display()} {movimento.importo:.2f} €\n"
        f"Saldo aggiornato: {saldo:.2f} €"
    )
