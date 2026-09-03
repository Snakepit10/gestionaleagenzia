"""
Conto Economico: report mensili ricavi/spese, per singola agenzia + vista consolidata.

Tassonomia (ProdottoRicavo / CategoriaSpesa) globale sul DB 'default'.
Dati finanziari (ContoEconomico / VoceRicavo / VoceCosto / MovimentoBancario) per-agenzia.
"""
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone

from .models import (
    ContoEconomico, VoceRicavo, VoceCosto, MovimentoBancario,
    ProdottoRicavo, CategoriaSpesa, CategoriaProdotto, CategoriaCosto, Cliente, Movimento, Agenzia,
)
from .database_utils import DatabaseManager, AGENZIA_DATABASE_MAP
from .forms import (
    ProdottoRicavoForm, CategoriaSpesaForm, CategoriaProdottoForm, CategoriaCostoForm, VoceCostoForm,
    VoceRicavoManualeForm, UploadEstrattoForm, ConsolidatoForm, MESI_CHOICES,
)
from . import estratto_conto
from .views import is_manager_or_admin


MESI_DICT = dict(MESI_CHOICES)


def is_superadmin(user):
    return user.is_superuser


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_importo(valore):
    """Parsa un importo digitato dall'operatore, gestendo sia il decimale con virgola
    sia con punto (l'ultimo separatore è considerato quello decimale)."""
    s = (valore or '').strip().replace(' ', '').replace('€', '')
    if not s:
        return None
    lc, ld = s.rfind(','), s.rfind('.')
    dec = max(lc, ld)
    if dec >= 0:
        s = s[:dec].replace('.', '').replace(',', '') + '.' + s[dec + 1:].replace('.', '').replace(',', '')
    else:
        s = s.replace('.', '').replace(',', '')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _prodotti_attivi():
    return list(ProdottoRicavo.objects.using('default').filter(attivo=True).order_by('ordine', 'nome'))


def _categorie_attive():
    return list(CategoriaSpesa.objects.using('default').filter(attivo=True).order_by('ordine', 'nome'))


def _mappa_prodotti():
    return {p.codice: p.nome for p in ProdottoRicavo.objects.using('default')}


def _mappa_categorie():
    return {c.codice: c.nome for c in CategoriaSpesa.objects.using('default')}


def _categorie_prodotto():
    return list(CategoriaProdotto.objects.using('default').filter(attivo=True).order_by('ordine', 'nome'))


def _mappa_cat_prodotto():
    return {c.codice: c.nome for c in CategoriaProdotto.objects.using('default')}


def _prodotti_per_categoria():
    """Prodotti attivi raggruppati per categoria: [{nome, codice, prodotti:[...]}, ...],
    con 'Senza categoria' in fondo."""
    cats = _categorie_prodotto()
    cod_validi = {c.codice for c in cats}
    prodotti = _prodotti_attivi()
    gruppi = []
    for c in cats:
        pl = [p for p in prodotti if p.categoria_codice == c.codice]
        if pl:
            gruppi.append({'nome': c.nome, 'codice': c.codice, 'prodotti': pl})
    senza = [p for p in prodotti if not p.categoria_codice or p.categoria_codice not in cod_validi]
    if senza:
        gruppi.append({'nome': 'Senza categoria', 'codice': '', 'prodotti': senza})
    return gruppi


def _prod_categoria_of():
    """Mappa codice prodotto -> codice categoria prodotto (vuoto se assente)."""
    return {p.codice: (p.categoria_codice or '') for p in ProdottoRicavo.objects.using('default')}


def _raggruppa_prodotti_per_categoria(items):
    """Raggruppa una lista di prodotti (dict con 'codice', 'nome', 'totale') per categoria
    prodotto. Salta prodotti e categorie con totale 0."""
    cats = _categorie_prodotto()
    ordine = {c.codice: i for i, c in enumerate(cats)}
    map_cat = _mappa_cat_prodotto()
    prod_cat = _prod_categoria_of()
    gruppi = {}
    for it in items:
        if not it.get('totale'):
            continue
        cc = prod_cat.get(it['codice'], '') or ''
        if cc not in ordine:
            cc = ''
        g = gruppi.setdefault(cc, {
            'nome': (map_cat.get(cc) if cc else 'Senza categoria') or 'Senza categoria',
            'ord': ordine.get(cc, 9999), 'prodotti': [], 'totale': Decimal('0')})
        g['prodotti'].append(it)
        g['totale'] += it.get('totale', Decimal('0'))
    for g in gruppi.values():
        g['prodotti'].sort(key=lambda x: x.get('nome', '').lower())
    return [g for g in sorted(gruppi.values(), key=lambda g: (g['ord'], g['nome'].lower())) if g['totale']]


def _categorie_costo():
    return list(CategoriaCosto.objects.using('default').filter(attivo=True).order_by('ordine', 'nome'))


def _mappa_cat_costo():
    return {c.codice: c.nome for c in CategoriaCosto.objects.using('default')}


def _spesa_categoria_of():
    """Mappa codice conto-spesa -> codice macro-categoria costo (vuoto se assente)."""
    return {c.codice: (c.categoria_costo_codice or '') for c in CategoriaSpesa.objects.using('default')}


def _raggruppa_costi_per_categoria(items):
    """Raggruppa i conti di costo (dict con 'codice', 'nome', 'totale') per macro-categoria
    costo. Salta conti e macro-categorie con totale 0."""
    cats = _categorie_costo()
    ordine = {c.codice: i for i, c in enumerate(cats)}
    map_cat = _mappa_cat_costo()
    spesa_cat = _spesa_categoria_of()
    gruppi = {}
    for it in items:
        if not it.get('totale'):
            continue
        cc = spesa_cat.get(it['codice'], '') or ''
        if cc not in ordine:
            cc = ''
        g = gruppi.setdefault(cc, {
            'nome': (map_cat.get(cc) if cc else 'Senza macro-categoria') or 'Senza macro-categoria',
            'ord': ordine.get(cc, 9999), 'costi': [], 'totale': Decimal('0')})
        g['costi'].append(it)
        g['totale'] += it.get('totale', Decimal('0'))
    for g in gruppi.values():
        g['costi'].sort(key=lambda x: x.get('nome', '').lower())
    return [g for g in sorted(gruppi.values(), key=lambda g: (g['ord'], g['nome'].lower())) if g['totale']]


def _get_conto(dbname, anno, mese, user=None, crea=False):
    """Ritorna il ContoEconomico del mese sul DB indicato; opzionalmente lo crea."""
    if crea:
        conto, _ = ContoEconomico.objects.using(dbname).get_or_create(
            anno=anno, mese=mese,
            defaults={'creato_da_id': user.id if user else None},
        )
        return conto
    return ContoEconomico.objects.using(dbname).filter(anno=anno, mese=mese).first()


def _report(dbname, anno, mese):
    """Calcola il conto economico del mese leggendo da un DB specifico (nessuna scrittura).

    Ritorna dict con:
      ricavi_prodotto: {codice: importo}, ricavi_manuali: Decimal,
      costi_categoria: {codice|'': importo}, tot_ricavi, tot_costi, utile.
    """
    conto = ContoEconomico.objects.using(dbname).filter(anno=anno, mese=mese).first()
    ricavi_prodotto, costi_categoria = {}, {}
    ricavi_manuali = Decimal('0')
    tot_ricavi = tot_costi = Decimal('0')

    if conto:
        for r in VoceRicavo.objects.using(dbname).filter(conto_economico=conto):
            tot_ricavi += r.importo
            if r.prodotto_codice:
                ricavi_prodotto[r.prodotto_codice] = ricavi_prodotto.get(r.prodotto_codice, Decimal('0')) + r.importo
            else:
                ricavi_manuali += r.importo
        for c in VoceCosto.objects.using(dbname).filter(conto_economico=conto):
            key = c.categoria_codice or ''
            if not key:
                continue  # i costi da classificare non entrano nel conto economico
            tot_costi += c.importo
            costi_categoria[key] = costi_categoria.get(key, Decimal('0')) + c.importo

    return {
        'conto': conto,
        'ricavi_prodotto': ricavi_prodotto,
        'ricavi_manuali': ricavi_manuali,
        'costi_categoria': costi_categoria,
        'tot_ricavi': tot_ricavi,
        'tot_costi': tot_costi,
        'utile': tot_ricavi - tot_costi,
    }


def _agenzie_db():
    """Agenzie attive con il rispettivo database (per la ripartizione dei costi)."""
    res = []
    for ag in Agenzia.objects.using('default').filter(attiva=True).order_by('nome'):
        dbn = AGENZIA_DATABASE_MAP.get(ag.nome.lower())
        if dbn:
            res.append({'db': dbn, 'nome': ag.nome})
    return res


def _fmt_perc(v):
    try:
        d = Decimal(str(v))
    except Exception:
        return ''
    return ('%g' % d).replace('.', ',')


def _rigenera_voci_da_riga(src_db, mb, anno, mese, allocazioni, user):
    """Rigenera le voci (costo o ricavo) generate da una riga bancaria ripartita.

    Elimina prima le voci precedenti (in tutti i DB agenzia) identificate da
    (origine_db, origine_mb_id), poi crea una voce per ogni fetta della ripartizione nel
    database dell'agenzia relativa, per il mese indicato. Una riga con importo negativo
    genera VoceCosto (categoria), una positiva genera VoceRicavo (prodotto).
    """
    for dbn in set(AGENZIA_DATABASE_MAP.values()):
        VoceCosto.objects.using(dbn).filter(origine_db=src_db, origine_mb_id=mb.pk).delete()
        VoceRicavo.objects.using(dbn).filter(origine_db=src_db, origine_mb_id=mb.pk).delete()
    is_costo = mb.importo < 0
    codice = (mb.categoria_codice if is_costo else mb.prodotto_codice)
    if not codice:
        return
    base = abs(mb.importo)
    for a in allocazioni or []:
        dbn = a.get('db')
        try:
            perc = Decimal(str(a.get('perc') or 0))
        except Exception:
            perc = Decimal('0')
        if not dbn or perc <= 0:
            continue
        importo = (base * perc / Decimal('100')).quantize(Decimal('0.01'))
        # user=None: chi ripartisce può non esistere nel DB dell'agenzia di destinazione
        # (FK creato_da), quindi il contenitore mensile viene creato senza autore.
        conto_m = _get_conto(dbn, anno, mese, None, crea=True)
        if is_costo:
            v = VoceCosto(conto_economico=conto_m, categoria_codice=codice,
                          descrizione=mb.descrizione[:200], importo=importo, data=mb.data,
                          fonte='csv', origine_db=src_db, origine_mb_id=mb.pk)
        else:
            v = VoceRicavo(conto_economico=conto_m, prodotto_codice=codice,
                           descrizione=mb.descrizione[:200], importo=importo,
                           fonte='csv', origine_db=src_db, origine_mb_id=mb.pk)
        v.save(using=dbn)


