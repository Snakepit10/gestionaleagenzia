# -*- coding: utf-8 -*-
"""
Catalogo competizioni per il ledwall.

Serve a POPOLARE l'elenco delle competizioni (modello CompetizioneLedwall) partendo dal
feed di diretta.it: tutte le competizioni che compaiono nel feed (su piu' giorni), raggruppate
per nazione, importate **disattivate**. L'utente poi, dall'admin, accende quelle che vuole e
imposta bandiera / modalita' / ordine.

- `discover_from_feed()` interroga il feed su un intervallo di giorni e ritorna la lista di
  competizioni (dict) trovate, ordinate per nazione + nome.
- `write_json()` / `load_json()` salvano/caricano lo stesso elenco in un file JSON versionato
  nel repo (`competizioni_catalogo.json`): cosi' una migrazione puo' seminarlo in produzione
  senza dover chiamare la rete durante il deploy (deterministico).
- `upsert()` inserisce le competizioni mancanti (dedup sugli alias gia' presenti, cosi' non
  duplica quelle curate) senza toccare quelle esistenti; valorizza la nazione dove manca.
"""
import json
import os

from . import config

CATALOG_JSON = os.path.join(os.path.dirname(__file__), 'competizioni_catalogo.json')

# ---------------------------------------------------------------------------
# Set CURATO delle competizioni PRINCIPALI (le piu' giocate), raggruppate per nazione.
# Per le nazioni top: campionati fino alla terza serie + coppa. Match col feed diretta.it via
# `aliases` (nome esatto "PAESE: Torneo") oppure `contiene` (sottostringa, piu' robusta per le
# coppe / suffissi di stagione). Alcune competizioni fuori stagione ora compariranno con la
# partita appena tornano in calendario.  Campi: codice, nazione, nome, short, flag, alias, contiene.
# ---------------------------------------------------------------------------
_P = lambda codice, nazione, nome, short, flag, alias='', contiene='': {
    'codice': codice, 'nazione': nazione, 'nome': nome, 'short_name': short,
    'bandiera': flag, 'aliases': alias, 'contiene': contiene}

PRINCIPALI = [
    # Coppe / Nazionali internazionali
    _P('champions', 'Europa', 'Champions League', 'CHAMPIONS', 'eu', 'EUROPA: Champions League', 'champions league'),
    _P('europa', 'Europa', 'Europa League', 'EUROPA LG', 'eu', 'EUROPA: Europa League', 'europa league'),
    _P('conference', 'Europa', 'Conference League', 'CONFERENCE', 'eu', 'EUROPA: Conference League', 'conference league'),
    _P('nations', 'Europa', 'Nations League', 'NATIONS', 'eu', 'EUROPA: UEFA Nations League', 'uefa nations league'),
    _P('europei', 'Europa', 'Europei', 'EUROPEI', 'eu', '', 'campionato europeo'),
    _P('mondiali', 'Mondo', 'Mondiali', 'MONDIALI', '', '', 'coppa del mondo'),
    # Italia
    _P('serie-a', 'Italia', 'Serie A', 'SERIE A', 'it', 'ITALIA: Serie A'),
    _P('serie-b', 'Italia', 'Serie B', 'SERIE B', 'it', 'ITALIA: Serie B'),
    _P('italia-serie-c-girone-a', 'Italia', 'Serie C - Girone A', 'SERIE C-A', 'it', 'ITALIA: Serie C - Girone A'),
    _P('italia-serie-c-girone-b', 'Italia', 'Serie C - Girone B', 'SERIE C-B', 'it', 'ITALIA: Serie C - Girone B'),
    _P('italia-serie-c-girone-c', 'Italia', 'Serie C - Girone C', 'SERIE C-C', 'it', 'ITALIA: Serie C - Girone C'),
    _P('coppa-italia', 'Italia', 'Coppa Italia', 'COPPA ITALIA', 'it', 'ITALIA: Coppa Italia'),
    _P('supercoppa-italiana', 'Italia', 'Supercoppa Italiana', 'SUPERCOPPA', 'it', '', 'italia: supercoppa'),
    # Inghilterra
    _P('premier', 'Inghilterra', 'Premier League', 'PREMIER', 'gb-eng', 'INGHILTERRA: Premier League'),
    _P('championship', 'Inghilterra', 'Championship', 'CHAMPIONSHIP', 'gb-eng', 'INGHILTERRA: Championship'),
    _P('league-one', 'Inghilterra', 'League One', 'LEAGUE ONE', 'gb-eng', 'INGHILTERRA: League One'),
    _P('league-two', 'Inghilterra', 'League Two', 'LEAGUE TWO', 'gb-eng', 'INGHILTERRA: League Two'),
    _P('fa-cup', 'Inghilterra', 'FA Cup', 'FA CUP', 'gb-eng', 'INGHILTERRA: FA Cup', 'inghilterra: fa cup'),
    _P('efl-cup', 'Inghilterra', 'EFL Cup', 'EFL CUP', 'gb-eng', 'INGHILTERRA: EFL Cup', 'carabao'),
    # Spagna
    _P('laliga', 'Spagna', 'LaLiga', 'LALIGA', 'es', 'SPAGNA: LaLiga'),
    _P('laliga2', 'Spagna', 'LaLiga2', 'LALIGA2', 'es', 'SPAGNA: LaLiga2'),
    _P('spagna-primera-rfef', 'Spagna', 'Primera RFEF', 'PRIMERA RFEF', 'es', '', 'spagna: primera rfef'),
    _P('spagna-copa-del-rey', 'Spagna', 'Copa del Rey', 'COPA DEL REY', 'es', 'SPAGNA: Copa del Rey'),
    # Germania
    _P('bundesliga', 'Germania', 'Bundesliga', 'BUNDESLIGA', 'de', 'GERMANIA: Bundesliga'),
    _P('germania-2-bundesliga', 'Germania', '2. Bundesliga', '2.BUNDESLIGA', 'de', 'GERMANIA: 2. Bundesliga'),
    _P('germania-3-liga', 'Germania', '3. Liga', '3. LIGA', 'de', 'GERMANIA: 3. Liga'),
    _P('germania-coppa', 'Germania', 'Coppa di Germania', 'DFB POKAL', 'de', '', 'germania: coppa'),
    # Francia
    _P('ligue1', 'Francia', 'Ligue 1', 'LIGUE 1', 'fr', 'FRANCIA: Ligue 1'),
    _P('francia-ligue-2', 'Francia', 'Ligue 2', 'LIGUE 2', 'fr', 'FRANCIA: Ligue 2'),
    _P('francia-coppa', 'Francia', 'Coppa di Francia', 'COPPA FRA', 'fr', '', 'francia: coppa'),
    # Portogallo
    _P('portogallo-primeira', 'Portogallo', 'Primeira Liga', 'PRIMEIRA', 'pt', 'PORTOGALLO: Liga Portugal', 'portogallo: liga portugal'),
    _P('portogallo-taca', 'Portogallo', 'Taca de Portugal', 'TACA', 'pt', 'PORTOGALLO: Taça de Portugal', 'portogallo: ta'),
    # Olanda
    _P('olanda-eredivisie', 'Olanda', 'Eredivisie', 'EREDIVISIE', 'nl', 'OLANDA: Eredivisie'),
    _P('olanda-knvb', 'Olanda', 'KNVB Beker', 'KNVB', 'nl', 'OLANDA: KNVB Beker'),
    # Altre leghe molto seguite
    _P('brasile-serie-a', 'Brasile', 'Brasileirao', 'BRASILE A', 'br', 'BRASILE: Serie A'),
    _P('argentina-liga-profesional-clausura', 'Argentina', 'Liga Profesional', 'LIGA ARG', 'ar', '', 'argentina: liga profesional'),
    _P('usa-mls', 'Usa', 'MLS', 'MLS', 'us', 'USA: MLS'),
    _P('messico-liga-mx-apertura', 'Messico', 'Liga MX', 'LIGA MX', 'mx', '', 'messico: liga mx'),
    _P('arabia-saudita-pro-league', 'Arabia Saudita', 'Saudi Pro League', 'SAUDI', 'sa', '', 'arabia saudita: saudi'),
    # Turchia
    _P('turchia-super-lig', 'Turchia', 'Super Lig', 'SUPER LIG', 'tr', 'TURCHIA: Super Lig'),
    _P('turchia-1-lig', 'Turchia', '1. Lig', '1. LIG', 'tr', 'TURCHIA: 1. Lig'),
    _P('turchia-coppa', 'Turchia', 'Coppa di Turchia', 'COPPA TUR', 'tr', '', 'turchia: coppa'),
    # Belgio
    _P('belgio-jupiler', 'Belgio', 'Jupiler Pro League', 'JUPILER', 'be', 'BELGIO: Jupiler League'),
    _P('belgio-challenger', 'Belgio', 'Challenger Pro League', 'CHALLENGER', 'be', 'BELGIO: Challenger Pro League'),
    _P('belgio-coppa', 'Belgio', 'Coppa del Belgio', 'COPPA BEL', 'be', 'BELGIO: Coppa del Belgio'),
    # Scozia
    _P('scozia-premiership', 'Scozia', 'Premiership', 'PREMIERSHIP', 'gb-sct', 'SCOZIA: Premiership'),
    _P('scozia-championship', 'Scozia', 'Championship', 'SCO CHAMP', 'gb-sct', 'SCOZIA: Championship'),
    _P('scozia-coppa', 'Scozia', 'Coppa di Scozia', 'COPPA SCO', 'gb-sct', '', 'scozia: coppa'),
]


