"""
Parsing best-effort di un estratto conto bancario in CSV.

Il file viene elaborato in memoria (nessuno storage). Il formato degli estratti conto
varia molto per banca, quindi si fa detection dell'header con fallback per indice.
Riusa il parser di importi italiani di cast_agent (`_parse_importo_it`).
"""
import csv
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal

from .cast_agent import _parse_importo_it


def _norm(s):
    return (s or '').strip().lower()


def _trova_colonna(header, chiavi):
    """Ritorna l'indice della prima colonna il cui nome contiene una delle chiavi."""
    for i, h in enumerate(header):
        hn = _norm(h)
        for k in chiavi:
            if k in hn:
                return i
    return -1


def _parse_data(valore):
    """Prova più formati comuni; ritorna un date o None."""
    v = (valore or '').strip()
    if not v:
        return None
    # ISO con eventuale orario
    v10 = v[:10]
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d.%m.%Y'):
        try:
            return datetime.strptime(v10, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv(contenuto):
    """
    Analizza il testo CSV di un estratto conto.

    Ritorna una lista di dict: {'data': date|None, 'descrizione': str, 'importo': Decimal}.
    Convenzione importi: negativo = uscita/spesa, positivo = entrata. Se l'estratto ha
    colonne separate Dare/Avere, l'uscita (Dare) è resa negativa.
    """
    testo = contenuto.replace('\r\n', '\n').replace('\r', '\n')
    righe_grezze = [r for r in testo.split('\n') if r.strip()]
    if not righe_grezze:
        return []

    # Delimitatore: ';' o ',' (sceglie quello più frequente nella prima riga)
    prima = righe_grezze[0]
    delim = ';' if prima.count(';') >= prima.count(',') else ','

    reader = list(csv.reader(io.StringIO(testo), delimiter=delim))
    reader = [r for r in reader if any((c or '').strip() for c in r)]
    if not reader:
        return []

    header = reader[0]
    header_norm = [_norm(h) for h in header]
    ha_header = any(k in ' '.join(header_norm)
                    for k in ('data', 'date', 'importo', 'amount', 'descr', 'causal', 'dare', 'avere'))

    i_data = _trova_colonna(header, ['data', 'date'])
    i_desc = _trova_colonna(header, ['descr', 'causal', 'operazion', 'dettagl', 'narrat'])
    i_imp = _trova_colonna(header, ['importo', 'amount', 'movimento'])
    i_dare = _trova_colonna(header, ['dare', 'uscite', 'addebit', 'debit'])
    i_avere = _trova_colonna(header, ['avere', 'entrate', 'accredit', 'credit'])

    # Fallback per posizione se non trovate
    if i_data < 0:
        i_data = 0
    if i_desc < 0:
        i_desc = 1 if len(header) > 1 else 0
    if i_imp < 0 and i_dare < 0 and i_avere < 0:
        i_imp = len(header) - 1

    dati = reader[1:] if ha_header else reader
    risultato = []
    for r in dati:
        def cella(idx):
            return r[idx] if 0 <= idx < len(r) else ''

        d = _parse_data(cella(i_data))
        descr = cella(i_desc).strip()

        importo = None
        if i_imp >= 0:
            importo = _parse_importo_it(cella(i_imp))
        if importo is None and (i_dare >= 0 or i_avere >= 0):
            dare = _parse_importo_it(cella(i_dare)) if i_dare >= 0 else None
            avere = _parse_importo_it(cella(i_avere)) if i_avere >= 0 else None
            if dare:
                importo = -abs(dare)
            elif avere:
                importo = abs(avere)

        if importo is None:
            # riga non interpretabile (intestazioni intermedie, saldi, righe vuote)
            continue

        risultato.append({
            'data': d,
            'descrizione': descr[:300],
            'importo': importo.quantize(Decimal('0.01')),
        })

    return risultato


def hash_riga(data_val, descrizione, importo):
    """Chiave di dedup stabile per una riga (data|descrizione|importo)."""
    d = data_val.isoformat() if isinstance(data_val, date) else (data_val or '')
    base = f"{d}|{(descrizione or '').strip().lower()}|{importo}"
    return hashlib.sha1(base.encode('utf-8')).hexdigest()