# ---------------------------------------------------------------------------
# Lista mesi (per agenzia)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def conto_economico(request):
    db = DatabaseManager(request.user)
    conti = ContoEconomico.objects.using(db.user_db).all()
    righe = []
    for c in conti:
        tr = c.totale_ricavi()
        # solo costi classificati entrano nei totali/utile
        tc = (VoceCosto.objects.using(db.user_db)
              .filter(conto_economico=c, categoria_codice__isnull=False)
              .exclude(categoria_codice='')
              .aggregate(t=Sum('importo'))['t'] or Decimal('0'))
        pending = MovimentoBancario.objects.using(db.user_db).filter(
            conto_economico=c, stato='da_classificare').count()
        righe.append({'conto': c, 'mese_nome': MESI_DICT.get(c.mese, c.mese),
                      'ricavi': tr, 'costi': tc, 'utile': tr - tc, 'pending': pending})

    oggi = timezone.localdate()
    context = {
        'righe': righe,
        'mesi': MESI_CHOICES,
        'anno_corrente': oggi.year,
        'mese_corrente': oggi.month,
        'anni': list(range(oggi.year, oggi.year - 6, -1)),
        'is_superadmin': request.user.is_superuser,
    }
    return render(request, 'app/conto_economico_lista.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def apri_mese(request):
    """Redirect verso il mese scelto nel form della lista (crea il contenitore)."""
    try:
        anno = int(request.GET.get('anno'))
        mese = int(request.GET.get('mese'))
    except (TypeError, ValueError):
        messages.error(request, 'Mese o anno non validi.')
        return redirect('conto_economico')
    if not (1 <= mese <= 12):
        messages.error(request, 'Mese non valido.')
        return redirect('conto_economico')
    db = DatabaseManager(request.user)
    _get_conto(db.user_db, anno, mese, request.user, crea=True)
    return redirect('conto_economico_mese', anno=anno, mese=mese)


@login_required
@user_passes_test(is_manager_or_admin)
def riepilogo_annuale(request, anno):
    """Conto economico dell'intero anno (somma dei mesi) per l'agenzia."""
    db = DatabaseManager(request.user)
    dbname = db.user_db
    map_prod = _mappa_prodotti()
    map_cat = _mappa_categorie()
    cat_deducibili = {c.codice for c in CategoriaSpesa.objects.using('default').filter(deducibile=True)}

    conti = list(ContoEconomico.objects.using(dbname).filter(anno=anno))
    ricavi_prod, costi_cat = {}, {}
    ricavi_manuali_tot = Decimal('0')
    tot_ricavi = tot_costi = costi_deducibili = Decimal('0')
    per_mese = []
    for c in sorted(conti, key=lambda x: x.mese):
        r_m = c_m = Decimal('0')
        for r in VoceRicavo.objects.using(dbname).filter(conto_economico=c):
            r_m += r.importo
            if r.prodotto_codice:
                ricavi_prod[r.prodotto_codice] = ricavi_prod.get(r.prodotto_codice, Decimal('0')) + r.importo
            else:
                ricavi_manuali_tot += r.importo
        for v in VoceCosto.objects.using(dbname).filter(conto_economico=c):
            if not v.categoria_codice:
                continue
            c_m += v.importo
            costi_cat[v.categoria_codice] = costi_cat.get(v.categoria_codice, Decimal('0')) + v.importo
            if v.categoria_codice in cat_deducibili:
                costi_deducibili += v.importo
        tot_ricavi += r_m
        tot_costi += c_m
        per_mese.append({'mese': c.mese, 'mese_nome': MESI_DICT.get(c.mese, c.mese),
                         'ricavi': r_m, 'costi': c_m, 'utile': r_m - c_m})

    ricavi_catgruppi = _raggruppa_prodotti_per_categoria(
        [{'codice': k, 'nome': map_prod.get(k, k), 'totale': v} for k, v in ricavi_prod.items()])
    costi_catgruppi = _raggruppa_costi_per_categoria(
        [{'codice': k, 'nome': map_cat.get(k, k), 'totale': v} for k, v in costi_cat.items()])
    costi_nondeducibili = tot_costi - costi_deducibili
    utile = tot_ricavi - tot_costi
    imponibile = tot_ricavi - costi_deducibili
    stima_imposte = max(Decimal('0'), (imponibile * Decimal('0.24')).quantize(Decimal('0.01')))

    oggi = timezone.localdate()
    context = {
        'anno': anno,
        'ricavi_catgruppi': ricavi_catgruppi, 'ricavi_manuali_tot': ricavi_manuali_tot,
        'costi_catgruppi': costi_catgruppi,
        'tot_ricavi': tot_ricavi, 'tot_costi': tot_costi,
        'costi_nondeducibili': costi_nondeducibili, 'imponibile': imponibile,
        'utile': utile, 'stima_imposte': stima_imposte, 'utile_netto': utile - stima_imposte,
        'per_mese': per_mese, 'n_mesi': len(conti),
        'anni': list(range(oggi.year, oggi.year - 6, -1)),
    }
    return render(request, 'app/conto_economico_annuale.html', context)


# ---------------------------------------------------------------------------
# Dettaglio mese (P&L)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def conto_economico_mese(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)

    if request.method == 'POST' and request.POST.get('azione') == 'classifica_costi':
        cat_valide = {c.codice for c in _categorie_attive()}
        n = 0
        for voce in VoceCosto.objects.using(dbname).filter(conto_economico=conto):
            nuovo = request.POST.get(f'catvoce_{voce.pk}', None)
            if nuovo is None:
                continue
            nuovo = nuovo if nuovo in cat_valide else ''
            if nuovo != (voce.categoria_codice or ''):
                voce.categoria_codice = nuovo or None
                voce.save(using=dbname, update_fields=['categoria_codice'])
                n += 1
        messages.success(request, f'{n} voci di costo aggiornate.')
        return redirect('conto_economico_mese', anno=anno, mese=mese)

    map_prod = _mappa_prodotti()
    map_cat = _mappa_categorie()

    # Ricavi: somma per prodotto, poi raggruppati per categoria prodotto
    voci_ricavo = list(VoceRicavo.objects.using(dbname).filter(conto_economico=conto))
    prod_tot = {}
    ricavi_manuali, tot_ricavi = [], Decimal('0')
    for r in voci_ricavo:
        tot_ricavi += r.importo
        if r.prodotto_codice:
            g = prod_tot.setdefault(r.prodotto_codice,
                                    {'codice': r.prodotto_codice,
                                     'nome': map_prod.get(r.prodotto_codice, r.prodotto_codice),
                                     'totale': Decimal('0')})
            g['totale'] += r.importo
        else:
            ricavi_manuali.append(r)
    ricavi_catgruppi = _raggruppa_prodotti_per_categoria(list(prod_tot.values()))

    # Costi raggruppati per categoria (le non classificate in un gruppo a parte).
    # Le voci non classificate NON entrano nel conto economico (totali/utile): restano
    # solo nel pannello di gestione finché non viene assegnata una categoria.
    voci_costo = list(VoceCosto.objects.using(dbname).filter(conto_economico=conto))
    gruppi = {}
    tot_costi = Decimal('0')          # solo costi classificati (nel prospetto)
    tot_costi_nonclass = Decimal('0')  # costi ancora da classificare (fuori dal prospetto)
    for c in voci_costo:
        key = c.categoria_codice or ''
        if key:
            tot_costi += c.importo
        else:
            tot_costi_nonclass += c.importo
        gruppi.setdefault(key, {'nome': map_cat.get(key, 'Da classificare') if key else 'Da classificare',
                                'voci': [], 'totale': Decimal('0')})
        gruppi[key]['voci'].append(c)
        gruppi[key]['totale'] += c.importo
    # ordina: categorie con nome prima, "da classificare" in fondo
    costi_gruppi = sorted(
        [{'codice': k, **v} for k, v in gruppi.items()],
        key=lambda g: (g['codice'] == '', g['nome'].lower())
    )
    # Solo i gruppi classificati entrano nel prospetto, raggruppati per macro-categoria costo
    costi_gruppi_prospetto = [g for g in costi_gruppi if g['codice']]
    costi_catgruppi = _raggruppa_costi_per_categoria(
        [{'codice': g['codice'], 'nome': g['nome'], 'totale': g['totale']} for g in costi_gruppi_prospetto])

    # Stima imposte: la base imponibile esclude i costi NON deducibili (che quindi
    # riducono l'utile reale ma non la stima delle imposte).
    cat_deducibili = {c.codice for c in CategoriaSpesa.objects.using('default').filter(deducibile=True)}
    costi_deducibili = sum((c.importo for c in voci_costo
                            if c.categoria_codice and c.categoria_codice in cat_deducibili), Decimal('0'))
    costi_nondeducibili = tot_costi - costi_deducibili
    utile = tot_ricavi - tot_costi
    imponibile = tot_ricavi - costi_deducibili           # reddito imponibile stimato
    stima_imposte = max(Decimal('0'), (imponibile * Decimal('0.24')).quantize(Decimal('0.01')))

    n_da_classificare = sum(1 for c in voci_costo if not c.categoria_codice)
    n_bancari_pending = MovimentoBancario.objects.using(dbname).filter(
        conto_economico=conto, stato='da_classificare').count()

    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'ricavi_catgruppi': ricavi_catgruppi, 'ricavi_manuali': ricavi_manuali,
        'tot_ricavi': tot_ricavi,
        'costi_gruppi': costi_gruppi, 'costi_catgruppi': costi_catgruppi,
        'tot_costi': tot_costi, 'tot_costi_nonclass': tot_costi_nonclass,
        'costi_nondeducibili': costi_nondeducibili, 'imponibile': imponibile,
        'utile': utile, 'stima_imposte': stima_imposte, 'utile_netto': utile - stima_imposte,
        'categorie': _categorie_attive(),
        'n_da_classificare': n_da_classificare,
        'n_bancari_pending': n_bancari_pending,
        'form_costo': VoceCostoForm(),
        'form_ricavo': VoceRicavoManualeForm(),
        'clienti_servizio': Cliente.objects.using(dbname).filter(conto_servizio=True).order_by('cognome', 'nome'),
    }
    return render(request, 'app/conto_economico_mese.html', context)