def _parse_records(text):
    for rec in text.split('~'):
        o = {}
        for part in rec.split('¬'):
            i = part.find('÷')
            if i > 0:
                o[part[:i]] = part[i + 1:]
        if o:
            yield o


def _build_catalog(items):
    """items: iterabile di dict {za, zy} -> lista di competizioni normalizzate."""
    from django.utils.text import slugify
    out, seen_cod = [], set()
    for it in items:
        za = (it.get('za') or '').strip()
        zy = (it.get('zy') or '').strip()
        if not za or ':' not in za:
            continue
        paese, _, torneo = za.partition(':')
        paese = paese.strip()
        torneo = torneo.strip()
        cod = (slugify(za) or slugify(torneo))[:40]
        if not cod or cod in seen_cod:
            continue
        seen_cod.add(cod)
        out.append({
            'codice': cod,
            'nazione': paese.title(),
            'nome': (torneo or za)[:80],
            'short_name': (torneo or za).upper()[:20],
            'aliases': za,
            'bandiera': config.COUNTRY_ISO.get(zy.lower(), ''),
        })
    out.sort(key=lambda c: (c['nazione'], c['nome']))
    return out


def discover_from_feed(days=None):
    """Interroga il feed su piu' giorni e ritorna il catalogo (lista di dict)."""
    import requests
    if days is None:
        days = range(-1, 8)
    headers = dict(config.FEED['headers'])
    headers['x-fsign'] = config.FEED['xfsign']
    found = {}  # za -> {za, zy}
    for day in days:
        fid = config.FEED['day_feed'].format(day=day, tz=config.FEED['tz'])
        try:
            r = requests.get(config.FEED['base_url'] + fid, headers=headers, timeout=config.FEED['timeout'])
            r.raise_for_status()
            txt = r.text
        except Exception:
            continue
        for rec in _parse_records(txt):
            za = rec.get('ZA')
            if not za or ':' not in za:
                continue
            low = za.lower()
            if any(x in low for x in config.EXCLUDE):
                continue
            if za not in found:
                found[za] = {'za': za, 'zy': rec.get('ZY', '')}
    return _build_catalog(found.values())


def write_json(catalog, path=CATALOG_JSON):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1, sort_keys=True)


def load_json(path=CATALOG_JSON):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def sync_principali(Model, using='default', attiva=True):
    """Tiene SOLO le competizioni principali: elimina tutte le altre e crea/aggiorna quelle
    dell'elenco PRINCIPALI (attive). Ritorna (create, aggiornate, eliminate)."""
    codici = [c['codice'] for c in PRINCIPALI]
    eliminate = Model.objects.using(using).exclude(codice__in=codici).delete()[0]
    creati = aggiornati = 0
    for i, c in enumerate(PRINCIPALI):
        defaults = {
            'nome': c['nome'], 'nazione': c['nazione'], 'short_name': c['short_name'],
            'bandiera': c['bandiera'], 'aliases': c['aliases'], 'contiene': c['contiene'],
            'modalita': 'entrambe', 'ordine': 10 + i,
        }
        if attiva:
            defaults['attivo'] = True
        obj, made = Model.objects.using(using).update_or_create(codice=c['codice'], defaults=defaults)
        creati += 1 if made else 0
        aggiornati += 0 if made else 1
    return creati, aggiornati, eliminate


def upsert(Model, catalog, using='default'):
    """Crea le competizioni mancanti (dedup sugli alias), lascia intatte quelle esistenti,
    e valorizza la nazione dove manca. Ritorna il numero di righe create."""
    existing = list(Model.objects.using(using).all())
    alias_set = set()
    for r in existing:
        for a in (r.aliases or '').splitlines():
            a = a.strip()
            if a:
                alias_set.add(a)
    created = 0
    for i, c in enumerate(catalog):
        if c['aliases'] in alias_set:
            continue
        _, made = Model.objects.using(using).get_or_create(
            codice=c['codice'],
            defaults={
                'nome': c['nome'], 'short_name': c['short_name'], 'nazione': c['nazione'],
                'aliases': c['aliases'], 'bandiera': c['bandiera'], 'modalita': 'entrambe',
                'attivo': False, 'ordine': 1000 + i,
            },
        )
        if made:
            created += 1
            alias_set.add(c['aliases'])
    # Valorizza la nazione delle competizioni gia' presenti (es. le curate) se mancante.
    for r in existing:
        if not (getattr(r, 'nazione', '') or '').strip():
            first = next((a.strip() for a in (r.aliases or '').splitlines() if a.strip()), '')
            if ':' in first:
                r.nazione = first.split(':', 1)[0].strip().title()
                r.save(using=using, update_fields=['nazione'])
    return created
