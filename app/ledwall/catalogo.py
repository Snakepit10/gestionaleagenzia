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