# ---------------------------------------------------------------------------
# Inserimento ricavi (pagina dedicata)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def conto_economico_ricavi(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)
    prodotti = _prodotti_attivi()

    if request.method == 'POST':
        n = 0
        for p in prodotti:
            importo = _parse_importo(request.POST.get(f'imp_{p.codice}', ''))
            # gestisce solo la voce manuale del prodotto (le voci da CSV restano intatte)
            esistente = VoceRicavo.objects.using(dbname).filter(
                conto_economico=conto, prodotto_codice=p.codice, origine_mb_id__isnull=True).first()
            if importo is None or importo == 0:
                if esistente:
                    esistente.delete(using=dbname)
                    n += 1
                continue
            if esistente:
                if esistente.importo != importo:
                    esistente.importo = importo
                    esistente.save(using=dbname, update_fields=['importo'])
                    n += 1
            else:
                v = VoceRicavo(conto_economico=conto, prodotto_codice=p.codice,
                               descrizione=p.nome, importo=importo, fonte='manuale')
                v.save(using=dbname)
                n += 1
        messages.success(request, f'Ricavi salvati ({n} voci aggiornate).')
        return redirect('conto_economico_mese', anno=anno, mese=mese)

    esistenti = {v.prodotto_codice: v.importo
                 for v in VoceRicavo.objects.using(dbname).filter(
                     conto_economico=conto, origine_mb_id__isnull=True)
                 if v.prodotto_codice}
    gruppi = [{'nome': g['nome'], 'codice': g['codice'],
               'righe': [{'prodotto': p, 'importo': esistenti.get(p.codice)} for p in g['prodotti']]}
              for g in _prodotti_per_categoria()]
    voci_manuali = list(VoceRicavo.objects.using(dbname).filter(
        conto_economico=conto, prodotto_codice__isnull=True))

    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'gruppi': gruppi, 'voci_manuali': voci_manuali,
        'form_ricavo': VoceRicavoManualeForm(),
        'nessun_prodotto': len(prodotti) == 0,
    }
    return render(request, 'app/conto_economico_ricavi.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def nuova_voce_ricavo(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)
    if request.method == 'POST':
        form = VoceRicavoManualeForm(request.POST)
        if form.is_valid():
            v = VoceRicavo(conto_economico=conto, prodotto_codice=None,
                           descrizione=form.cleaned_data['descrizione'],
                           importo=form.cleaned_data['importo'], fonte='manuale')
            v.save(using=dbname)
            messages.success(request, 'Voce di ricavo aggiunta.')
    return redirect('conto_economico_ricavi', anno=anno, mese=mese)


@login_required
@user_passes_test(is_manager_or_admin)
def elimina_voce_ricavo(request, anno, mese, pk):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    if request.method == 'POST':
        voce = get_object_or_404(VoceRicavo.objects.using(dbname), pk=pk)
        voce.delete(using=dbname)
        messages.success(request, 'Voce di ricavo eliminata.')
    return redirect('conto_economico_ricavi', anno=anno, mese=mese)


# ---------------------------------------------------------------------------
# Costi: inserimento manuale + eliminazione
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def nuova_voce_costo(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)
    if request.method == 'POST':
        form = VoceCostoForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            v = VoceCosto(conto_economico=conto,
                          categoria_codice=cd.get('categoria_codice') or None,
                          descrizione=cd['descrizione'],
                          importo=abs(cd['importo']),
                          data=cd.get('data'), fonte='manuale')
            v.save(using=dbname)
            messages.success(request, 'Voce di costo aggiunta.')
        else:
            messages.error(request, 'Dati non validi per la voce di costo.')
    return redirect('conto_economico_mese', anno=anno, mese=mese)


@login_required
@user_passes_test(is_manager_or_admin)
def elimina_voce_costo(request, anno, mese, pk):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    if request.method == 'POST':
        voce = get_object_or_404(VoceCosto.objects.using(dbname), pk=pk)
        # sgancia eventuale riga bancaria collegata
        riga = MovimentoBancario.objects.using(dbname).filter(voce_costo=voce).first()
        if riga:
            riga.voce_costo = None
            riga.stato = 'da_classificare'
            riga.save(using=dbname, update_fields=['voce_costo', 'stato'])
        voce.delete(using=dbname)
        messages.success(request, 'Voce di costo eliminata.')
    return redirect('conto_economico_mese', anno=anno, mese=mese)


# ---------------------------------------------------------------------------
# Import conto spese (cliente conto_servizio)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def importa_conto_spese(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)

    if request.method != 'POST':
        return redirect('conto_economico_mese', anno=anno, mese=mese)

    try:
        cliente_id = int(request.POST.get('cliente'))
    except (TypeError, ValueError):
        messages.error(request, 'Seleziona un conto spese valido.')
        return redirect('conto_economico_mese', anno=anno, mese=mese)

    cliente = Cliente.objects.using(dbname).filter(pk=cliente_id, conto_servizio=True).first()
    if not cliente:
        messages.error(request, 'Conto spese non trovato.')
        return redirect('conto_economico_mese', anno=anno, mese=mese)

    movimenti = Movimento.objects.using(dbname).filter(
        cliente=cliente, data__year=anno, data__month=mese)

    importati = saltati = 0
    for m in movimenti:
        # Tutti i movimenti (di qualunque segno) del conto spese diventano costi:
        # il segno del movimento dipende da come l'operatore lo registra, quindi non
        # si filtra per segno. Si salta solo l'importo nullo. Dedup su FK movimento.
        if m.importo == 0:
            continue
        if VoceCosto.objects.using(dbname).filter(conto_economico=conto, movimento=m).exists():
            saltati += 1
            continue
        v = VoceCosto(conto_economico=conto, categoria_codice=None,
                      descrizione=(m.note or m.get_tipo_display())[:200],
                      importo=abs(m.importo), data=m.data.date() if hasattr(m.data, 'date') else m.data,
                      fonte='conto_spese', movimento=m)
        v.save(using=dbname)
        importati += 1

    messages.success(request,
                     f'Conto spese importato: {importati} costi aggiunti, {saltati} già presenti. '
                     f'Assegna una categoria alle voci "Da classificare".')
    return redirect('conto_economico_mese', anno=anno, mese=mese)


# ---------------------------------------------------------------------------
# Estratto conto bancario: upload CSV + classificazione
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_manager_or_admin)
def carica_estratto(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db

    if request.method == 'POST':
        form = UploadEstrattoForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data['file']
            try:
                raw = f.read()
                try:
                    testo = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    testo = raw.decode('latin-1')
            except Exception:
                messages.error(request, 'Impossibile leggere il file.')
                return redirect('carica_estratto', anno=anno, mese=mese)

            righe = estratto_conto.parse_csv(testo)
            fname = getattr(f, 'name', '')[:200]
            per_mese = {}          # (anno, mese) -> ContoEconomico (creato on demand)
            conteggi = {}          # (anno, mese) -> nuove righe
            duplicati = ignorati = senza_data = 0
            for r in righe:
                # Uscite (negativo) = costi; entrate (positivo) = possibili ricavi.
                if r['importo'] == 0:
                    ignorati += 1
                    continue
                if not r['data']:
                    senza_data += 1
                    continue
                ym = (r['data'].year, r['data'].month)
                conto_m = per_mese.get(ym)
                if conto_m is None:
                    conto_m = _get_conto(dbname, ym[0], ym[1], request.user, crea=True)
                    per_mese[ym] = conto_m
                h = estratto_conto.hash_riga(r['data'], r['descrizione'], r['importo'])
                if MovimentoBancario.objects.using(dbname).filter(conto_economico=conto_m, hash_riga=h).exists():
                    duplicati += 1
                    continue
                mb = MovimentoBancario(conto_economico=conto_m, data=r['data'],
                                       descrizione=r['descrizione'], importo=r['importo'],
                                       hash_riga=h, stato='da_classificare', file_nome=fname)
                mb.save(using=dbname)
                conteggi[ym] = conteggi.get(ym, 0) + 1

            nuovi = sum(conteggi.values())
            coda = (f'{duplicati} duplicati saltati'
                    + (f', {senza_data} righe senza data' if senza_data else '') + '.')
            if conteggi:
                dett = ', '.join(f'{MESI_DICT.get(m, m)} {a} ({n})'
                                 for (a, m), n in sorted(conteggi.items()))
                messages.success(request,
                                 f'Import completato: {nuovi} nuove righe ripartite per mese — {dett}. ' + coda)
            else:
                messages.warning(request, f'Nessuna nuova riga importata. ' + coda)

            # Un solo mese -> vai alla sua classificazione; più mesi -> vai alla lista.
            if len(conteggi) == 1:
                (a, m) = next(iter(conteggi))
                return redirect('classifica_estratto', anno=a, mese=m)
            return redirect('conto_economico')
    else:
        form = UploadEstrattoForm()

    context = {'anno': anno, 'mese': mese,
               'mese_nome': MESI_DICT.get(mese, mese), 'form': form}
    return render(request, 'app/carica_estratto.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def classifica_estratto(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)

    is_super = request.user.is_superuser
    agenzie = _agenzie_db()
    dbs_validi = {a['db'] for a in agenzie}

    if request.method == 'POST':
        cat_valide = {c.codice for c in _categorie_attive()}
        prod_valide = {p.codice for p in _prodotti_attivi()}
        n_class = n_ign = warn_sum = 0
        for riga in MovimentoBancario.objects.using(dbname).filter(conto_economico=conto):
            stato = request.POST.get(f'stato_{riga.pk}')  # 'includi' | 'ignora' | None
            if stato is None:
                continue
            if stato == 'ignora':
                riga.stato = 'ignorato'
                riga.categoria_codice = None
                riga.prodotto_codice = None
                riga.allocazioni = []
                riga.voce_costo = None
                riga.save(using=dbname, update_fields=['stato', 'categoria_codice', 'prodotto_codice', 'allocazioni', 'voce_costo'])
                _rigenera_voci_da_riga(dbname, riga, anno, mese, [], request.user)
                n_ign += 1
                continue

            # Ripartizione: percentuali per agenzia (solo super-admin);
            # altrimenti 100% all'agenzia che ha caricato l'estratto.
            alloc = []
            if is_super:
                for a in agenzie:
                    raw = (request.POST.get(f'perc_{riga.pk}_{a["db"]}', '') or '').strip().replace(',', '.')
                    try:
                        perc = Decimal(raw) if raw else Decimal('0')
                    except Exception:
                        perc = Decimal('0')
                    if perc > 0:
                        alloc.append({'db': a['db'], 'perc': float(perc)})
            if not alloc:
                alloc = [{'db': dbname, 'perc': 100.0}]

            # Uscita = costo (categoria); entrata = ricavo (prodotto).
            if riga.importo < 0:
                cat = request.POST.get(f'cat_{riga.pk}', '') or ''
                cat = cat if cat in cat_valide else ''
                riga.categoria_codice = cat or None
                riga.prodotto_codice = None
                codice = cat
            else:
                prod = request.POST.get(f'prod_{riga.pk}', '') or ''
                prod = prod if prod in prod_valide else ''
                riga.prodotto_codice = prod or None
                riga.categoria_codice = None
                codice = prod

            somma = sum((Decimal(str(a['perc'])) for a in alloc), Decimal('0'))
            if codice and abs(somma - Decimal('100')) > Decimal('0.5'):
                warn_sum += 1

            riga.allocazioni = alloc
            riga.stato = 'classificato' if codice else 'da_classificare'
            riga.voce_costo = None
            riga.save(using=dbname, update_fields=['categoria_codice', 'prodotto_codice', 'allocazioni', 'stato', 'voce_costo'])
            _rigenera_voci_da_riga(dbname, riga, anno, mese, alloc, request.user)
            n_class += 1

        # Bonifica: dopo aver rigenerato tutte le righe con il tracciamento d'origine,
        # elimina le eventuali vecchie voci CSV senza origine per questo mese (create
        # dalla logica precedente alla ripartizione) che duplicherebbero i costi.
        rimosse = 0
        for dbn in set(AGENZIA_DATABASE_MAP.values()):
            conto_m = ContoEconomico.objects.using(dbn).filter(anno=anno, mese=mese).first()
            if conto_m:
                rimosse += VoceCosto.objects.using(dbn).filter(
                    conto_economico=conto_m, fonte='csv', origine_mb_id__isnull=True).delete()[0]

        msg = f'{n_class} righe classificate, {n_ign} ignorate.'
        if rimosse:
            msg += f' Rimossi {rimosse} doppioni residui.'
        if warn_sum:
            msg += f' Attenzione: {warn_sum} righe con percentuali che non sommano a 100%.'
        messages.success(request, msg)
        return redirect('classifica_estratto', anno=anno, mese=mese)

    righe = list(MovimentoBancario.objects.using(dbname).filter(conto_economico=conto))
    map_cat = _mappa_categorie()
    map_prod = _mappa_prodotti()
    for r in righe:
        r.is_ricavo = r.importo >= 0
        r.categoria_nome = map_cat.get(r.categoria_codice, '') if r.categoria_codice else ''
        r.prodotto_nome = map_prod.get(r.prodotto_codice, '') if r.prodotto_codice else ''
        perc_map = {a['db']: '' for a in agenzie}
        if r.allocazioni:
            for a in r.allocazioni:
                if a.get('db') in perc_map:
                    perc_map[a['db']] = _fmt_perc(a.get('perc'))
        elif dbname in perc_map:
            perc_map[dbname] = '100'
        r.alloc_cells = [{'db': a['db'], 'nome': a['nome'], 'perc': perc_map.get(a['db'], '')} for a in agenzie]
    costi_da = [r for r in righe if r.stato == 'da_classificare' and r.importo < 0]
    entrate_da = [r for r in righe if r.stato == 'da_classificare' and r.importo >= 0]
    righe_class = [r for r in righe if r.stato == 'classificato']
    righe_escl = [r for r in righe if r.stato == 'ignorato']
    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'costi_da': costi_da, 'entrate_da': entrate_da,
        'righe_class': righe_class, 'righe_escl': righe_escl,
        'n_costi_da': len(costi_da), 'n_entrate_da': len(entrate_da),
        'n_class': len(righe_class), 'n_escl': len(righe_escl),
        'n_righe': len(righe),
        'categorie': _categorie_attive(),
        'prodotti': _prodotti_attivi(), 'prodotti_gruppi': _prodotti_per_categoria(),
        'n_pending': len(costi_da) + len(entrate_da),
        'agenzie': agenzie, 'is_super': is_super,
    }
    return render(request, 'app/classifica_estratto.html', context)


# ---------------------------------------------------------------------------
# Vista consolidata (super-admin)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_superadmin)
def conto_economico_consolidato(request):
    oggi = timezone.localdate()
    form = ConsolidatoForm(request.GET or None, initial={'anno': oggi.year, 'mesi': [oggi.month]})
    dati = None

    if request.GET.get('anno') and form.is_valid():
        anno = form.cleaned_data['anno']
        mesi = sorted(int(m) for m in form.cleaned_data['mesi'])
        agenzie_sel = form.cleaned_data['agenzie']
        map_prod = _mappa_prodotti()
        map_cat = _mappa_categorie()
        cat_deducibili = {c.codice for c in CategoriaSpesa.objects.using('default').filter(deducibile=True)}

        cols = []                 # [{db, nome}] una per agenzia selezionata
        prod_rows, cat_rows = {}, {}
        manuali = {}              # db -> ricavi manuali
        tot_ric, tot_cos = {}, {}
        imponibile_col, imposte_col = {}, {}

        for ag in agenzie_sel:
            dbn = AGENZIA_DATABASE_MAP.get(ag.nome.lower())
            if not dbn:
                continue
            cols.append({'db': dbn, 'nome': ag.nome})
            tr = tc = ded = man = Decimal('0')
            # somma su tutti i mesi selezionati
            conti = ContoEconomico.objects.using(dbn).filter(anno=anno, mese__in=mesi)
            for conto in conti:
                for r in VoceRicavo.objects.using(dbn).filter(conto_economico=conto):
                    tr += r.importo
                    if r.prodotto_codice:
                        row = prod_rows.setdefault(r.prodotto_codice, {
                            'nome': map_prod.get(r.prodotto_codice, r.prodotto_codice), 'valori': {}, 'totale': Decimal('0')})
                        row['valori'][dbn] = row['valori'].get(dbn, Decimal('0')) + r.importo
                        row['totale'] += r.importo
                    else:
                        man += r.importo
                for v in VoceCosto.objects.using(dbn).filter(conto_economico=conto):
                    if not v.categoria_codice:
                        continue
                    tc += v.importo
                    row = cat_rows.setdefault(v.categoria_codice, {
                        'nome': map_cat.get(v.categoria_codice, v.categoria_codice), 'valori': {}, 'totale': Decimal('0')})
                    row['valori'][dbn] = row['valori'].get(dbn, Decimal('0')) + v.importo
                    row['totale'] += v.importo
                    if v.categoria_codice in cat_deducibili:
                        ded += v.importo
            manuali[dbn] = man
            tot_ric[dbn] = tr
            tot_cos[dbn] = tc
            imponibile_col[dbn] = tr - ded
            imposte_col[dbn] = max(Decimal('0'), ((tr - ded) * Decimal('0.24')).quantize(Decimal('0.01')))

        def celle(dcol):
            return [dcol.get(c['db'], Decimal('0')) for c in cols]

        for row in list(cat_rows.values()):
            row['celle'] = [row['valori'].get(c['db'], Decimal('0')) for c in cols]
        cat_list = sorted(cat_rows.values(), key=lambda x: x['nome'].lower())

        # Ricavi: righe prodotto raggruppate per categoria prodotto (subtotale per colonna)
        prod_cat = _prod_categoria_of()
        catp = _categorie_prodotto()
        ordine_cp = {c.codice: i for i, c in enumerate(catp)}
        map_catp = _mappa_cat_prodotto()
        prod_catgroups = {}
        for code, row in prod_rows.items():
            cc = prod_cat.get(code, '') or ''
            if cc not in ordine_cp:
                cc = ''
            g = prod_catgroups.setdefault(cc, {
                'nome': (map_catp.get(cc) if cc else 'Senza categoria') or 'Senza categoria',
                'ord': ordine_cp.get(cc, 9999), 'prodotti': [],
                'celle': [Decimal('0')] * len(cols), 'totale': Decimal('0')})
            pcelle = [row['valori'].get(c['db'], Decimal('0')) for c in cols]
            g['prodotti'].append({'nome': row['nome'], 'celle': pcelle, 'totale': row['totale']})
            g['celle'] = [a + b for a, b in zip(g['celle'], pcelle)]
            g['totale'] += row['totale']
        for g in prod_catgroups.values():
            g['prodotti'].sort(key=lambda x: x['nome'].lower())
        prod_catlist = [g for g in sorted(prod_catgroups.values(), key=lambda g: (g['ord'], g['nome'].lower())) if g['totale']]

        # Costi: righe conto raggruppate per macro-categoria costo (subtotale per colonna)
        spesa_cat = _spesa_categoria_of()
        catc = _categorie_costo()
        ordine_cc = {c.codice: i for i, c in enumerate(catc)}
        map_catc = _mappa_cat_costo()
        cost_catgroups = {}
        for code, row in cat_rows.items():
            cc = spesa_cat.get(code, '') or ''
            if cc not in ordine_cc:
                cc = ''
            g = cost_catgroups.setdefault(cc, {
                'nome': (map_catc.get(cc) if cc else 'Senza macro-categoria') or 'Senza macro-categoria',
                'ord': ordine_cc.get(cc, 9999), 'costi': [],
                'celle': [Decimal('0')] * len(cols), 'totale': Decimal('0')})
            pcelle = [row['valori'].get(c['db'], Decimal('0')) for c in cols]
            g['costi'].append({'nome': row['nome'], 'celle': pcelle, 'totale': row['totale']})
            g['celle'] = [a + b for a, b in zip(g['celle'], pcelle)]
            g['totale'] += row['totale']
        for g in cost_catgroups.values():
            g['costi'].sort(key=lambda x: x['nome'].lower())
        cost_catlist = [g for g in sorted(cost_catgroups.values(), key=lambda g: (g['ord'], g['nome'].lower())) if g['totale']]

        utile_col = {c['db']: tot_ric[c['db']] - tot_cos[c['db']] for c in cols}
        netto_col = {c['db']: utile_col[c['db']] - imposte_col[c['db']] for c in cols}
        g_ric = sum(tot_ric.values(), Decimal('0'))
        g_cos = sum(tot_cos.values(), Decimal('0'))
        g_man = sum(manuali.values(), Decimal('0'))
        g_imposte = sum(imposte_col.values(), Decimal('0'))

        if len(mesi) == 12:
            periodo = 'Anno intero'
        elif len(mesi) == 1:
            periodo = MESI_DICT.get(mesi[0], mesi[0])
        else:
            periodo = ', '.join(MESI_DICT.get(m, str(m)) for m in mesi)

        dati = {
            'anno': anno, 'periodo': periodo,
            'cols': cols,
            'prod_catlist': prod_catlist, 'cost_catlist': cost_catlist,
            'manuali_celle': celle(manuali), 'g_man': g_man, 'ha_manuali': g_man != 0,
            'totA_celle': celle(tot_ric), 'g_ric': g_ric,
            'totB_celle': celle(tot_cos), 'g_cos': g_cos,
            'diff_celle': celle(utile_col), 'g_utile': g_ric - g_cos,
            'imponibile_celle': celle(imponibile_col), 'g_imponibile': sum(imponibile_col.values(), Decimal('0')),
            'imposte_celle': celle(imposte_col), 'g_imposte': g_imposte,
            'netto_celle': celle(netto_col), 'g_netto': (g_ric - g_cos) - g_imposte,
            'n_cols': len(cols) + 2,
        }

    return render(request, 'app/conto_economico_consolidato.html', {'form': form, 'dati': dati})


# ---------------------------------------------------------------------------
# CRUD tassonomia globale (categorie di spesa / prodotti) — su DB 'default'
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_superadmin)
def categorie_spesa(request):
    categorie = CategoriaSpesa.objects.using('default').all()
    return render(request, 'app/lista_categorie_spesa.html', {'categorie': categorie})


