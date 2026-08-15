"""
Client per il portale CAST Agent (cast-agent.goldbet.it).

Flusso in due passi, con l'operatore che risolve il CAPTCHA nella pagina
"Estrazione saldi" del gestionale:

1. prepara_login(): apre la pagina di login del portale, estrae i token
   nascosti del form e scarica l'immagine CAPTCHA. Lo stato (cookie + token)
   viene conservato nella sessione Django dell'operatore.
2. esegui_login(stato, username, password, codice): completa il POST /login
   con le credenziali digitate dall'operatore e il codice CAPTCHA.
3. analizza_saldi(session): dopo il login cerca i saldi nelle pagine del
   portale e raccoglie informazioni diagnostiche (valori candidati e link)
   utili a calibrare l'estrazione.

Le credenziali NON vengono mai salvate: restano nel form e nella richiesta.
"""
import base64
import logging
import re
from decimal import Decimal, InvalidOperation

import requests

logger = logging.getLogger(__name__)

URL_BASE = 'https://cast-agent.goldbet.it'
TIMEOUT = 15
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gestionale-Agenzia'


def _nuova_session():
    s = requests.Session()
    s.headers.update({'User-Agent': USER_AGENT})
    return s


def _estrai_campo_hidden(html, nome):
    m = re.search(
        r'name="%s"[^>]*value="([^"]*)"' % re.escape(nome), html
    ) or re.search(
        r'value="([^"]*)"[^>]*name="%s"' % re.escape(nome), html
    )
    return m.group(1) if m else None


def prepara_login(url_base=URL_BASE):
    """
    Apre la pagina di login e prepara lo stato per il secondo passo.
    Ritorna {'ok': True, 'stato': {...}, 'captcha_b64': str} oppure
    {'ok': False, 'errore': str}.
    """
    try:
        s = _nuova_session()
        r = s.get(f"{url_base}/true", timeout=TIMEOUT)
        if r.status_code != 200:
            return {'ok': False, 'errore': f"Il portale ha risposto {r.status_code}"}
        html = r.text

        campi = {}
        for nome in ('DNTCaptchaText', 'DNTCaptchaToken', '__RequestVerificationToken'):
            valore = _estrai_campo_hidden(html, nome)
            if valore is None:
                return {'ok': False, 'errore': f"Campo '{nome}' non trovato nella pagina di login (il portale è cambiato?)"}
            campi[nome] = valore

        m = re.search(r'id="dntCaptchaImg"[^>]*src="([^"]+)"', html) or \
            re.search(r'src="(/captcha/[^"]+)"', html)
        if not m:
            return {'ok': False, 'errore': "Immagine CAPTCHA non trovata nella pagina di login"}
        captcha_url = m.group(1)
        if captcha_url.startswith('/'):
            captcha_url = url_base + captcha_url

        r_img = s.get(captcha_url, timeout=TIMEOUT, headers={'Referer': f"{url_base}/true"})
        if r_img.status_code != 200 or not r_img.content:
            return {'ok': False, 'errore': "Impossibile scaricare l'immagine CAPTCHA"}

        stato = {
            'url_base': url_base,
            'cookies': s.cookies.get_dict(),
            'campi': campi,
        }
        return {
            'ok': True,
            'stato': stato,
            'captcha_b64': base64.b64encode(r_img.content).decode(),
        }
    except requests.RequestException as e:
        logger.error(f"CAST: errore di rete in prepara_login: {e}")
        return {'ok': False, 'errore': f"Errore di rete verso il portale: {e}"}


def esegui_login(stato, username, password, codice_captcha):
    """
    Completa il login con le credenziali e il codice CAPTCHA.
    Ritorna {'ok': True, 'session': requests.Session} oppure {'ok': False, 'errore': str}.
    """
    try:
        url_base = stato.get('url_base', URL_BASE)
        s = _nuova_session()
        for k, v in (stato.get('cookies') or {}).items():
            s.cookies.set(k, v)

        dati = dict(stato.get('campi') or {})
        dati.update({
            'Username': username,
            'Password': password,
            'DNTCaptchaInputText': codice_captcha.strip(),
        })

        r = s.post(
            f"{url_base}/login",
            data=dati,
            timeout=TIMEOUT,
            headers={'Referer': f"{url_base}/true"},
            allow_redirects=True,
        )

        if 'DNTCaptchaInputText' in r.text or 'name="Password"' in r.text:
            # Siamo ancora sulla pagina di login: credenziali o captcha errati
            m = re.search(r'validation-summary[^>]*>(.*?)</div>', r.text, re.S)
            dettaglio = ''
            if m:
                dettaglio = re.sub(r'<[^>]+>', ' ', m.group(1))
                dettaglio = ' '.join(dettaglio.split())
            return {'ok': False, 'errore': dettaglio or 'Login non riuscito: verifica credenziali e codice CAPTCHA.'}

        return {'ok': True, 'session': s}
    except requests.RequestException as e:
        logger.error(f"CAST: errore di rete in esegui_login: {e}")
        return {'ok': False, 'errore': f"Errore di rete verso il portale: {e}"}


