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
    ProdottoRicavo, CategoriaSpesa, Cliente, Movimento, Agenzia,
)
from .database_utils import DatabaseManager, AGENZIA_DATABASE_MAP
from .forms import (
    ProdottoRicavoForm, CategoriaSpesaForm, VoceCostoForm,
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
            tot_costi += c.importo
            key = c.categoria_codice or ''
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
        tc = c.totale_costi()
        righe.append({'conto': c, 'mese_nome': MESI_DICT.get(c.mese, c.mese),
                      'ricavi': tr, 'costi': tc, 'utile': tr - tc})

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

    # Ricavi
    voci_ricavo = list(VoceRicavo.objects.using(dbname).filter(conto_economico=conto))
    ricavi_prodotto, ricavi_manuali, tot_ricavi = [], [], Decimal('0')
    for r in voci_ricavo:
        tot_ricavi += r.importo
        if r.prodotto_codice:
            ricavi_prodotto.append({'voce': r, 'nome': map_prod.get(r.prodotto_codice, r.prodotto_codice)})
        else:
            ricavi_manuali.append(r)

    # Costi raggruppati per categoria (le non classificate in un gruppo a parte)
    voci_costo = list(VoceCosto.objects.using(dbname).filter(conto_economico=conto))
    gruppi = {}
    tot_costi = Decimal('0')
    for c in voci_costo:
        tot_costi += c.importo
        key = c.categoria_codice or ''
        gruppi.setdefault(key, {'nome': map_cat.get(key, 'Da classificare') if key else 'Da classificare',
                                'voci': [], 'totale': Decimal('0')})
        gruppi[key]['voci'].append(c)
        gruppi[key]['totale'] += c.importo
    # ordina: categorie con nome prima, "da classificare" in fondo
    costi_gruppi = sorted(
        [{'codice': k, **v} for k, v in gruppi.items()],
        key=lambda g: (g['codice'] == '', g['nome'].lower())
    )

    # Stima imposte (solo categorie deducibili)
    cat_deducibili = {c.codice for c in CategoriaSpesa.objects.using('default').filter(deducibile=True)}
    costi_deducibili = sum((c.importo for c in voci_costo if (c.categoria_codice in cat_deducibili)), Decimal('0'))
    utile = tot_ricavi - tot_costi
    utile_deducibile = tot_ricavi - costi_deducibili
    stima_imposte = max(Decimal('0'), (utile_deducibile * Decimal('0.24')).quantize(Decimal('0.01')))

    n_da_classificare = sum(1 for c in voci_costo if not c.categoria_codice)
    n_bancari_pending = MovimentoBancario.objects.using(dbname).filter(
        conto_economico=conto, stato='da_classificare').count()

    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'ricavi_prodotto': ricavi_prodotto, 'ricavi_manuali': ricavi_manuali,
        'tot_ricavi': tot_ricavi,
        'costi_gruppi': costi_gruppi, 'tot_costi': tot_costi,
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
            esistente = VoceRicavo.objects.using(dbname).filter(
                conto_economico=conto, prodotto_codice=p.codice).first()
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
                 for v in VoceRicavo.objects.using(dbname).filter(conto_economico=conto)
                 if v.prodotto_codice}
    righe = [{'prodotto': p, 'importo': esistenti.get(p.codice)} for p in prodotti]
    voci_manuali = list(VoceRicavo.objects.using(dbname).filter(
        conto_economico=conto, prodotto_codice__isnull=True))

    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'righe': righe, 'voci_manuali': voci_manuali,
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
        # solo uscite (importo negativo) = spese; dedup su FK movimento
        if m.importo >= 0:
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
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)

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
            nuovi = duplicati = ignorati = 0
            for r in righe:
                if r['importo'] >= 0:
                    ignorati += 1  # entrate: non sono costi
                    continue
                h = estratto_conto.hash_riga(r['data'], r['descrizione'], r['importo'])
                if MovimentoBancario.objects.using(dbname).filter(conto_economico=conto, hash_riga=h).exists():
                    duplicati += 1
                    continue
                mb = MovimentoBancario(conto_economico=conto, data=r['data'],
                                       descrizione=r['descrizione'], importo=r['importo'],
                                       hash_riga=h, stato='da_classificare',
                                       file_nome=getattr(f, 'name', '')[:200])
                mb.save(using=dbname)
                nuovi += 1
            messages.success(request,
                             f'Import completato: {nuovi} nuove righe, {duplicati} duplicati saltati, '
                             f'{ignorati} entrate ignorate.')
            return redirect('classifica_estratto', anno=anno, mese=mese)
    else:
        form = UploadEstrattoForm()

    context = {'conto': conto, 'anno': anno, 'mese': mese,
               'mese_nome': MESI_DICT.get(mese, mese), 'form': form}
    return render(request, 'app/carica_estratto.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def classifica_estratto(request, anno, mese):
    db = DatabaseManager(request.user)
    dbname = db.user_db
    conto = _get_conto(dbname, anno, mese, request.user, crea=True)

    if request.method == 'POST':
        cat_valide = {c.codice for c in _categorie_attive()}
        n_class = n_ign = 0
        for riga in MovimentoBancario.objects.using(dbname).filter(conto_economico=conto):
            stato = request.POST.get(f'stato_{riga.pk}')  # 'includi' | 'ignora' | None
            if stato is None:
                continue
            if stato == 'ignora':
                riga.stato = 'ignorato'
                if riga.voce_costo_id:
                    vc = VoceCosto.objects.using(dbname).filter(pk=riga.voce_costo_id).first()
                    riga.voce_costo = None
                    riga.save(using=dbname, update_fields=['stato', 'voce_costo'])
                    if vc:
                        vc.delete(using=dbname)
                else:
                    riga.save(using=dbname, update_fields=['stato'])
                n_ign += 1
                continue

            cat = request.POST.get(f'cat_{riga.pk}', '') or ''
            cat = cat if cat in cat_valide else ''
            riga.categoria_codice = cat or None
            riga.stato = 'classificato' if cat else 'da_classificare'

            if riga.voce_costo_id:
                vc = VoceCosto.objects.using(dbname).filter(pk=riga.voce_costo_id).first()
            else:
                vc = None
            if vc is None:
                vc = VoceCosto(conto_economico=conto, fonte='csv')
            vc.categoria_codice = cat or None
            vc.descrizione = riga.descrizione[:200]
            vc.importo = abs(riga.importo)
            vc.data = riga.data
            vc.save(using=dbname)
            riga.voce_costo = vc
            riga.save(using=dbname, update_fields=['categoria_codice', 'stato', 'voce_costo'])
            n_class += 1

        messages.success(request, f'{n_class} righe classificate, {n_ign} ignorate.')
        return redirect('classifica_estratto', anno=anno, mese=mese)

    righe = list(MovimentoBancario.objects.using(dbname).filter(conto_economico=conto))
    map_cat = _mappa_categorie()
    for r in righe:
        r.categoria_nome = map_cat.get(r.categoria_codice, '') if r.categoria_codice else ''
    context = {
        'conto': conto, 'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
        'righe': righe, 'categorie': _categorie_attive(),
        'n_pending': sum(1 for r in righe if r.stato == 'da_classificare'),
    }
    return render(request, 'app/classifica_estratto.html', context)


# ---------------------------------------------------------------------------
# Vista consolidata (super-admin)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_superadmin)
def conto_economico_consolidato(request):
    oggi = timezone.localdate()
    form = ConsolidatoForm(request.GET or None, initial={'anno': oggi.year, 'mese': oggi.month})
    dati = None

    if request.GET.get('anno') and form.is_valid():
        anno = form.cleaned_data['anno']
        mese = int(form.cleaned_data['mese'])
        agenzie = form.cleaned_data['agenzie']
        map_prod = _mappa_prodotti()
        map_cat = _mappa_categorie()

        per_agenzia = []
        agg_prod, agg_cat = {}, {}
        agg_manuali = Decimal('0')
        tot_ricavi = tot_costi = Decimal('0')

        for ag in agenzie:
            dbname = AGENZIA_DATABASE_MAP.get(ag.nome.lower())
            if not dbname:
                continue
            rep = _report(dbname, anno, mese)
            per_agenzia.append({'agenzia': ag, 'report': rep})
            tot_ricavi += rep['tot_ricavi']
            tot_costi += rep['tot_costi']
            agg_manuali += rep['ricavi_manuali']
            for k, v in rep['ricavi_prodotto'].items():
                agg_prod[k] = agg_prod.get(k, Decimal('0')) + v
            for k, v in rep['costi_categoria'].items():
                agg_cat[k] = agg_cat.get(k, Decimal('0')) + v

        ricavi_prodotto = sorted(
            [{'codice': k, 'nome': map_prod.get(k, k), 'importo': v} for k, v in agg_prod.items()],
            key=lambda x: x['nome'].lower())
        costi_categoria = sorted(
            [{'codice': k, 'nome': (map_cat.get(k, 'Da classificare') if k else 'Da classificare'),
              'importo': v} for k, v in agg_cat.items()],
            key=lambda x: (x['codice'] == '', x['nome'].lower()))

        # nomi mesi/agenzie per il dettaglio espandibile
        for pa in per_agenzia:
            rep = pa['report']
            pa['ricavi_prodotto'] = [{'nome': map_prod.get(k, k), 'importo': v}
                                     for k, v in sorted(rep['ricavi_prodotto'].items())]
            pa['costi_categoria'] = [{'nome': (map_cat.get(k, 'Da classificare') if k else 'Da classificare'),
                                      'importo': v}
                                     for k, v in sorted(rep['costi_categoria'].items())]

        dati = {
            'anno': anno, 'mese': mese, 'mese_nome': MESI_DICT.get(mese, mese),
            'per_agenzia': per_agenzia,
            'ricavi_prodotto': ricavi_prodotto, 'ricavi_manuali': agg_manuali,
            'costi_categoria': costi_categoria,
            'tot_ricavi': tot_ricavi, 'tot_costi': tot_costi, 'utile': tot_ricavi - tot_costi,
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
