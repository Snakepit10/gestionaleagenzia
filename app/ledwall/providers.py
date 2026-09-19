# -*- coding: utf-8 -*-
"""
Provider dati per il ledwall calcio.

Ogni provider espone fetch() -> dict normalizzato:
  {
    "updated": "<iso8601>",
    "source": "diretta|demo",
    "competitions": [
       {"id","name","shortName","priority",
        "matches": [{"status":"live|scheduled|finished","minute","time",
                     "home","away","homeScore","awayScore","date"}]}
    ]
  }

Il provider e' SOSTITUIBILE: per usare un'API ufficiale (API-Football, football-data.org)
basta scrivere una nuova classe con lo stesso fetch() e cambiare PROVIDER in config.py.
Lo scraping di diretta.it e' fragile e soggetto ai termini d'uso del sito: se il feed
cambia formato o viene bloccato, DirettaProvider solleva un'eccezione e il servizio
continua a servire gli ultimi dati validi (vedi service.py).

Raccolta dati (DirettaProvider):
  - GET del feed "del giorno" calcio da https://www.diretta.it/x/feed/f_1_0_0_it_1
    con header x-fsign (firma statica del sito) + Referer.
  - Il feed e' un testo delimitato: record separati da '~', coppie chiave/valore
    separate da '¬' e '÷'. Una riga con 'ZA' e' l'intestazione della
    competizione ("PAESE: Torneo"); le righe con 'AA' sono le partite che seguono.
  - Frequenza: la pagina LED interroga solo il NOSTRO endpoint; il server chiama
    diretta.it al massimo una volta per TTL cache (60s con live, 10 min altrimenti).
"""
from datetime import datetime, timezone as _tz

import requests

from . import config

try:
    from zoneinfo import ZoneInfo
    _ROME = ZoneInfo(config.TIMEZONE)
except Exception:  # pragma: no cover
    _ROME = None

# Chiavi del feed FlashScore/diretta usate:
#   AA id, AD start(unix), AB status(1 sched,2 live,3 finita), AC fase, AO inizio periodo,
#   AE/AF nome casa/ospite, AG/AH gol casa/ospite.
# Codici fase (AC), verificati confrontando col minuto mostrato da diretta.it:
#   12 = 1o tempo (minuto = minuti da AO)
#   13 = 2o tempo (minuto = 45 + minuti da AO)
#   38 = INTERVALLO (nessun minuto: si mostra "INT")
# Altri codici (supplementari, rigori, ecc.) -> etichetta generica "LIVE".
_STATUS = {'1': 'scheduled', '2': 'live', '3': 'finished'}
_PHASE_BASE = {'12': 0, '13': 45}
_AC_INTERVALLO = '38'


def _parse_records(text):
    """Genera dict per ogni record del feed."""
    for rec in text.split('~'):
        if not rec:
            continue
        o = {}
        for part in rec.split('¬'):
            i = part.find('÷')
            if i > 0:
                o[part[:i]] = part[i + 1:]
        if o:
            yield o


def _short_team(name):
    if not name:
        return name
    return config.TEAM_ABBREVIATIONS.get(name, name)


def _logo(code):
    """Dal codice logo del feed (OA/OB) all'URL del nostro proxy con cache."""
    if not code:
        return None
    return 'api/logo/' + code


def _match_competition(za_name):
    """Ritorna la competizione di config per un'intestazione 'PAESE: Torneo', o None."""
    if not za_name:
        return None
    low = za_name.lower()
    for pat in config.EXCLUDE:
        if pat in low:
            return None
    # prima gli alias esatti (piu' precisi), poi il 'contains'
    for comp in config.COMPETITIONS:
        for alias in comp.get('aliases', []):
            if za_name == alias:
                return comp
    for comp in config.COMPETITIONS:
        c = comp.get('contains')
        if c and c in low:
            return comp
    return None


