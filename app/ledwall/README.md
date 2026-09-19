# Ledwall Calcio

Pagina a schermo intero per player LED (Colorlight A35, Chromium Android 9) su ledwall
320×200, e endpoint dati sul nostro server. Il ledwall legge **solo** il nostro endpoint,
mai diretta.it.

## URL
- Pagina:   `https://<dominio>/ledwall/calcio`
- Endpoint: `https://<dominio>/ledwall/api/calcio.json`

Parametri della pagina (query string):
- `?label=CALCIO OGGI` — testo del riquadro fisso a sinistra (default "CALCIO OGGI").
- `?speed=3` — velocità di scorrimento in **caratteri al secondo** (default 3).
- `?demo=1` — dati fittizi (≥4 competizioni) per provare grafica/scorrimento senza rete.

Esempio player: `https://<dominio>/ledwall/calcio?label=CALCIO%20OGGI&speed=3`

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
               "home","away","homeScore","awayScore","date"}]}]}
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
La pagina è pensata per una **fascia orizzontale** che riempie i 200 px di altezza. Per un
formato diverso agire solo su `templates/ledwall/calcio.html`:
- **Dimensioni**: `html,body{width:…;height:…}` e `<meta viewport width=… height=…>` col nuovo
  formato (es. 384×960).
- **Formato verticale (384×960)**: una singola riga che scorre non sfrutta l'altezza. Meglio
  passare a uno **scorrimento verticale** (in alto→basso) con le partite impilate: cambiare i
  `@keyframes ledscroll` in `translateY(-50%)`, il `#track` a `flex-direction:column` e le
  `.copy` a colonna; alzare le dimensioni del testo. La logica dati/JS resta identica.
- **Font/spaziature**: i `font-size` in `.comp/.team/.score/.time` scalano l'aspetto; su superfici
  più grandi aumentarli. Colori e regole di contrasto restano validi.
