# -*- coding: utf-8 -*-
"""
Configurazione UNICA del ledwall calcio.

Qui si decide:
  - quali competizioni mostrare e in che ordine di priorita' (le italiane per prime);
  - le abbreviazioni dei nomi squadra (forma breve);
  - i parametri della fonte dati (diretta.it) e della cache.

Per aggiungere/togliere una competizione basta modificare COMPETITIONS: non serve
toccare la pagina ne' le view. Ogni competizione elenca gli "alias" (il nome esatto
usato da diretta.it, nel formato "PAESE: Torneo") e, opzionalmente, un "contains"
(sottostringa, utile per fasi/qualificazioni). Il campo shortName e' l'etichetta gialla
mostrata sul ledwall.
"""

# --- Fonte dati: feed di diretta.it (formato FlashScore, delimitato) ---------
# Il feed "del giorno" per il calcio (sport id 1). day=0 oggi, -1 ieri, +1 domani.
# NB: l'header x-fsign e' una firma statica del sito; se un giorno il feed smette di
# rispondere (403/empty), aggiornare qui XFSIGN oppure passare a un provider con API
# ufficiale (vedi providers.py -> get_provider / PROVIDER).
FEED = {
    'base_url': 'https://www.diretta.it/x/feed/',   # host che risponde lato server
    'day_feed': 'f_1_{day}_{tz}_it_1',              # {day} offset, {tz} indice fuso
    'tz': 0,
    'xfsign': 'SW9D1eZo',
    'timeout': 20,
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9; ledwall) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/96 Mobile Safari/537.36',
        'Referer': 'https://www.diretta.it/',
        'Origin': 'https://www.diretta.it',
        'Accept': '*/*',
        'Accept-Language': 'it-IT,it;q=0.9',
        'x-requested-with': 'XMLHttpRequest',
    },
}

# Provider dati attivo: 'diretta' (scraping) oppure 'demo' (dati fittizi).
# Sostituibile con un provider ad API ufficiale mantenendo lo stesso JSON.
PROVIDER = 'diretta'

# --- Cache -------------------------------------------------------------------
CACHE = {
    'ttl_live': 60,       # secondi, quando c'e' almeno una partita live
    'ttl_idle': 600,      # secondi, altrimenti (10 minuti)
}

# Fuso per formattare gli orari delle partite.
TIMEZONE = 'Europe/Rome'

# --- Competizioni (ordine = priorita', italiane per prime) -------------------
# priority: numero piu' basso = piu' in alto. name: nome esteso. shortName: etichetta LED.
# aliases: nomi ESATTI di diretta.it ("PAESE: Torneo"). contains: match per sottostringa.
COMPETITIONS = [
    {'id': 'serie-a',     'name': 'Serie A',           'shortName': 'SERIE A',    'priority': 10,
     'aliases': ['ITALIA: Serie A']},
    {'id': 'serie-b',     'name': 'Serie B',           'shortName': 'SERIE B',    'priority': 20,
     'aliases': ['ITALIA: Serie B']},
    {'id': 'coppa-italia','name': 'Coppa Italia',      'shortName': 'COPPA ITALIA','priority': 30,
     'aliases': ['ITALIA: Coppa Italia']},
    {'id': 'champions',   'name': 'Champions League',  'shortName': 'CHAMPIONS',  'priority': 40,
     'aliases': ['EUROPA: Champions League'], 'contains': 'champions league'},
    {'id': 'europa',      'name': 'Europa League',     'shortName': 'EUROPA LG',  'priority': 50,
     'aliases': ['EUROPA: Europa League'], 'contains': 'europa league'},
    {'id': 'conference',  'name': 'Conference League', 'shortName': 'CONFERENCE', 'priority': 60,
     'aliases': ['EUROPA: Conference League'], 'contains': 'conference league'},
    {'id': 'premier',     'name': 'Premier League',    'shortName': 'PREMIER',    'priority': 70,
     'aliases': ['INGHILTERRA: Premier League']},
    {'id': 'laliga',      'name': 'LaLiga',            'shortName': 'LALIGA',     'priority': 80,
     'aliases': ['SPAGNA: LaLiga']},
    {'id': 'bundesliga',  'name': 'Bundesliga',        'shortName': 'BUNDESLIGA', 'priority': 90,
     'aliases': ['GERMANIA: Bundesliga']},
    {'id': 'ligue1',      'name': 'Ligue 1',           'shortName': 'LIGUE 1',    'priority': 100,
     'aliases': ['FRANCIA: Ligue 1']},
    # Nazionali: compaiono solo quando in corso.
    {'id': 'nations',     'name': 'Nations League',    'shortName': 'NATIONS',    'priority': 110,
     'aliases': ['EUROPA: UEFA Nations League'], 'contains': 'nations league'},
    {'id': 'mondiali',    'name': 'Mondiali',          'shortName': 'MONDIALI',   'priority': 120,
     'contains': 'coppa del mondo'},
    {'id': 'europei',     'name': 'Europei',           'shortName': 'EUROPEI',    'priority': 130,
     'contains': 'campionato europeo'},
]

# Escludi sempre queste varianti (femminili, giovanili, futsal, ecc.): match sul nome
# competizione in minuscolo.
EXCLUDE = [
    'femminile', 'women', 'femenino', 'frauen',
    ' u1', ' u2', ' under', 'youth', 'primavera', 'juvenil', 'giovan',
    'futsal', 'beach', 'esports', 'amichevoli club',
]

# --- Abbreviazioni squadra (override sulla forma gia' breve di diretta.it) ----
# chiave = nome cosi' come arriva dal feed; valore = forma breve per il LED.
TEAM_ABBREVIATIONS = {
    # Italia
    'Internazionale': 'Inter', 'Inter Milan': 'Inter', 'AC Milan': 'Milan',
    'Hellas Verona': 'Verona', 'US Lecce': 'Lecce',
    # Inghilterra
    'Manchester City': 'Man City', 'Manchester Utd': 'Man Utd', 'Manchester United': 'Man Utd',
    'Tottenham': 'Tottenham', 'Tottenham Hotspur': 'Tottenham',
    'Wolverhampton': 'Wolves', 'Wolverhampton Wanderers': 'Wolves',
    'Newcastle': 'Newcastle', 'Newcastle United': 'Newcastle',
    'Nottingham': 'Forest', 'Nottingham Forest': 'Forest',
    'Brighton': 'Brighton', 'West Ham': 'West Ham', 'West Ham United': 'West Ham',
    # Spagna
    'Real Madrid': 'Real Madrid', 'Atletico Madrid': 'Atletico', 'Atl. Madrid': 'Atletico',
    'Athletic Bilbao': 'Athletic', 'Real Sociedad': 'Sociedad', 'Real Betis': 'Betis',
    # Germania
    'Bayern Monaco': 'Bayern', 'Bayern Munich': 'Bayern', 'Bayern': 'Bayern',
    'Bayer Leverkusen': 'Leverkusen', 'Borussia Dortmund': 'Dortmund',
    'Borussia Mönchengladbach': 'Gladbach', "M'gladbach": 'Gladbach',
    'Eintracht Frankfurt': 'Eintracht', 'RB Lipsia': 'Lipsia', 'RB Leipzig': 'Lipsia',
    # Francia
    'Paris Saint-Germain': 'PSG', 'Paris SG': 'PSG',
    'Olympique Marsiglia': 'Marsiglia', 'Marseille': 'Marsiglia',
    'Olympique Lione': 'Lione', 'Lyon': 'Lione',
}
