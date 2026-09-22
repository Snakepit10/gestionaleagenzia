# -*- coding: utf-8 -*-
"""View pubbliche del ledwall calcio: la pagina, l'endpoint dati, le pubblicita' e i loghi."""
import re

import requests
from django.http import JsonResponse, HttpResponse, HttpResponseNotFound

from .models import PubblicitaLedwall, ImpostazioniLedwall
from .ledwall import config
from .ledwall.service import get_payload

_SAFE_CODE = re.compile(r'^[A-Za-z0-9._-]{1,80}$')
_FLAG_CODE = re.compile(r'^[a-z]{2}(-[a-z]{2,3})?$')   # es. 'it', 'es', 'gb-eng', 'eu'
_logo_cache = {}   # code -> (bytes, content_type)
_flag_cache = {}   # code -> (bytes, content_type)

# transizione (backend) -> classe CSS della pagina
_FX = {'destra': 'fx-right', 'zoom': 'fx-zoom', 'alto': 'fx-up', 'dissolvenza': 'fx-fade'}


def ledwall_calcio(request):
    """Pagina a schermo intero per il player LED (nessun login, nessuna interazione)."""
    return render_page(request)


def render_page(request):
    from django.shortcuts import render
    return render(request, 'ledwall/calcio.html')


def ledwall_api_calcio(request):
    """Endpoint dati partite. Con ?demo=1 restituisce dati fittizi."""
    demo = request.GET.get('demo') in ('1', 'true', 'yes')
    payload = get_payload(demo=demo)
    resp = JsonResponse(payload, json_dumps_params={'ensure_ascii': False})
    resp['Cache-Control'] = 'public, max-age=30'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


def ledwall_api_ads(request):
    """Pubblicita' attive + impostazioni globali, tutto configurato da Django admin."""
    cfg = ImpostazioniLedwall.get_solo()
    ads = PubblicitaLedwall.objects.using('default').filter(attivo=True).order_by('ordine', 'id')
    data = {
        'config': {
            'hold': cfg.secondi_scheda,
            'adEvery': cfg.ogni_n_schede,
            'adSlide': cfg.secondi_pubblicita,
            'barDur': cfg.secondi_barra_risultati,
            'sumMax': cfg.max_partite_riepilogo,
            'sumLogos': bool(cfg.loghi_riepilogo),
        },
        'ads': [{
            'id': a.pk,
            'url': 'api/ad/%d' % a.pk,
            'fx': _FX.get(a.transizione, 'fx-right'),
            'seconds': a.secondi or cfg.secondi_pubblicita,
        } for a in ads],
    }
    resp = JsonResponse(data)
    resp['Cache-Control'] = 'public, max-age=60'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


def ledwall_api_ad(request, pk):
    """Serve i byte di una singola immagine pubblicitaria (dal DB)."""
    ad = PubblicitaLedwall.objects.using('default').filter(pk=pk, attivo=True).first()
    if not ad or not ad.dati:
        return HttpResponseNotFound()
    resp = HttpResponse(bytes(ad.dati), content_type=ad.content_type or 'image/png')
    resp['Cache-Control'] = 'public, max-age=60'
    return resp


def ledwall_api_logo(request, src, code):
    """Proxy con cache dei loghi squadra (il ledwall chiama solo noi).
    src='af' -> API-Football (HD 150px); src='d' -> diretta.it (30px)."""
    if src == 'af':
        if not re.match(r'^\d{1,7}\.png$', code or ''):
            return HttpResponseNotFound()
        base = config.APIFOOTBALL_LOGO_BASE
    else:  # 'd'
        if not _SAFE_CODE.match(code or ''):
            return HttpResponseNotFound()
        base = config.LOGO_BASE
    key = src + '/' + code
    cached = _logo_cache.get(key)
    if cached is None:
        try:
            r = requests.get(base + code,
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.diretta.it/'},
                             timeout=10)
            if r.status_code != 200 or not r.content:
                return HttpResponseNotFound()
            cached = (r.content, r.headers.get('content-type', 'image/png'))
            if len(_logo_cache) < 4000:      # cap semplice della cache in memoria
                _logo_cache[key] = cached
        except Exception:
            return HttpResponseNotFound()
    resp = HttpResponse(cached[0], content_type=cached[1])
    resp['Cache-Control'] = 'public, max-age=86400'   # loghi statici: cache lunga
    return resp


def ledwall_api_flag(request, code):
    """Proxy con cache delle bandiere (il ledwall chiama solo noi). code = codice ISO/flagcdn
    (es. 'it', 'es', 'gb-eng', 'eu'); l'immagine viene da flagcdn.com (nessuna chiave)."""
    code = (code or '').lower()
    if not _FLAG_CODE.match(code):
        return HttpResponseNotFound()
    cached = _flag_cache.get(code)
    if cached is None:
        try:
            r = requests.get('%sw80/%s.png' % (config.FLAG_BASE, code),
                             headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if r.status_code != 200 or not r.content:
                return HttpResponseNotFound()
            cached = (r.content, r.headers.get('content-type', 'image/png'))
            if len(_flag_cache) < 1000:
                _flag_cache[code] = cached
        except Exception:
            return HttpResponseNotFound()
    resp = HttpResponse(cached[0], content_type=cached[1])
    resp['Cache-Control'] = 'public, max-age=604800'   # bandiere statiche: cache 7 giorni
    return resp