def _minute(ev, now_ts):
    ac = ev.get('AC')
    if ac == _AC_INTERVALLO:
        return 'INT'                 # intervallo: nessun minuto
    base = _PHASE_BASE.get(ac)
    ao = ev.get('AO')
    if base is None or not ao:
        return 'LIVE'                # supplementari/rigori/fase sconosciuta
    try:
        elapsed = int((now_ts - int(ao) + 30) // 60)   # minuti da inizio periodo, arrotondati
    except (TypeError, ValueError):
        return 'LIVE'
    return str(base + max(1, elapsed))


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _fmt_time(ad):
    try:
        ts = int(ad)
    except (TypeError, ValueError):
        return ''
    dt = datetime.fromtimestamp(ts, _tz.utc)
    if _ROME is not None:
        dt = dt.astimezone(_ROME)
    return dt.strftime('%H:%M')


def _fmt_date(ad):
    try:
        ts = int(ad)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(ts, _tz.utc)
    if _ROME is not None:
        dt = dt.astimezone(_ROME)
    return dt.strftime('%d/%m')


def _event_to_match(ev, now_ts, with_date=False):
    status = _STATUS.get(ev.get('AB'))
    if status is None:
        return None  # rinviata/sospesa/annullata: ignora
    m = {
        'status': status,
        'minute': _minute(ev, now_ts) if status == 'live' else None,
        'time': _fmt_time(ev.get('AD')) if status != 'finished' else _fmt_time(ev.get('AD')),
        'home': _short_team(ev.get('AE', '')),
        'away': _short_team(ev.get('AF', '')),
        'homeScore': _int_or_none(ev.get('AG')),
        'awayScore': _int_or_none(ev.get('AH')),
        'homeLogo': _logo(ev.get('OA')),
        'awayLogo': _logo(ev.get('OB')),
        'date': _fmt_date(ev.get('AD')) if with_date else None,
    }
    return m


def _collect(text, now_ts, with_date=False):
    """Raggruppa gli eventi del feed per competizione configurata."""
    buckets = {}  # comp id -> {comp, matches:[]}
    current = None
    for rec in _parse_records(text):
        if 'ZA' in rec:
            current = _match_competition(rec['ZA'])
        elif 'AA' in rec and current is not None:
            m = _event_to_match(rec, now_ts, with_date=with_date)
            if m is None:
                continue
            b = buckets.setdefault(current['id'], {'comp': current, 'matches': []})
            b['matches'].append(m)
    return buckets


_ORDER = {'live': 0, 'scheduled': 1, 'finished': 2}


def _build_competitions(buckets):
    comps = []
    for b in buckets.values():
        comp = b['comp']
        matches = sorted(b['matches'], key=lambda m: (_ORDER.get(m['status'], 3), m['time'] or ''))
        comps.append({
            'id': comp['id'], 'name': comp['name'], 'shortName': comp['shortName'],
            'priority': comp['priority'], 'matches': matches,
        })
    comps.sort(key=lambda c: c['priority'])
    return comps


class DirettaProvider:
    source = 'diretta'

    def _fetch_day(self, day):
        fid = config.FEED['day_feed'].format(day=day, tz=config.FEED['tz'])
        url = config.FEED['base_url'] + fid
        headers = dict(config.FEED['headers'])
        headers['x-fsign'] = config.FEED['xfsign']
        r = requests.get(url, headers=headers, timeout=config.FEED['timeout'])
        r.raise_for_status()
        txt = r.text
        if not txt or len(txt) < 20:
            raise RuntimeError('Feed diretta.it vuoto (day=%s)' % day)
        return txt

    def fetch(self):
        now_ts = int(datetime.now(_tz.utc).timestamp())
        text = self._fetch_day(0)
        buckets = _collect(text, now_ts, with_date=False)
        if buckets:
            comps = _build_competitions(buckets)
            return self._envelope(comps)

        # Nessuna partita oggi nelle competizioni configurate:
        # mostra ultimi risultati (ieri) e prossime partite (domani), con la data.
        fb = {}
        for day in (-1, 1):
            try:
                t = self._fetch_day(day)
            except Exception:
                continue
            for cid, b in _collect(t, now_ts, with_date=True).items():
                fb.setdefault(cid, {'comp': b['comp'], 'matches': []})['matches'].extend(b['matches'])
        return self._envelope(_build_competitions(fb))

    def _envelope(self, comps):
        return {
            'updated': datetime.now(_tz.utc).isoformat(timespec='seconds'),
            'source': self.source,
            'competitions': comps,
        }


class DemoProvider:
    """Dati fittizi per verificare grafica e scorrimento (?demo=1), senza rete."""
    source = 'demo'

    def fetch(self):
        return {
            'updated': datetime.now(_tz.utc).isoformat(timespec='seconds'),
            'source': self.source,
            'competitions': [
                {'id': 'serie-a', 'name': 'Serie A', 'shortName': 'SERIE A', 'priority': 10, 'matches': [
                    {'status': 'live', 'minute': '63', 'time': '20:45', 'home': 'Inter', 'away': 'Milan',
                     'homeScore': 2, 'awayScore': 1, 'date': None},
                    {'status': 'live', 'minute': '31', 'time': '20:45', 'home': 'Napoli', 'away': 'Roma',
                     'homeScore': 0, 'awayScore': 0, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '22:00', 'home': 'Juventus', 'away': 'Lazio',
                     'homeScore': None, 'awayScore': None, 'date': None},
                    {'status': 'finished', 'minute': None, 'time': '18:00', 'home': 'Atalanta', 'away': 'Torino',
                     'homeScore': 3, 'awayScore': 0, 'date': None},
                ]},
                {'id': 'champions', 'name': 'Champions League', 'shortName': 'CHAMPIONS', 'priority': 40, 'matches': [
                    {'status': 'live', 'minute': '78', 'time': '21:00', 'home': 'Real Madrid', 'away': 'Man City',
                     'homeScore': 1, 'awayScore': 1, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '21:00', 'home': 'Bayern', 'away': 'PSG',
                     'homeScore': None, 'awayScore': None, 'date': None},
                ]},
                {'id': 'premier', 'name': 'Premier League', 'shortName': 'PREMIER', 'priority': 70, 'matches': [
                    {'status': 'finished', 'minute': None, 'time': '16:30', 'home': 'Arsenal', 'away': 'Chelsea',
                     'homeScore': 2, 'awayScore': 2, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '18:30', 'home': 'Liverpool', 'away': 'Man Utd',
                     'homeScore': None, 'awayScore': None, 'date': None},
                ]},
                {'id': 'laliga', 'name': 'LaLiga', 'shortName': 'LALIGA', 'priority': 80, 'matches': [
                    {'status': 'live', 'minute': 'LIVE', 'time': '19:00', 'home': 'Barcelona', 'away': 'Betis',
                     'homeScore': 4, 'awayScore': 0, 'date': None},
                    {'status': 'finished', 'minute': None, 'time': '14:00', 'home': 'Atletico', 'away': 'Sociedad',
                     'homeScore': 1, 'awayScore': 0, 'date': None},
                ]},
            ],
        }


def get_provider(demo=False):
    if demo or config.PROVIDER == 'demo':
        return DemoProvider()
    return DirettaProvider()