@login_required
@user_passes_test(is_superadmin)
def nuova_categoria_spesa(request):
    if request.method == 'POST':
        form = CategoriaSpesaForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria "{obj.nome}" creata.')
            return redirect('categorie_spesa')
    else:
        form = CategoriaSpesaForm()
    return render(request, 'app/form_categoria_spesa.html', {'form': form, 'titolo': 'Nuova Categoria di Spesa'})


@login_required
@user_passes_test(is_superadmin)
def modifica_categoria_spesa(request, pk):
    obj = get_object_or_404(CategoriaSpesa.objects.using('default'), pk=pk)
    if request.method == 'POST':
        form = CategoriaSpesaForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria "{obj.nome}" aggiornata.')
            return redirect('categorie_spesa')
    else:
        form = CategoriaSpesaForm(instance=obj)
    return render(request, 'app/form_categoria_spesa.html',
                  {'form': form, 'oggetto': obj, 'titolo': f'Modifica: {obj.nome}'})


@login_required
@user_passes_test(is_superadmin)
def elimina_categoria_spesa(request, pk):
    obj = get_object_or_404(CategoriaSpesa.objects.using('default'), pk=pk)
    if request.method == 'POST':
        nome = obj.nome
        obj.delete(using='default')
        messages.success(request, f'Categoria "{nome}" eliminata.')
        return redirect('categorie_spesa')
    return render(request, 'app/elimina_tassonomia.html',
                  {'oggetto': obj, 'tipo': 'categoria di spesa', 'annulla_url': 'categorie_spesa'})


