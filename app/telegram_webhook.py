"""
Endpoint webhook per ricevere i messaggi inviati al bot Telegram.

Uso principale: impostare la soglia cassa di un'agenzia mandando un messaggio
nella sua chat (es. "soglia 5000"). L'agenzia viene identificata dal chat_id
del mittente, già associato in Agenzia.telegram_chat_id.

Sicurezza: l'endpoint è protetto da un segreto nel path dell'URL e dall'header
'X-Telegram-Bot-Api-Secret-Token' impostato da Telegram (setWebhook secret_token).
Agisce solo su chat_id già associati a un'agenzia.
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import telegram_utils
from .models import Agenzia

logger = logging.getLogger(__name__)

AIUTO = (
    "Comandi disponibili:\n"
    "• <code>soglia</code> — mostra la soglia cassa attuale\n"
    "• <code>soglia 5000</code> — imposta la soglia a 5000 €\n"
    "• <code>soglia off</code> — disattiva l'alert cassa"
)


def _parse_importo(testo):
    """Converte una stringa importo (accetta sia '.' che ',') in Decimal, o None."""
    try:
        return Decimal(testo.replace('.', '').replace(',', '.')) if ',' in testo else Decimal(testo)
    except (InvalidOperation, ValueError):
        return None


@csrf_exempt
@require_POST
def telegram_webhook(request, secret):
    # Verifica del segreto (path + header impostato da Telegram)
    atteso = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
    if not atteso or secret != atteso:
        return HttpResponseForbidden("forbidden")
    header_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if header_secret is not None and header_secret != atteso:
        return HttpResponseForbidden("forbidden")

    try:
        update = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponse(status=200)  # ignora payload non validi senza far ritentare

    message = update.get('message') or update.get('edited_message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    testo = (message.get('text') or '').strip()

    if chat_id is None or not testo:
        return HttpResponse(status=200)

    # Identifica l'agenzia dalla chat
    agenzia = Agenzia.objects.using('default').filter(telegram_chat_id=str(chat_id)).first()
    if not agenzia:
        # Chat non associata ad alcuna agenzia: logga il chat_id (utile per configurarla) e ignora
        logger.info(f"Telegram webhook: messaggio da chat non associata {chat_id}: {testo!r}")
        return HttpResponse(status=200)

    # Normalizza il comando: rimuove '/' iniziale ed eventuale '@NomeBot'
    parti = testo.split()
    comando = parti[0].lstrip('/').split('@')[0].lower()

    if comando == 'soglia':
        if len(parti) == 1:
            # Mostra la soglia attuale
            if agenzia.soglia_cassa is not None:
                risposta = f"Soglia cassa attuale per {agenzia.nome}: <b>{agenzia.soglia_cassa:.2f} €</b>"
            else:
                risposta = f"Nessuna soglia cassa impostata per {agenzia.nome}."
        elif parti[1].lower() in ('off', 'no', 'disattiva'):
            agenzia.soglia_cassa = None
            agenzia.save(using='default', update_fields=['soglia_cassa'])
            risposta = f"Alert cassa disattivato per {agenzia.nome}."
        else:
            valore = _parse_importo(parti[1])
            if valore is None or valore < 0:
                risposta = f"Valore non valido. Esempio: <code>soglia 5000</code>\n\n{AIUTO}"
            elif valore == 0:
                agenzia.soglia_cassa = None
                agenzia.save(using='default', update_fields=['soglia_cassa'])
                risposta = f"Alert cassa disattivato per {agenzia.nome}."
            else:
                agenzia.soglia_cassa = valore
                agenzia.save(using='default', update_fields=['soglia_cassa'])
                risposta = f"Soglia cassa per {agenzia.nome} impostata a <b>{valore:.2f} €</b>."
    else:
        risposta = AIUTO

    telegram_utils.invia_messaggio(str(chat_id), risposta)
    return HttpResponse(status=200)
