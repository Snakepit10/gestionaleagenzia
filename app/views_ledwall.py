# -*- coding: utf-8 -*-
"""View pubbliche del ledwall calcio: la pagina e l'endpoint JSON."""
from django.http import JsonResponse
from django.shortcuts import render

from .ledwall.service import get_payload


def ledwall_calcio(request):
    """Pagina a schermo intero per il player LED (nessun login, nessuna interazione)."""
    return render(request, 'ledwall/calcio.html')


def ledwall_api_calcio(request):
    """Endpoint che il ledwall interroga. Con ?demo=1 restituisce dati fittizi."""
    demo = request.GET.get('demo') in ('1', 'true', 'yes')
    payload = get_payload(demo=demo)
    resp = JsonResponse(payload, json_dumps_params={'ensure_ascii': False})
    # Cache breve lato eventuale proxy/CDN; il ledwall comunque fa polling.
    resp['Cache-Control'] = 'public, max-age=30'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp
