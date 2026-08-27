"""Context processor per il branding dinamico per agenzia.

Espone `brand` a tutti i template: nome, colore primario (navbar), colore
accento e un wordmark HTML in stile marchio ufficiale, in base all'agenzia
dell'utente loggato (fallback neutro se non associato).
"""
from django.utils.safestring import mark_safe


def _wm(html):
    return mark_safe(html)


# Configurazione per-agenzia (chiave = nome agenzia in minuscolo).
# primario = sfondo navbar; accento = colore highlight; logo_html = wordmark.
AGENZIA_BRAND = {
    'goldbet': {
        'nome': 'GoldBet',
        'primario': '#0e1a3c',   # blu navy
        'accento': '#f5b71d',    # oro
        'logo_html': _wm('<span class="wm" style="letter-spacing:.01em;">'
                         '<span style="color:#f5b71d;">Gold</span>'
                         '<span style="color:#ffffff;">Bet</span></span>'),
    },
    'better': {
        'nome': 'Better',
        'primario': '#14602f',   # verde scuro
        'accento': '#8dc63f',    # verde lime
        'logo_html': _wm('<span class="wm" style="font-style:italic;letter-spacing:.04em;color:#ffffff;'
                         'text-shadow:0 1px 0 rgba(0,0,0,.25);">BETTER</span>'),
    },
    'planet': {
        'nome': 'PlanetWin365',
        'primario': '#1b1b1b',   # nero
        'accento': '#f2c200',    # giallo/oro
        'logo_html': _wm('<span class="wm" style="letter-spacing:.02em;">'
                         '<span style="color:#f2c200;">PLANET</span>'
                         '<span style="color:#ffffff;">WIN</span>'
                         '<span style="color:#f2c200;font-size:.62em;vertical-align:super;">365</span></span>'),
    },
}

BRAND_DEFAULT = {
    'nome': 'Gestionale',
    'primario': '#1f2327',
    'accento': '#6b7aff',
    'logo_html': _wm('<span class="wm"><i class="fas fa-chart-line me-2"></i>Gestionale</span>'),
}


def branding(request):
    brand = dict(BRAND_DEFAULT)
    brand['agenzia'] = None
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        try:
            agenzia = user.profiloutente.agenzia
        except Exception:
            agenzia = None
        if agenzia is not None:
            brand['agenzia'] = agenzia.nome
            cfg = AGENZIA_BRAND.get((agenzia.nome or '').strip().lower())
            if cfg:
                brand.update(cfg)
            else:
                # Agenzia non mappata: nome col wordmark di default.
                brand['nome'] = agenzia.nome
                brand['logo_html'] = _wm('<span class="wm">%s</span>' % agenzia.nome)
    return {'brand': brand}
