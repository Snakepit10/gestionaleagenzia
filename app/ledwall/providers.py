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


def _logo(name, code, hd=True):
    """URL del logo (proxy nostro). Se HD attivo e la squadra e' mappata, usa il logo
    ad alta risoluzione di API-Football; altrimenti il logo di diretta.it; altrimenti None."""
    if hd:
        tid = config.APIFOOTBALL_TEAM_IDS.get((name or '').strip().lower())
        if tid:
            return 'api/logo/af/%d.png' % tid
    if code:
        return 'api/logo/d/' + code
    return None


def _load_competizioni():
    """Competizioni attive dal DB (gestite in admin); fallback a config.COMPETITIONS."""
    try:
        from ..models import CompetizioneLedwall
        rows = list(CompetizioneLedwall.objects.using('default')
                    .filter(attivo=True).order_by('ordine', 'nome'))
        if rows:
            out = []
            for r in rows:
                aliases = [a.strip() for a in (r.aliases or '').splitlines() if a.strip()]
                out.append({'id': r.codice, 'name': r.nome, 'shortName': r.short_name,
                            'priority': r.ordine, 'aliases': aliases,
                            'contains': (r.contiene or '').strip().lower() or None,
                            'flag': (r.bandiera or '').strip().lower()})
            return out
    except Exception:
        pass
    return [{'id': c['id'], 'name': c['name'], 'shortName': c['shortName'],
             'priority': c['priority'], 'aliases': c.get('aliases', []),
             'contains': c.get('contains'), 'flag': c.get('flag', '')} for c in config.COMPETITIONS]


def _load_impostazioni():
    """Filtri (quali partite mostrare) dal DB; default se non disponibili."""
    d = {'live': True, 'oggi_sched': True, 'oggi_fin': True, 'domani': False, 'hd': True}
    try:
        from ..models import ImpostazioniLedwall
        o = ImpostazioniLedwall.get_solo()
        d['live'] = o.mostra_live
        d['oggi_sched'] = o.mostra_oggi_in_programma
        d['oggi_fin'] = o.mostra_oggi_finite
        d['domani'] = o.mostra_domani
        d['hd'] = o.loghi_hd
    except Exception:
        pass
    return d


def _match_competition(za_name, comps):
    """Ritorna la competizione per un'intestazione 'PAESE: Torneo', o None."""
    if not za_name:
        return None
    low = za_name.lower()
    for pat in config.EXCLUDE:
        if pat in low:
            return None
    for comp in comps:                      # prima gli alias esatti
        for alias in comp.get('aliases', []):
            if za_name == alias:
                return comp
    for comp in comps:                      # poi il 'contains'
        c = comp.get('contains')
        if c and c in low:
            return comp
    return None


def _resolve_flag(comp, zy):
    """Codice bandiera per la competizione. Priorita': override esplicito (campo admin
    'bandiera' o config 'flag'); altrimenti derivato dal PAESE del feed diretta (ZY, in
    inglese) tramite config.COUNTRY_ISO. Vuoto se sconosciuto (nessuna bandiera mostrata)."""
    f = (comp.get('flag') or '').strip().lower()
    if f:
        return f
    return config.COUNTRY_ISO.get((zy or '').strip().lower(), '')


def _flag_url(code):
    return ('api/flag/' + code) if code else None


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


def _event_to_match(ev, now_ts, with_date=False, hd=True):
    status = _STATUS.get(ev.get('AB'))
    if status is None:
        return None  # rinviata/sospesa/annullata: ignora
    home = _short_team(ev.get('AE', ''))
    away = _short_team(ev.get('AF', ''))
    m = {
        'status': status,
        'minute': _minute(ev, now_ts) if status == 'live' else None,
        'time': _fmt_time(ev.get('AD')),
        'home': home,
        'away': away,
        'homeScore': _int_or_none(ev.get('AG')),
        'awayScore': _int_or_none(ev.get('AH')),
        'homeLogo': _logo(home, ev.get('OA'), hd),
        'awayLogo': _logo(away, ev.get('OB'), hd),
        'date': _fmt_date(ev.get('AD')) if with_date else None,
    }
    return m