@login_required
@user_passes_test(is_superadmin)
def prodotti_ricavo(request):
    prodotti = ProdottoRicavo.objects.using('default').all()
    return render(request, 'app/lista_prodotti_ricavo.html', {'prodotti': prodotti})


@login_required
@user_passes_test(is_superadmin)
def nuovo_prodotto_ricavo(request):
    if request.method == 'POST':
        form = ProdottoRicavoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Prodotto "{obj.nome}" creato.')
            return redirect('prodotti_ricavo')
    else:
        form = ProdottoRicavoForm()
    return render(request, 'app/form_prodotto_ricavo.html', {'form': form, 'titolo': 'Nuovo Prodotto'})


@login_required
@user_passes_test(is_superadmin)
def modifica_prodotto_ricavo(request, pk):
    obj = get_object_or_404(ProdottoRicavo.objects.using('default'), pk=pk)
    if request.method == 'POST':
        form = ProdottoRicavoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Prodotto "{obj.nome}" aggiornato.')
            return redirect('prodotti_ricavo')
    else:
        form = ProdottoRicavoForm(instance=obj)
    return render(request, 'app/form_prodotto_ricavo.html',
                  {'form': form, 'oggetto': obj, 'titolo': f'Modifica: {obj.nome}'})


@login_required
@user_passes_test(is_superadmin)
def elimina_prodotto_ricavo(request, pk):
    obj = get_object_or_404(ProdottoRicavo.objects.using('default'), pk=pk)
    if request.method == 'POST':
        nome = obj.nome
        obj.delete(using='default')
        messages.success(request, f'Prodotto "{nome}" eliminato.')
        return redirect('prodotti_ricavo')
    return render(request, 'app/elimina_tassonomia.html',
                  {'oggetto': obj, 'tipo': 'prodotto', 'annulla_url': 'prodotti_ricavo'})