def _estrai_token_balance(html):
    """Estrae il token 'id' usato dalle chiamate API di /balanceaccount."""
    m = re.search(r'api/BalanceAccount\?id=([^&"\'\s]+)', html)
    if m:
        return m.group(1)
    # fallback: token lungo assegnato a una variabile/attributo vicino a 'BalanceAccount'
    m = re.search(r'BalanceAccount.{0,200}?["\']([A-Za-z0-9._-]{40,})["\']', html, re.S)
    return m.group(1) if m else None


def _ultimo_saldo_del_giorno(voci):
    """
    Dalle voci dell'API (lista di dict con DataOra e Saldo) ritorna il Saldo
    della voce con DataOra più recente, come Decimal. None se lista vuota.
    """
    from datetime import datetime

    migliore = None
    migliore_dt = None
    for voce in voci:
        try:
            dt = datetime.fromisoformat(voce['DataOra'])
        except (KeyError, ValueError):
            continue
        if migliore_dt is None or dt > migliore_dt:
            migliore_dt = dt
            migliore = voce
    if migliore is None:
        return None
    try:
        return Decimal(str(migliore['Saldo'])).quantize(Decimal('0.01'))
    except (KeyError, InvalidOperation):
        return None


def estrai_saldi_giornalieri(session, giorni, url_base=URL_BASE):
    """
    Estrae l'ultimo saldo di ciascuna giornata richiesta dall'API BalanceAccount.
    `giorni` è una lista di date. Ritorna:
      {'ok': True, 'saldi': {date: Decimal|None}} (None = nessun movimento quel giorno)
      oppure {'ok': False, 'errore': str}.
    """
    import time as _time

    try:
        r = session.get(f"{url_base}/balanceaccount", timeout=TIMEOUT)
        token = _estrai_token_balance(r.text)
        if not token:
            return {'ok': False, 'errore': "Token API non trovato nella pagina /balanceaccount (portale cambiato?)"}

        saldi = {}
        for giorno in giorni:
            data_str = giorno.strftime('%Y/%m/%d 00:00:00')
            r_api = session.get(
                f"{url_base}/api/BalanceAccount",
                params={
                    'id': token,
                    'dataInizio': data_str,
                    'dataFine': data_str,
                    'idOperatore': '',
                    'idProdotto': '',
                    'idTipoOperazione': '',
                    '_': str(int(_time.time() * 1000)),
                },
                timeout=TIMEOUT,
                headers={'Referer': f"{url_base}/balanceaccount"},
            )
            if r_api.status_code != 200:
                return {'ok': False, 'errore': f"API BalanceAccount ha risposto {r_api.status_code} per il {giorno.strftime('%d/%m/%Y')}"}
            try:
                voci = r_api.json().get('data') or []
            except ValueError:
                return {'ok': False, 'errore': f"Risposta API non valida per il {giorno.strftime('%d/%m/%Y')} (sessione scaduta?)"}
            saldi[giorno] = _ultimo_saldo_del_giorno(voci)

        return {'ok': True, 'saldi': saldi}
    except requests.RequestException as e:
        logger.error(f"CAST: errore di rete in estrai_saldi_giornalieri: {e}")
        return {'ok': False, 'errore': f"Errore di rete verso il portale: {e}"}


def _testo_pulito(html):
    html = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    html = re.sub(r'<style.*?</style>', ' ', html, flags=re.S)
    testo = re.sub(r'<[^>]+>', ' ', html)
    return ' '.join(testo.split())


def _parse_importo_it(valore):
    try:
        return Decimal(valore.replace('.', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        return None


def analizza_saldi(session, url_base=URL_BASE):
    """
    Analizza la pagina principale del portale dopo il login.
    Ritorna {'saldo': Decimal|None, 'candidati': [(etichetta, valore)], 'link': [(testo, href)]}.
    - 'saldo' è valorizzato se viene individuato un unico valore etichettato 'saldo'.
    - 'candidati' e 'link' servono da diagnostica per calibrare l'estrazione.
    """
    risultato = {'saldo': None, 'candidati': [], 'link': []}
    try:
        r = session.get(f"{url_base}/", timeout=TIMEOUT)
        html = r.text

        # Link interni (menu) per capire dove vive lo storico saldi
        for m in re.finditer(r'<a[^>]+href="(/[^"#][^"]*)"[^>]*>(.*?)</a>', html, re.S):
            href, testo = m.group(1), ' '.join(re.sub(r'<[^>]+>', ' ', m.group(2)).split())
            if testo and (testo, href) not in risultato['link']:
                risultato['link'].append((testo, href))
        risultato['link'] = risultato['link'][:40]

        # Valori monetari vicini alla parola 'saldo'
        testo = _testo_pulito(html)
        for m in re.finditer(r'(?i)([\w\s/.-]{0,40}saldo[\w\s/.-]{0,40})[:\s]*(-?\d{1,3}(?:\.\d{3})*,\d{2})', testo):
            etichetta = ' '.join(m.group(1).split())[-50:]
            risultato['candidati'].append((etichetta, m.group(2)))

        if len(risultato['candidati']) == 1:
            risultato['saldo'] = _parse_importo_it(risultato['candidati'][0][1])

        return risultato
    except requests.RequestException as e:
        logger.error(f"CAST: errore di rete in analizza_saldi: {e}")
        return risultato
