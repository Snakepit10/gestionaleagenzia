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
    "• <code>soglia off</code> — disattiva l'alert cassa\n"
    "Se la chat è condivisa da più agenzie, indica l'agenzia: <code>soglia goldbet 5000</code>"
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

    # Identifica le agenzie associate alla chat (una chat puo' servire piu' agenzie)
    agenzie = list(Agenzia.objects.using('default').filter(telegram_chat_id=str(chat_id)))
    if not agenzie:
        # Chat non associata ad alcuna agenzia: logga il chat_id (utile per configurarla) e ignora
        logger.info(f"Telegram webhook: messaggio da chat non associata {chat_id}: {testo!r}")
        return HttpResponse(status=200)

    # Normalizza il comando: rimuove '/' iniziale ed eventuale '@NomeBot'
    parti = testo.split()
    comando = parti[0].lstrip('/').split('@')[0].lower()

    if comando != 'soglia':
        telegram_utils.invia_messaggio(str(chat_id), AIUTO)
        return HttpResponse(status=200)

    args = parti[1:]

    # Selettore agenzia opzionale come primo argomento (nome o codice), utile se la
    # chat e' condivisa da piu' agenzie: es. "soglia goldbet 5000".
    target = None
    if args:
        sel = args[0].lower()
        for a in agenzie:
            if sel == a.nome.lower() or sel == (a.codice or '').lower():
                target = a
                args = args[1:]
                break

    if target is None:
        if len(agenzie) == 1:
            target = agenzie[0]
        else:
            nomi = ', '.join(a.nome for a in agenzie)
            risposta = (f"Questa chat è associata a più agenzie ({nomi}).\n"
                        f"Specifica l'agenzia: <code>soglia &lt;agenzia&gt; &lt;valore&gt;</code>")
            telegram_utils.invia_messaggio(str(chat_id), risposta)
            return HttpResponse(status=200)

    if not args:
        # Mostra la soglia attuale dell'agenzia selezionata
        if target.soglia_cassa is not None:
            risposta = f"Soglia cassa attuale per {target.nome}: <b>{target.soglia_cassa:.2f} €</b>"
        else:
            risposta = f"Nessuna soglia cassa impostata per {target.nome}."
    elif args[0].lower() in ('off', 'no', 'disattiva'):
        target.soglia_cassa = None
        target.save(using='default', update_fields=['soglia_cassa'])
        risposta = f"Alert cassa disattivato per {target.nome}."
    else:
        valore = _parse_importo(args[0])
        if valore is None or valore < 0:
            risposta = f"Valore non valido. Esempio: <code>soglia 5000</code>\n\n{AIUTO}"
        elif valore == 0:
            target.soglia_cassa = None
            target.save(using='default', update_fields=['soglia_cassa'])
            risposta = f"Alert cassa disattivato per {target.nome}."
        else:
            target.soglia_cassa = valore
            target.save(using='default', update_fields=['soglia_cassa'])
            risposta = f"Soglia cassa per {target.nome} impostata a <b>{valore:.2f} €</b>."

    telegram_utils.invia_messaggio(str(chat_id), risposta)
    return HttpResponse(status=200)