# ---------------------------------------------------------------------------
# CRUD Categorie Prodotto (raggruppamento prodotti) — su DB 'default'
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_superadmin)
def categorie_prodotto(request):
    categorie = CategoriaProdotto.objects.using('default').all()
    map_cat = _mappa_cat_prodotto()
    conteggi = {}
    for p in ProdottoRicavo.objects.using('default').all():
        conteggi[p.categoria_codice or ''] = conteggi.get(p.categoria_codice or '', 0) + 1
    righe = [{'cat': c, 'n_prodotti': conteggi.get(c.codice, 0)} for c in categorie]
    return render(request, 'app/lista_categorie_prodotto.html',
                  {'righe': righe, 'senza_categoria': conteggi.get('', 0)})


@login_required
@user_passes_test(is_superadmin)
def nuova_categoria_prodotto(request):
    if request.method == 'POST':
        form = CategoriaProdottoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria prodotto "{obj.nome}" creata.')
            return redirect('categorie_prodotto')
    else:
        form = CategoriaProdottoForm()
    return render(request, 'app/form_categoria_prodotto.html', {'form': form, 'titolo': 'Nuova Categoria Prodotto'})


@login_required
@user_passes_test(is_superadmin)
def modifica_categoria_prodotto(request, pk):
    obj = get_object_or_404(CategoriaProdotto.objects.using('default'), pk=pk)
    if request.method == 'POST':
        form = CategoriaProdottoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria prodotto "{obj.nome}" aggiornata.')
            return redirect('categorie_prodotto')
    else:
        form = CategoriaProdottoForm(instance=obj)
    return render(request, 'app/form_categoria_prodotto.html',
                  {'form': form, 'oggetto': obj, 'titolo': f'Modifica: {obj.nome}'})