def _collect(text, now_ts, comps, with_date=False, hd=True):
    """Raggruppa gli eventi del feed per competizione configurata."""
    buckets = {}  # comp id -> {comp, flag, matches:[]}
    current = None
    current_flag = ''
    for rec in _parse_records(text):
        if 'ZA' in rec:
            current = _match_competition(rec['ZA'], comps)
            current_flag = _resolve_flag(current, rec.get('ZY')) if current else ''
        elif 'AA' in rec and current is not None:
            m = _event_to_match(rec, now_ts, with_date=with_date, hd=hd)
            if m is None:
                continue
            b = buckets.setdefault(current['id'], {'comp': current, 'flag': current_flag, 'matches': []})
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
            'priority': comp['priority'], 'flag': _flag_url(b.get('flag', '')), 'matches': matches,
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
        comps = _load_competizioni()
        imp = _load_impostazioni()

        hd = imp.get('hd', True)
        text = self._fetch_day(0)
        buckets = _collect(text, now_ts, comps, with_date=False, hd=hd)

        # Filtra le partite di oggi secondo gli interruttori dell'admin.
        def keep_today(m):
            if m['status'] == 'live':
                return imp['live']
            if m['status'] == 'scheduled':
                return imp['oggi_sched']
            if m['status'] == 'finished':
                return imp['oggi_fin']
            return False
        for b in buckets.values():
            b['matches'] = [m for m in b['matches'] if keep_today(m)]

        # Aggiungi le partite in programma DOMANI (se attivo), con la data.
        if imp['domani']:
            try:
                t1 = self._fetch_day(1)
                for cid, b in _collect(t1, now_ts, comps, with_date=True, hd=hd).items():
                    sched = [m for m in b['matches'] if m['status'] == 'scheduled']
                    if sched:
                        buckets.setdefault(cid, {'comp': b['comp'], 'flag': b.get('flag', ''), 'matches': []})['matches'].extend(sched)
            except Exception:
                pass

        buckets = {k: v for k, v in buckets.items() if v['matches']}
        if buckets:
            return self._envelope(_build_competitions(buckets))

        # Niente da mostrare: ultimi risultati (ieri) + prossime partite (domani), con la data.
        fb = {}
        for day in (-1, 1):
            try:
                t = self._fetch_day(day)
            except Exception:
                continue
            for cid, b in _collect(t, now_ts, comps, with_date=True, hd=hd).items():
                fb.setdefault(cid, {'comp': b['comp'], 'flag': b.get('flag', ''), 'matches': []})['matches'].extend(b['matches'])
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
                {'id': 'serie-a', 'name': 'Serie A', 'shortName': 'SERIE A', 'priority': 10,
                 'flag': 'api/flag/it', 'matches': [
                    {'status': 'live', 'minute': '63', 'time': '20:45', 'home': 'Inter', 'away': 'Milan',
                     'homeScore': 2, 'awayScore': 1, 'date': None},
                    {'status': 'live', 'minute': '31', 'time': '20:45', 'home': 'Napoli', 'away': 'Roma',
                     'homeScore': 0, 'awayScore': 0, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '22:00', 'home': 'Juventus', 'away': 'Lazio',
                     'homeScore': None, 'awayScore': None, 'date': None},
                    {'status': 'finished', 'minute': None, 'time': '18:00', 'home': 'Atalanta', 'away': 'Torino',
                     'homeScore': 3, 'awayScore': 0, 'date': None},
                ]},
                {'id': 'champions', 'name': 'Champions League', 'shortName': 'CHAMPIONS', 'priority': 40,
                 'flag': 'api/flag/eu', 'matches': [
                    {'status': 'live', 'minute': '78', 'time': '21:00', 'home': 'Real Madrid', 'away': 'Man City',
                     'homeScore': 1, 'awayScore': 1, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '21:00', 'home': 'Bayern', 'away': 'PSG',
                     'homeScore': None, 'awayScore': None, 'date': None},
                ]},
                {'id': 'premier', 'name': 'Premier League', 'shortName': 'PREMIER', 'priority': 70,
                 'flag': 'api/flag/gb-eng', 'matches': [
                    {'status': 'finished', 'minute': None, 'time': '16:30', 'home': 'Arsenal', 'away': 'Chelsea',
                     'homeScore': 2, 'awayScore': 2, 'date': None},
                    {'status': 'scheduled', 'minute': None, 'time': '18:30', 'home': 'Liverpool', 'away': 'Man Utd',
                     'homeScore': None, 'awayScore': None, 'date': None},
                ]},
                {'id': 'laliga', 'name': 'LaLiga', 'shortName': 'LALIGA', 'priority': 80,
                 'flag': 'api/flag/es', 'matches': [
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
