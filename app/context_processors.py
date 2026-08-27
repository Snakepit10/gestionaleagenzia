"""Context processor per il branding dinamico per agenzia.

Espone `brand` a tutti i template: nome, colore accento e icona in base
all'agenzia dell'utente loggato (fallback neutro se non associato).
"""

# Configurazione per-agenzia (chiave = nome agenzia in minuscolo).
AGENZIA_BRAND = {
    'goldbet': {'nome': 'Goldbet', 'colore': '#e0aa1e', 'colore2': '#b8860b', 'icona': 'fa-crown'},
    'better':  {'nome': 'Better',  'colore': '#e0301e', 'colore2': '#a51d10', 'icona': 'fa-bolt'},
    'planet':  {'nome': 'Planet',  'colore': '#2e7d32', 'colore2': '#1b5e20', 'icona': 'fa-globe'},
}

BRAND_DEFAULT = {'nome': 'Gestionale', 'colore': '#6b7aff', 'colore2': '#4b56c0', 'icona': 'fa-chart-line'}


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
                # Agenzia non mappata: usa il suo nome col colore di default.
                brand['nome'] = agenzia.nome
    return {'brand': brand}