@login_required
@user_passes_test(is_superadmin)
def elimina_categoria_prodotto(request, pk):
    obj = get_object_or_404(CategoriaProdotto.objects.using('default'), pk=pk)
    if request.method == 'POST':
        nome = obj.nome
        obj.delete(using='default')
        messages.success(request, f'Categoria prodotto "{nome}" eliminata.')
        return redirect('categorie_prodotto')
    return render(request, 'app/elimina_tassonomia.html',
                  {'oggetto': obj, 'tipo': 'categoria prodotto', 'annulla_url': 'categorie_prodotto'})


# ---------------------------------------------------------------------------
# CRUD Categorie Costo (macro-categorie dei conti di spesa) — su DB 'default'
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_superadmin)
def categorie_costo(request):
    categorie = CategoriaCosto.objects.using('default').all()
    conteggi = {}
    for c in CategoriaSpesa.objects.using('default').all():
        conteggi[c.categoria_costo_codice or ''] = conteggi.get(c.categoria_costo_codice or '', 0) + 1
    righe = [{'cat': c, 'n_conti': conteggi.get(c.codice, 0)} for c in categorie]
    return render(request, 'app/lista_categorie_costo.html',
                  {'righe': righe, 'senza_categoria': conteggi.get('', 0)})


@login_required
@user_passes_test(is_superadmin)
def nuova_categoria_costo(request):
    if request.method == 'POST':
        form = CategoriaCostoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria costo "{obj.nome}" creata.')
            return redirect('categorie_costo')
    else:
        form = CategoriaCostoForm()
    return render(request, 'app/form_categoria_costo.html', {'form': form, 'titolo': 'Nuova Categoria Costo'})


@login_required
@user_passes_test(is_superadmin)
def modifica_categoria_costo(request, pk):
    obj = get_object_or_404(CategoriaCosto.objects.using('default'), pk=pk)
    if request.method == 'POST':
        form = CategoriaCostoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.save(using='default')
            messages.success(request, f'Categoria costo "{obj.nome}" aggiornata.')
            return redirect('categorie_costo')
    else:
        form = CategoriaCostoForm(instance=obj)
    return render(request, 'app/form_categoria_costo.html',
                  {'form': form, 'oggetto': obj, 'titolo': f'Modifica: {obj.nome}'})


@login_required
@user_passes_test(is_superadmin)
def elimina_categoria_costo(request, pk):
    obj = get_object_or_404(CategoriaCosto.objects.using('default'), pk=pk)
    if request.method == 'POST':
        nome = obj.nome
        obj.delete(using='default')
        messages.success(request, f'Categoria costo "{nome}" eliminata.')
        return redirect('categorie_costo')
    return render(request, 'app/elimina_tassonomia.html',
                  {'oggetto': obj, 'tipo': 'categoria costo', 'annulla_url': 'categorie_costo'})
