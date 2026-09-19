# -*- coding: utf-8 -*-
"""View pubbliche del ledwall calcio: la pagina, l'endpoint dati, le pubblicita' e i loghi."""
import re

import requests
from django.http import JsonResponse, HttpResponse, HttpResponseNotFound

from .models import PubblicitaLedwall, ImpostazioniLedwall
from .ledwall import config
from .ledwall.service import get_payload

_SAFE_CODE = re.compile(r'^[A-Za-z0-9._-]{1,80}$')
_logo_cache = {}   # code -> (bytes, content_type)

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


def ledwall_api_logo(request, code):
    """Proxy con cache dei loghi squadra da diretta.it (il ledwall chiama solo noi)."""
    if not _SAFE_CODE.match(code or ''):
        return HttpResponseNotFound()
    cached = _logo_cache.get(code)
    if cached is None:
        try:
            r = requests.get(config.LOGO_BASE + code,
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.diretta.it/'},
                             timeout=10)
            if r.status_code != 200 or not r.content:
                return HttpResponseNotFound()
            cached = (r.content, r.headers.get('content-type', 'image/png'))
            if len(_logo_cache) < 2000:      # cap semplice della cache in memoria
                _logo_cache[code] = cached
        except Exception:
            return HttpResponseNotFound()
    resp = HttpResponse(cached[0], content_type=cached[1])
    resp['Cache-Control'] = 'public, max-age=86400'   # loghi statici: cache lunga
    return resp
