# Ledwall Calcio

Pagina a schermo intero per player LED (Colorlight A35, Chromium Android 9) su ledwall
320×200, e endpoint dati sul nostro server. Il ledwall legge **solo** il nostro endpoint,
mai diretta.it.

## URL
- Pagina:        `https://<dominio>/ledwall/calcio`
- Dati partite:  `https://<dominio>/ledwall/api/calcio.json`
- Pubblicità:    `https://<dominio>/ledwall/api/ads.json` e `/ledwall/api/ad/<id>`
- Loghi (proxy): `https://<dominio>/ledwall/api/logo/<code>`

La pagina mostra le **schede partita** stile tabellone (una alla volta, con loghi squadra,
competizione, data, punteggio e stato LIVE/OGGI/FINALE) e, ogni N schede, un **intermezzo
pubblicitario**: i risultati scendono in una barra scorrevole in basso e sopra passano a
rotazione le immagini pubblicitarie caricate dall'admin (con transizioni diverse).

La rotazione, i tempi e le transizioni si configurano **dal backend Django** (vedi sotto),
non servono parametri nell'URL. Solo per test si possono forzare con `?hold=`, `?adEvery=`,
`?adSlide=`, e `?demo=1` usa dati partite fittizi (le pubblicità restano quelle reali dal DB).

Esempio player: `https://<dominio>/ledwall/calcio`

## Pubblicità e tempi (tutto da Django admin)
Voce di menu **"Ledwall"** (solo super-user) → apre la gestione. Due sezioni:
- **Ledwall - Pubblicità** (`app.PubblicitaLedwall`): ogni immagine ha
  **immagine** (upload), **attivo**, **ordine**, **transizione** d'entrata
  (Scorrimento da destra / Zoom / Dal basso / Dissolvenza) e **secondi** di permanenza
  (0 = usa il default globale). I byte dell'immagine sono salvati **nel database** (non su
  filesystem), così sopravvivono ai redeploy senza configurare lo storage media. Consigliata
  un'immagine orizzontale (es. ~320×140).
- **Ledwall - Impostazioni** (riga unica): **secondi per scheda** (durata di ogni scheda
  partita), **ogni N schede** (dopo quante schede parte la pubblicità) e **secondi pubblicità**
  di default.

La pagina legge tutto da `/ledwall/api/ads.json` (config + elenco con `fx`/`seconds` per
immagine) e serve le immagini da `/ledwall/api/ad/<id>`. Le modifiche si vedono sul ledwall
entro ~5 minuti (o al reload).

## Loghi squadra
Presi da diretta.it (codici `OA`/`OB` del feed) e serviti dal **nostro proxy** con cache
`/ledwall/api/logo/<code>` (base in `config.LOGO_BASE`), così il ledwall continua a chiamare
solo il nostro server. Se un logo manca, la scheda mostra le iniziali della squadra.

I loghi di diretta.it sono a **30×30 px**: per non renderli sgranati la scheda NON li ingrandisce
oltre il nativo (`.badge img{max-width:…;width:auto}`), li mostra nitidi in un badge bianco. Per
loghi grandi e nitidi servirebbe una fonte a maggiore risoluzione (es. API-Football), collegabile
sostituendo il provider senza cambiare la pagina.

## Architettura
```
Ledwall (browser)  ──GET──▶  /ledwall/api/calcio.json  ──▶  cache (60s live / 10min)
                                                          └▶  provider (diretta.it)
```
- `views_ledwall.py` — la pagina e l'endpoint.
- `ledwall/service.py` — cache in-process + fallback "ultimi dati validi".
- `ledwall/providers.py` — `DirettaProvider` (scraping) e `DemoProvider`. **Sostituibile.**
- `ledwall/config.py` — **unico file** da toccare: competizioni, priorità, abbreviazioni,
  parametri feed e cache.
- `templates/ledwall/calcio.html` — pagina singola (CSS+JS inline, font Google).

JSON servito:
```json
{"updated":"<iso>","source":"diretta","stale":false,
 "competitions":[{"id","name","shortName","priority",
   "matches":[{"status":"live|scheduled|finished","minute","time",
               "home","away","homeScore","awayScore","homeLogo","awayLogo","date"}]}]}
```

