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
competizione, **bandiera**, data, punteggio e stato LIVE/OGGI/FINALE) e, ogni N schede, un
**intermezzo pubblicitario**: i risultati scendono in una barra scorrevole in basso e sopra
passano a rotazione le immagini pubblicitarie caricate dall'admin (con transizioni diverse).

Dopo aver mostrato le singole partite di una competizione (se sono almeno 2) compare una
**scheda riepilogo** con tutte le sue partite, divise in tre sezioni in ordine cronologico —
**Terminate**, **In corso** (rosso), **Prossime** (azzurro) — pensata per la lettura a distanza.

Accanto al nome della competizione (banner, riepilogo e barra scorrevole) c'è la **bandiera** del
paese. Il paese viene letto **direttamente dal feed di diretta.it** (chiave `ZY`) e mappato a una
bandiera (`config.COUNTRY_ISO`); si può forzare un codice specifico dall'admin (campo `bandiera`
della competizione, es. `it`, `es`, `gb-eng`, `eu`). Vuoto = nessuna bandiera. Le immagini
bandiera sono servite dal **nostro proxy** con cache (`/ledwall/api/flag/<codice>`, fonte flagcdn.com,
nessuna chiave), così il ledwall chiama solo il nostro server.

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
  filesystem), così sopravvivono ai redeploy senza configurare lo storage media.
  **Dimensione consigliata: 2–3× la risoluzione dell'area pubblicitaria del LED**, stesso rapporto
  d'aspetto (es. per un LED 320×200 → immagine ~640×280 o ~960×420). Il browser la rimpicciolisce
  per adattarla: caricarla a risoluzione maggiore **migliora** la nitidezza (fa da antialiasing su
  scritte e bordi), non peggiora; l'unico costo è un file un po' più pesante. Da evitare invece
  immagini **sotto** la risoluzione nativa, che verrebbero ingrandite e apparirebbero sgranate.
- **Ledwall - Impostazioni** (riga unica): **secondi per scheda** (durata di ogni scheda
  partita), **ogni N schede** (dopo quante schede parte la pubblicità), **secondi pubblicità**
  di default e **secondi barra risultati** (velocità dello scorrimento risultati, **costante** in
  px/sec indipendentemente dal numero di partite: più basso = più veloce).

La pagina legge tutto da `/ledwall/api/ads.json` (config + elenco con `fx`/`seconds` per
immagine) e serve le immagini da `/ledwall/api/ad/<id>`. Le modifiche si vedono sul ledwall
entro ~2 minuti (o al reload).

## Filtri: quali campionati e quali partite (da Django admin)
Dal menu **"Ledwall"** (super-user):
- **Ledwall - Competizioni** (`app.CompetizioneLedwall`): l'elenco dei campionati. Per ognuno
  **attivo** (on/off), **ordine** (priorità, le italiane per prime), **short_name** (etichetta
  gialla) e le regole di match col nome di diretta.it (**aliases** esatti, uno per riga, oppure
  **contiene** una sottostringa). Le voci iniziali (Serie A/B, Coppa Italia, Champions, Europa,
  Conference, Premier, LaLiga, Bundesliga, Ligue 1, Nations, Mondiali, Europei) sono già presenti;
  puoi aggiungerne altre.
- **Ledwall - Impostazioni → Filtri partite**: interruttori per **mostra_live** (risultati in
  corso), **mostra_oggi_in_programma** (partite di oggi non iniziate), **mostra_oggi_finite**
  (risultati finali di oggi), **mostra_domani** (anche le partite in programma domani, con la data).
  Se non c'è nulla da mostrare, il ledwall ripiega su ultimi risultati (ieri) + prossime (domani).

Il provider legge questi filtri dal DB (`_load_competizioni` / `_load_impostazioni`); le modifiche
si vedono sul ledwall entro ~2 minuti (la cache lato server viene invalidata al
salvataggio delle impostazioni; il player ricontrolla ogni 2 minuti).

## Loghi squadra
Serviti dal **nostro proxy** con cache (`/ledwall/api/logo/<src>/<code>`), così il ledwall chiama
solo il nostro server. Due sorgenti:
- **HD (API-Football)**: loghi 150×150 px dal CDN pubblico `media.api-sports.io` (nessuna chiave),
  usati per le squadre presenti nella mappa `config.APIFOOTBALL_TEAM_IDS` (Serie A + top club
  europei, verificata visivamente). `src='af'`, `code='<id>.png'`.
- **diretta.it** (fallback): loghi 30×30 px per tutte le altre squadre. `src='d'`.

L'interruttore **Ledwall - Impostazioni → Loghi → loghi_hd** attiva/disattiva gli HD. Se un logo
manca, la scheda mostra le iniziali. Per aggiungere HD ad altre squadre basta inserire la coppia
`nome-breve-diretta: id-api-football` in `config.APIFOOTBALL_TEAM_IDS`.

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

## Diverse risoluzioni di LED: la pagina si auto-adatta (nessuna configurazione)
**Una sola pagina** (`/ledwall/calcio`) va bene per tutti i LED, di qualsiasi risoluzione: ogni
player carica lo stesso URL e la pagina si dimensiona da sola sulla risoluzione reale del
dispositivo. Non servono pagine separate né parametri.

Come funziona (in `templates/ledwall/calcio.html`):
- `--w`/`--ph` = larghezza/altezza **reali** del dispositivo (`100vw`/`100vh`): riempiono lo schermo.
- `--h` = base di **scala** dei testi/elementi = `100vmin` (lato corto). In orizzontale `vmin` è
  l'altezza, quindi 320×200, 320×160, ecc. si ricompongono da soli; in verticale è la larghezza,
  così i testi non escono di lato.
- **Formato verticale**: lo `<script>` mette la classe `.portrait` sul `<html>` quando il box è più
  alto che largo (device reale o anteprima) e la scheda passa a layout **impilato**
  (squadra casa / punteggio / squadra ospite), sfruttando l'altezza. Nessuna modifica al codice.

**Anteprima da PC/telefono** (o per un player che non riporta la risoluzione nativa): aggiungere
`?w=<larghezza>&h=<altezza>` all'URL, es. `/ledwall/calcio?w=320&h=200` o `?w=384&h=960`. Forza un
riquadro di quelle dimensioni, centrato nella finestra. Sul ledwall reale, senza parametri, riempie
lo schermo. Si combina con `?demo=1` e con gli override tempi (`?hold=`, `?adEvery=`, `?adSlide=`,
`?barDur=`).

**Colori e contrasti** restano validi su qualsiasi formato.
