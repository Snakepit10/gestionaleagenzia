# -*- coding: utf-8 -*-
"""
Servizio con cache per il ledwall: unico punto che la view chiama.

- Interroga il provider (diretta.it) al massimo una volta per TTL:
  60s se c'e' almeno una partita live, 10 minuti altrimenti.
- Se il provider fallisce, continua a servire gli ULTIMI dati validi (senza
  mai schermo vuoto o errori tecnici); la pagina mostra in piccolo l'ora
  dell'ultimo aggiornamento riuscito.
- La cache e' in-process (per worker): sufficiente perche' il TTL limita gia'
  le chiamate a monte. Il ledwall legge solo il nostro endpoint.
"""
import threading
import time

from . import config
from .providers import get_provider

_lock = threading.Lock()
_cache = {'payload': None, 'ts': 0.0}   # ultima risposta servita
_last_good = {'payload': None}          # ultimo fetch riuscito


def _has_live(payload):
    if not payload:
        return False
    for c in payload.get('competitions', []):
        for m in c.get('matches', []):
            if m.get('status') == 'live':
                return True
    return False


def _ttl(payload):
    return config.CACHE['ttl_live'] if _has_live(payload) else config.CACHE['ttl_idle']


def get_payload(demo=False):
    """Ritorna il JSON normalizzato (con cache). Non solleva mai eccezioni."""
    if demo:
        try:
            p = get_provider(demo=True).fetch()
            p['stale'] = False
            return p
        except Exception:
            return {'updated': None, 'source': 'demo', 'competitions': [], 'stale': True}

    with _lock:
        now = time.time()
        cached = _cache['payload']
        if cached is not None and (now - _cache['ts']) < _ttl(cached):
            return cached

        try:
            payload = get_provider().fetch()
            payload['stale'] = False
            _cache['payload'] = payload
            _cache['ts'] = now
            _last_good['payload'] = payload
            return payload
        except Exception:
            # Fetch fallito: continua con l'ultimo valido, marcato 'stale'.
            fallback = _last_good['payload'] or _cache['payload']
            if fallback is not None:
                stale = dict(fallback)
                stale['stale'] = True
                # non aggiorno il timestamp di cache: riprovo al prossimo giro
                return stale
            return {'updated': None, 'source': config.PROVIDER, 'competitions': [], 'stale': True}