## Come vengono raccolti i dati (diretta.it)
`DirettaProvider` fa una GET del feed "del giorno" del calcio:
`https://www.diretta.it/x/feed/f_1_0_0_it_1` con header `x-fsign` (firma statica del sito) +
`Referer`. È un testo delimitato (formato FlashScore): record separati da `~`, coppie
`chiave÷valore` separate da `¬`. Una riga `ZA` è l'intestazione competizione ("PAESE: Torneo"),
le righe `AA` sono le partite. Chiavi usate: `AB` stato (1 in programma, 2 live, 3 finita),
`AE/AF` squadre, `AG/AH` gol, `AD` inizio (unix), `AC`+`AO` per il minuto live.

**Frequenza**: il ledwall interroga solo il nostro endpoint; il server chiama diretta.it al
massimo **una volta per TTL cache** — 60s quando c'è almeno una partita live, 10 minuti
altrimenti. Se non ci sono partite oggi nelle competizioni configurate, il provider recupera
anche ieri (ultimi risultati) e domani (prossime), con la data.

**Fragilità / termini d'uso**: lo scraping di diretta.it non è una API ufficiale ed è soggetto
ai suoi termini. Se il feed cambia formato, viene bloccato o `x-fsign` scade, `DirettaProvider`
solleva un'eccezione e il servizio **continua a servire gli ultimi dati validi** (la pagina
mostra in piccolo l'ora dell'ultimo aggiornamento; mai schermo vuoto). In quel caso:
1. aggiornare `FEED['xfsign']` in `config.py`, oppure
2. passare a una fonte con API ufficiale (vedi sotto) — il JSON resta identico, la pagina non cambia.

## Sostituire la fonte (API ufficiale)
Il modulo dati è sostituibile: creare in `providers.py` una classe con lo stesso metodo
`fetch()` che ritorna lo stesso JSON, ad es. `ApiFootballProvider` (api-sports.io, copre tutte
le competizioni elencate) o `FootballDataProvider` (football-data.org). Poi impostare
`PROVIDER = 'api_football'` in `config.py` e aggiungere la chiave via variabile d'ambiente
(mai nel codice/nel client). Cache, endpoint e pagina restano invariati.

## Configurare le competizioni
In `config.py`, lista `COMPETITIONS`: ogni voce ha `priority` (numero più basso = più in alto,
le italiane per prime), `shortName` (etichetta gialla sul LED) e gli `aliases` (nome esatto di
diretta.it "PAESE: Torneo") o `contains` (sottostringa). Le varianti femminili/giovanili sono
escluse da `EXCLUDE`. Le abbreviazioni squadra sono in `TEAM_ABBREVIATIONS`.

## Pubblicazione e cache
- Le rotte sono già in `app/urls.py` (pubbliche, senza login). Deploy come il resto del sito
  (Railway esegue già le migrazioni; qui non servono migrazioni).
- La cache è **in-process** (in `service.py`): nessuna configurazione esterna necessaria. Con
  più worker gunicorn ognuno tiene la propria cache (al più 1 chiamata a diretta.it per worker
  per TTL). Per una cache condivisa tra worker si può in futuro spostare su `django.core.cache`.
- L'endpoint invia `Cache-Control: public, max-age=30` (utile se davanti c'è una CDN/proxy).
- Requisiti: `requests` e `tzdata` (già in `requirements.txt`).

## Se cambia il formato del ledwall (es. 384×960 verticale)
Le dimensioni dei testi sono già espresse in `calc(100vh * …)`, quindi **scalano da sole con
l'altezza**. Per un formato diverso agire solo su `templates/ledwall/calcio.html`:
- **Dimensioni**: `html,body{width:…;height:…}` e `<meta viewport width=… height=…>` col nuovo
  formato (es. 384×960). Le schede (grid a 3 colonne, centrata) e l'intermezzo pubblicitario si
  adattano; su schermi molto più alti valutare di ridurre i moltiplicatori `100vh*…` per non
  ingigantire troppo il testo.
- **Formato verticale (384×960)**: c'è molto spazio verticale. Opzioni: aumentare l'area
  pubblicitaria (alzare `.ad{bottom:…}` e la barra `.bar{height:…}`), o impilare i loghi/nomi;
  la logica dati/JS resta identica.
- **Colori e contrasti** restano validi su qualsiasi formato.
