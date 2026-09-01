from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.db.models import Sum, Q, F, Window
from django.core.paginator import Paginator
from decimal import Decimal

from .models import (
    Cliente, Movimento, DistintaCassa, Comunicazione,
    ContoFinanziario, BilancioPeriodico, MovimentoConti, ActivityLog,
    AzzeramentoProgrammato
)
from .database_utils import DatabaseManager, get_user_database, sync_user_to_agency_db
from . import telegram_utils
from django.views.decorators.csrf import csrf_exempt
from .forms import (ClienteForm, MovimentoForm, DistintaCassaForm, ChiusuraDistintaForm,
                   VerificaDistintaForm, ComunicazioneForm, FiltroMovimentiForm, FiltroDistinteForm,
                   ContoFinanziarioForm, ModificaSaldoForm, BilancioPeriodoForm, GirocontoForm)


# Funzione di utilità per ottenere il database dell'utente
def get_user_database(user):
    """Ottieni il database associato all'agenzia dell'utente"""
    try:
        profilo = user.profiloutente
        return profilo.agenzia.database_name if profilo and profilo.agenzia else 'default'
    except:
        return 'default'


# Funzioni di utilità per i controlli di autorizzazione
def is_manager_or_admin(user):
    """Verifica se l'utente è un manager o un amministratore"""
    return user.is_superuser or user.groups.filter(name__in=['Manager', 'Amministratore']).exists()

def is_admin(user):
    """Verifica se l'utente è un amministratore"""
    return user.is_superuser or user.groups.filter(name='Amministratore').exists()


# Homepage semplice per tutti gli utenti
@login_required
def home(request):
    return render(request, 'app/home.html')

# ===== Indice Qualità del Credito (IQC) =====
# Combina: rotazione (volume giocato / credito), freschezza (età del credito) ed
# esposizione (ammontare del credito). Punteggio 0-100, più alto = credito migliore.
def _iqc_freschezza(giorni):
    if giorni is None:
        return 0
    if giorni < 7:
        return 100
    if giorni < 30:
        return 80
    if giorni < 90:
        return 50
    if giorni < 180:
        return 25
    return 0


def _iqc_esposizione(credito):
    # Solo valore assoluto del credito: più basso = meglio (soglie = fasce importo).
    c = float(credito or 0)
    if c <= 100:
        return 100
    if c <= 250:
        return 85
    if c <= 500:
        return 65
    if c <= 1000:
        return 45
    if c <= 2500:
        return 25
    return 5


def _iqc_classe(score):
    if score >= 75:
        return ('Ottimo', '#28a745')
    if score >= 50:
        return ('Buono', '#8dc63f')
    if score >= 25:
        return ('Attenzione', '#fd7e14')
    return ('Critico', '#dc3545')


def calcola_iqc(credito, giorni, volume30):
    """Ritorna il dizionario IQC per un cliente a debito.
    credito: importo dovuto (positivo); giorni: età ultimo movimento; volume30: volume
    giocato (schedine+ricariche) negli ultimi 30 giorni."""
    credito = Decimal(str(credito or 0))
    volume30 = Decimal(str(volume30 or 0))
    if credito and credito != 0:
        rot = volume30 / credito
        score_rot = min(100.0, float(rot) / 3.0 * 100.0)
    else:
        rot = Decimal('0')
        score_rot = 100.0
    score_fre = _iqc_freschezza(giorni)
    score_esp = _iqc_esposizione(credito)
    iqc = round(0.40 * score_rot + 0.35 * score_fre + 0.25 * score_esp)
    classe, colore = _iqc_classe(iqc)
    return {'iqc': iqc, 'classe': classe, 'colore': colore,
            'rotazione': round(float(rot), 2), 'score_rot': round(score_rot),
            'score_fre': score_fre, 'score_esp': score_esp}


# Dashboard (accesso ristretto)
@login_required
def dashboard(request):
    # Verifica esplicita dell'accesso: solo Manager e Amministratore possono accedere
    if not (request.user.is_superuser or
            request.user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
        messages.error(request, 'Non sei autorizzato ad accedere alla dashboard.')
        return redirect('home')
    
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    
    # Il saldo di ogni cliente è mantenuto aggiornato a ogni scrittura di movimento
    # (Movimento.save/delete/salda chiamano aggiorna_saldo): non serve ricalcolarlo qui.

    # Recupera i clienti (reali) con fido superato: saldo negativo che supera il fido in valore assoluto.
    # I conti di servizio (POS, spese, aggiustamenti) sono esclusi da tutti i conteggi clienti.
    clienti_fido_superato = db.get_queryset(Cliente).filter(conto_servizio=False).filter(saldo__lt=0).filter(saldo__lt=-F('fido_massimo'))

    # Recupera i clienti con saldo negativo in ritardo da più di 3 giorni
    from datetime import timedelta
    data_limite = timezone.now() - timedelta(days=3)

    clienti_in_ritardo = []
    for cliente in db.get_queryset(Cliente).filter(conto_servizio=False).filter(saldo__lt=0):
        # Trova l'ultimo movimento non saldato del cliente
        ultimo_movimento = cliente.movimenti.filter(saldato=False).order_by('-data').first()
        if ultimo_movimento:
            giorni_ritardo = (timezone.now() - ultimo_movimento.data).days
            if giorni_ritardo > 3:
                clienti_in_ritardo.append({
                    'cliente': cliente,
                    'ultimo_movimento': ultimo_movimento,
                    'giorni_ritardo': giorni_ritardo
                })

    # Recupera le distinte in attesa di verifica
    distinte_da_verificare = db.get_queryset(DistintaCassa).filter(stato='chiusa')

    # Recupera statistiche generali (solo clienti reali)
    totale_clienti = db.get_queryset(Cliente).filter(conto_servizio=False).count()
    saldo_complessivo = Cliente.calcola_saldo_complessivo(request.user)
    saldo_conti_servizio = Cliente.calcola_saldo_conti_servizio(request.user)

    # ===== KPI analisi crediti (solo clienti reali) =====
    from django.db.models import Max
    from datetime import timedelta
    adesso = timezone.now()
    clienti_reali = db.get_queryset(Cliente).filter(conto_servizio=False)

    # Fascia di anzianità del credito: si usa la data dell'ULTIMO movimento del cliente.
    COLORI_AGING = {'settimana': '#20c997', 'recenti': '#28a745', 'm1_3': '#ffc107', 'm3_6': '#fd7e14', 'm6': '#dc3545'}

    def _bucket(riferimento):
        giorni = (adesso - riferimento).days if riferimento else 99999
        if giorni < 7:
            return 'settimana'
        elif giorni < 30:
            return 'recenti'
        elif giorni < 90:
            return 'm1_3'
        elif giorni < 180:
            return 'm3_6'
        return 'm6'

    # Credito in essere e aging (crediti fermi) per data dell'ultimo movimento
    debitori = clienti_reali.filter(saldo__lt=0).annotate(ultimo_mov=Max('movimenti__data'))
    credito_in_essere = Decimal('0')
    aging = {'settimana': Decimal('0'), 'recenti': Decimal('0'), 'm1_3': Decimal('0'), 'm3_6': Decimal('0'), 'm6': Decimal('0')}
    aging_clienti = {'settimana': [], 'recenti': [], 'm1_3': [], 'm3_6': [], 'm6': []}
    # Distribuzione del credito per fascia di importo (istogramma)
    distribuzione = [
        {'key': 'f0', 'label': '≤ 100 €', 'lo': Decimal('0'), 'hi': Decimal('100'), 'n': 0, 'tot': Decimal('0'), 'clienti': []},
        {'key': 'f1', 'label': '100–250 €', 'lo': Decimal('100'), 'hi': Decimal('250'), 'n': 0, 'tot': Decimal('0'), 'clienti': []},
        {'key': 'f2', 'label': '250–500 €', 'lo': Decimal('250'), 'hi': Decimal('500'), 'n': 0, 'tot': Decimal('0'), 'clienti': []},
        {'key': 'f3', 'label': '500–1.000 €', 'lo': Decimal('500'), 'hi': Decimal('1000'), 'n': 0, 'tot': Decimal('0'), 'clienti': []},
        {'key': 'f4', 'label': '1.000–2.500 €', 'lo': Decimal('1000'), 'hi': Decimal('2500'), 'n': 0, 'tot': Decimal('0'), 'clienti': []},
        {'key': 'f5', 'label': '> 2.500 €', 'lo': Decimal('2500'), 'hi': None, 'n': 0, 'tot': Decimal('0'), 'clienti': []},
    ]
    n_debitori = 0
    for c in debitori:
        imp = -c.saldo  # importo positivo dovuto dal cliente
        credito_in_essere += imp
        n_debitori += 1
        b = _bucket(c.ultimo_mov)
        aging[b] += imp
        giorni = (adesso - c.ultimo_mov).days if c.ultimo_mov else None
        aging_clienti[b].append({'nome': c.nome_completo, 'pk': c.pk, 'giorni': giorni, 'importo': imp})
        giorni_deb = (adesso - c.ultimo_mov).days if c.ultimo_mov else None
        for f in distribuzione:
            if imp > f['lo'] and (f['hi'] is None or imp <= f['hi']):
                f['n'] += 1
                f['tot'] += imp
                f['clienti'].append({'nome': c.nome_completo, 'pk': c.pk, 'giorni': giorni_deb, 'importo': imp})
                break
    for b in aging_clienti:
        aging_clienti[b].sort(key=lambda x: x['importo'], reverse=True)
    for f in distribuzione:
        f['clienti'].sort(key=lambda x: x['importo'], reverse=True)
    _etichette_aging = {'settimana': '< 1 settimana', 'recenti': '1 sett. – 1 mese',
                        'm1_3': '1–3 mesi', 'm3_6': '3–6 mesi', 'm6': 'oltre 6 mesi'}
    aging_fasce = [{'key': k, 'label': _etichette_aging[k], 'clienti': aging_clienti[k],
                    'totale': aging[k]} for k in ('settimana', 'recenti', 'm1_3', 'm3_6', 'm6')]

    def _pct(v):
        return (v / credito_in_essere * 100) if credito_in_essere else Decimal('0')

    aging_pct = {k: _pct(v) for k, v in aging.items()}

    # Flussi ultimi 7 giorni
    sette = adesso - timedelta(days=7)
    mov7 = db.get_queryset(Movimento).filter(data__gte=sette, cliente__conto_servizio=False)
    rientrato_7 = mov7.filter(importo__gt=0).aggregate(t=Sum('importo'))['t'] or Decimal('0')
    erogato_7 = abs(mov7.filter(importo__lt=0).aggregate(t=Sum('importo'))['t'] or Decimal('0'))
    volume_7 = erogato_7 + rientrato_7  # volume totale movimentato (valore assoluto)
    n_mov7 = mov7.count()

    # Rigiro del credito (7 gg): credito rientrato / credito in essere (formula precedente)
    rigiro_sett = _pct(rientrato_7)

    # Classifica volumi giocato (schedine + ricariche) per cliente, per periodo.
    def _classifica_volumi(giorni, limite=10):
        inizio = adesso - timedelta(days=giorni)
        rows = (db.get_queryset(Movimento)
                .filter(tipo__in=['schedina', 'ricarica'], cliente__conto_servizio=False, data__gte=inizio)
                .values('cliente_id', 'cliente__nome', 'cliente__cognome', 'tipo')
                .annotate(tot=Sum('importo')))
        agg = {}
        for r in rows:
            cid = r['cliente_id']
            e = agg.get(cid)
            if e is None:
                e = {'pk': cid,
                     'nome': ('%s %s' % (r['cliente__cognome'] or '', r['cliente__nome'] or '')).strip(),
                     'schedina': Decimal('0'), 'ricarica': Decimal('0')}
                agg[cid] = e
            val = abs(r['tot'] or Decimal('0'))
            if r['tipo'] == 'schedina':
                e['schedina'] += val
            else:
                e['ricarica'] += val
        lista = list(agg.values())
        for e in lista:
            e['totale'] = e['schedina'] + e['ricarica']
        lista.sort(key=lambda x: x['totale'], reverse=True)
        return lista[:limite]

    volumi = {
        'settimana': _classifica_volumi(7),
        'mese': _classifica_volumi(30),
        'anno': _classifica_volumi(365),
    }

    # Indice Qualità del Credito (IQC): volume giocato (30g) vs età vs ammontare, per debitore
    _v30_inizio = adesso - timedelta(days=30)
    vol30_map = {}
    for r in (db.get_queryset(Movimento)
              .filter(tipo__in=['schedina', 'ricarica'], cliente__conto_servizio=False, data__gte=_v30_inizio)
              .values('cliente_id').annotate(tot=Sum('importo'))):
        vol30_map[r['cliente_id']] = abs(r['tot'] or Decimal('0'))

    qualita_clienti = []
    _classi_ordine = ['Ottimo', 'Buono', 'Attenzione', 'Critico']
    _classi_colore = {'Ottimo': '#28a745', 'Buono': '#8dc63f', 'Attenzione': '#fd7e14', 'Critico': '#dc3545'}
    _conta_classi = {k: 0 for k in _classi_ordine}
    _somma_iqc = 0
    for c in debitori:
        imp = -c.saldo
        giorni = (adesso - c.ultimo_mov).days if c.ultimo_mov else None
        vol30 = vol30_map.get(c.pk, Decimal('0'))
        q = calcola_iqc(imp, giorni, vol30)
        qualita_clienti.append({'pk': c.pk, 'nome': c.nome_completo, 'credito': imp,
                                'giorni': giorni, 'volume': vol30, **q})
        _conta_classi[q['classe']] += 1
        _somma_iqc += q['iqc']
    qualita_clienti.sort(key=lambda x: x['iqc'])  # dai più rischiosi
    n_qual = len(qualita_clienti)
    qualita_distribuzione = [
        {'classe': k, 'colore': _classi_colore[k], 'n': _conta_classi[k],
         'pct': (Decimal(_conta_classi[k]) / n_qual * 100) if n_qual else Decimal('0')}
        for k in _classi_ordine
    ]
    qualita_media = round(_somma_iqc / n_qual) if n_qual else 0

    # Distribuzione del credito tra i clienti: top debitori, colorati per anzianità del credito
    top_debitori = []
    for c in debitori.order_by('saldo')[:10]:
        b = _bucket(c.ultimo_mov)
        top_debitori.append({
            'pk': c.pk,
            'nome': c.nome_completo,
            'importo': -c.saldo,
            'bucket': b,
            'colore': COLORI_AGING[b],
        })
    max_deb = top_debitori[0]['importo'] if top_debitori else Decimal('0')
    for t in top_debitori:
        t['pct_barra'] = (t['importo'] / max_deb * 100) if max_deb else Decimal('0')
        t['pct_tot'] = _pct(t['importo'])
    concentrazione_top5 = _pct(sum((t['importo'] for t in top_debitori[:5]), Decimal('0')))

    # Percentuali/barra per l'istogramma di distribuzione
    max_n_fascia = max((f['n'] for f in distribuzione), default=0) or 1
    for f in distribuzione:
        f['pct_barra'] = (Decimal(f['n']) / max_n_fascia * 100) if max_n_fascia else Decimal('0')
        f['pct_tot'] = _pct(f['tot'])

    # Trend mensile (ultimi 6 mesi): erogato / rientrato / netto per mese
    from django.db.models import Case, When, Count
    from django.db.models.functions import TruncMonth

    def _add_mesi(d, n):
        m = d.month - 1 + n
        return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)

    primo_mese_corrente = timezone.localdate().replace(day=1)
    inizio_trend = _add_mesi(primo_mese_corrente, -5)
    righe_trend = (mov7.model.objects.using(db.user_db)
                   .filter(cliente__conto_servizio=False, data__date__gte=inizio_trend)
                   .annotate(mese=TruncMonth('data'))
                   .values('mese')
                   .annotate(
                       erogato=Sum(Case(When(importo__lt=0, then=F('importo')), default=Decimal('0'))),
                       rientrato=Sum(Case(When(importo__gt=0, then=F('importo')), default=Decimal('0'))),
                       n=Count('id'),
                   ))
    per_mese = {}
    for r in righe_trend:
        md = r['mese']
        chiave = (md.year, md.month)
        per_mese[chiave] = r
    trend = []
    for i in range(6):
        md = _add_mesi(inizio_trend, i)
        r = per_mese.get((md.year, md.month))
        erog = abs(r['erogato']) if r and r['erogato'] else Decimal('0')
        rientr = r['rientrato'] if r and r['rientrato'] else Decimal('0')
        trend.append({'mese': md, 'erogato': erog, 'rientrato': rientr,
                      'netto': rientr - erog, 'n': r['n'] if r else 0})

    kpi = {
        'credito_in_essere': credito_in_essere,
        'n_debitori': n_debitori,
        'aging': aging,
        'aging_pct': aging_pct,
        'aging_clienti': aging_clienti,
        'aging_fasce': aging_fasce,
        'rientrato_7': rientrato_7,
        'erogato_7': erogato_7,
        'volume_7': volume_7,
        'flusso_netto_7': rientrato_7 - erogato_7,
        'n_mov7': n_mov7,
        'rigiro_sett': rigiro_sett,
        'trend': trend,
        'top_debitori': top_debitori,
        'concentrazione_top5': concentrazione_top5,
        'distribuzione': distribuzione,
        'volumi': volumi,
        'qualita_clienti': qualita_clienti[:15],
        'qualita_distribuzione': qualita_distribuzione,
        'qualita_media': qualita_media,
        'qualita_n': n_qual,
    }
    
    # Aggiorna automaticamente il saldo della cassa dalle distinte e recupera il valore
    try:
        # Prima aggiorna il saldo della cassa basandosi sulle distinte verificate
        ContoFinanziario.aggiorna_saldo_cassa_da_distinte(request.user)
        
        # Poi recupera il saldo aggiornato
        conto_cassa = db.get_queryset(ContoFinanziario).get(tipo='cassa', nome='Cassa Agenzia')
        saldo_cassa_agenzia = conto_cassa.saldo
    except ContoFinanziario.DoesNotExist:
        # Se il conto non esiste, crealo automaticamente
        try:
            ContoFinanziario.crea_conti_default(request.user)
            conto_cassa = db.get_queryset(ContoFinanziario).get(tipo='cassa', nome='Cassa Agenzia')
            saldo_cassa_agenzia = conto_cassa.saldo
        except Exception as e:
            messages.error(request, f'Errore nella creazione dei conti predefiniti: {str(e)}. Contatta l\'amministratore.')
            saldo_cassa_agenzia = 0

    # Recupera l'ultima distinta aperta dall'operatore corrente
    try:
        distinta_corrente = db.get_queryset(DistintaCassa).filter(
            operatore=request.user,
            stato='aperta'
        ).latest('data', 'ora_inizio')
    except DistintaCassa.DoesNotExist:
        distinta_corrente = None

    context = {
        'clienti_fido_superato': clienti_fido_superato,
        'clienti_in_ritardo': clienti_in_ritardo,
        'distinte_da_verificare': distinte_da_verificare,
        'totale_clienti': totale_clienti,
        'saldo_complessivo': saldo_complessivo,
        'saldo_conti_servizio': saldo_conti_servizio,
        'saldo_cassa_agenzia': saldo_cassa_agenzia,
        'distinta_corrente': distinta_corrente,
        'kpi': kpi,
        'vol_periodi': [('settimana', volumi['settimana']),
                        ('mese', volumi['mese']),
                        ('anno', volumi['anno'])],
    }

    return render(request, 'app/dashboard.html', context)


# Gestione Clienti
@login_required
@permission_required('app.view_cliente', raise_exception=True)
def lista_clienti(request):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    
    # Il saldo è già mantenuto aggiornato a ogni scrittura di movimento:
    # nessun ricalcolo per-richiesta (causava query O(N) su DB remoto).
    clienti = db.get_queryset(Cliente)

    # Filtraggio clienti
    filtro_nome = request.GET.get('nome', '')
    if filtro_nome:
        clienti = clienti.filter(
            Q(nome__icontains=filtro_nome) |
            Q(cognome__icontains=filtro_nome)
        )

    filtro_rating = request.GET.get('rating', '')
    if filtro_rating:
        clienti = clienti.filter(rating=filtro_rating)
    
    # Paginazione
    paginator = Paginator(clienti, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'filtro_nome': filtro_nome,
        'filtro_rating': filtro_rating,
        'rating_choices': Cliente.RATING_CHOICES,
    }
    
    return render(request, 'app/lista_clienti.html', context)

@login_required
@permission_required('app.view_cliente', raise_exception=True)
def dettaglio_cliente(request, pk):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    cliente = db.get_object_or_404(Cliente, pk=pk)

    # Aggiorna il saldo del cliente
    cliente.aggiorna_saldo(user=request.user)

    # Movimenti del cliente con saldo progressivo calcolato dal database (window function).
    # La paginazione carica solo le righe della pagina, non l'intera storia: evita
    # i timeout sui clienti con migliaia di movimenti.
    movimenti_qs = cliente.movimenti.annotate(
        saldo_prog=Window(
            expression=Sum('importo'),
            order_by=[F('data').asc(), F('id').asc()],
        )
    ).order_by('-data', '-id')

    paginator = Paginator(movimenti_qs, 50)
    page_number = request.GET.get('page')
    movimenti = paginator.get_page(page_number)

    # Recupera le comunicazioni del cliente
    comunicazioni = cliente.comunicazioni.all().order_by('-data')[:10]

    # Verifica se c'è una distinta aperta per la funzionalità saldo
    distinta_aperta = db.get_queryset(DistintaCassa).filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    # Indice Qualità del Credito (IQC) del cliente, se a debito
    from django.db.models import Max as _Max, Sum as _Sum
    from datetime import timedelta as _td
    iqc_cliente = None
    if cliente.saldo < 0:
        credito = -cliente.saldo
        ultimo = cliente.movimenti.aggregate(u=_Max('data'))['u']
        giorni = (timezone.now() - ultimo).days if ultimo else None
        v30 = cliente.movimenti.filter(
            tipo__in=['schedina', 'ricarica'], data__gte=timezone.now() - _td(days=30)
        ).aggregate(t=_Sum('importo'))['t']
        vol30 = abs(v30) if v30 else Decimal('0')
        iqc_cliente = calcola_iqc(credito, giorni, vol30)
        iqc_cliente.update({'credito': credito, 'giorni': giorni, 'volume': vol30})

    context = {
        'cliente': cliente,
        'movimenti': movimenti,
        'comunicazioni': comunicazioni,
        'distinta_aperta': distinta_aperta,
        'iqc_cliente': iqc_cliente,
    }

    return render(request, 'app/dettaglio_cliente.html', context)

@login_required
@permission_required('app.add_cliente', raise_exception=True)
def nuovo_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST, user=request.user)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.creato_da_id = request.user.id
            
            # Determina il database corretto in base all'agenzia dell'utente
            try:
                profilo = request.user.profiloutente
                db_name = profilo.agenzia.database_name if profilo and profilo.agenzia else 'default'
            except:
                db_name = 'default'
                
            cliente.save(using=db_name)
            messages.success(request, f'Cliente {cliente.nome_completo} creato con successo!')
            return redirect('dettaglio_cliente', pk=cliente.pk)
    else:
        form = ClienteForm(user=request.user)
    
    return render(request, 'app/form_cliente.html', {'form': form, 'titolo': 'Nuovo Cliente'})

@login_required
@permission_required('app.change_cliente', raise_exception=True)
def modifica_cliente(request, pk):
    db = DatabaseManager(request.user)
    cliente = get_object_or_404(db.get_queryset(Cliente), pk=pk)
    
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente, user=request.user)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.modificato_da_id = request.user.id
            db.save_object(cliente)
            messages.success(request, f'Cliente {cliente.nome_completo} aggiornato con successo!')
            return redirect('dettaglio_cliente', pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente, user=request.user)
    
    return render(request, 'app/form_cliente.html', {'form': form, 'cliente': cliente, 'titolo': 'Modifica Cliente'})


# Gestione Movimenti
@login_required
def lista_movimenti(request):
    # Usa il nuovo DatabaseManager per gestire tutto
    db = DatabaseManager(request.user)
    
    # Il saldo è già mantenuto aggiornato a ogni scrittura di movimento:
    # nessun ricalcolo per-richiesta (causava query O(N) su DB remoto).

    # Ottieni tutti i movimenti con relazioni precaricate
    movimenti = db.get_queryset(
        Movimento, 
        select_related=['cliente', 'distinta', 'creato_da']
    )

    # Verifica se c'è una distinta aperta (per la funzionalità saldo)
    distinta_aperta = db.get_queryset(DistintaCassa).filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    # Prepara il form di filtro
    form_filtro = FiltroMovimentiForm(request.GET, user=request.user)
    
    # Applica i filtri se il form è valido
    if form_filtro.is_valid():
        # Filtro per cliente
        cliente = form_filtro.cleaned_data.get('cliente')
        if cliente:
            movimenti = movimenti.filter(cliente=cliente)
        
        # Filtro per tipo
        tipo = form_filtro.cleaned_data.get('tipo')
        if tipo:
            movimenti = movimenti.filter(tipo=tipo)
        
        # Filtro per data
        data_inizio = form_filtro.cleaned_data.get('data_inizio')
        if data_inizio:
            movimenti = movimenti.filter(data__gte=data_inizio)
        
        data_fine = form_filtro.cleaned_data.get('data_fine')
        if data_fine:
            movimenti = movimenti.filter(data__date__lte=data_fine)
        
        # Filtro per stato saldato
        saldato = form_filtro.cleaned_data.get('saldato')
        if saldato:
            movimenti = movimenti.filter(saldato=(saldato == 'True'))
    
    # Ordina per data
    movimenti = movimenti.order_by('-data')
    
    # Paginazione
    paginator = Paginator(movimenti, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'form_filtro': form_filtro,
        'distinta_aperta': distinta_aperta,
    }

    return render(request, 'app/lista_movimenti.html', context)

@login_required
@permission_required('app.add_movimento', raise_exception=True)
def nuovo_movimento(request):
    db = DatabaseManager(request.user)
    user_db = get_user_database(request.user)
    # Verifica se esiste una distinta aperta
    try:
        distinta = db.get_queryset(DistintaCassa).filter(
            operatore=request.user,
            stato='aperta'
        ).latest('data', 'ora_inizio')
    except DistintaCassa.DoesNotExist:
        messages.error(request, 'Non esiste una distinta aperta. Creane una prima di registrare movimenti.')
        return redirect('nuova_distinta')

    # Verifica se la richiesta è AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = MovimentoForm(request.POST, distinta=distinta, user=request.user)
        if form.is_valid():
            movimento = form.save(commit=False)
            movimento.distinta = distinta
            movimento.creato_da_id = request.user.id

            # Salva la nota dal campo manuale
            if request.POST.get('note'):
                movimento.note = request.POST.get('note')

            # Anti doppio invio: se un movimento identico (stesso cliente, tipo, importo,
            # distinta e operatore) è stato creato negli ultimi 10 secondi, è quasi
            # certamente un doppio click con server lento: non salvare il duplicato.
            from datetime import timedelta
            if movimento.tipo in ['schedina', 'ricarica', 'pagamento_debito']:
                importo_firmato = -abs(movimento.importo)
            else:
                importo_firmato = abs(movimento.importo)
            # Il confronto considera SOLO i movimenti inseriti dal form: quelli di
            # compensazione creati da 'salda'/'salda tutti' hanno movimento_origine
            # valorizzato e vanno ignorati, altrimenti un inserimento manuale legittimo
            # subito dopo un salda verrebbe scambiato per doppio click.
            duplicato = db.get_queryset(Movimento).filter(
                cliente=movimento.cliente,
                tipo=movimento.tipo,
                importo=importo_firmato,
                distinta=distinta,
                creato_da_id=request.user.id,
                movimento_origine__isnull=True,
                data_creazione__gte=timezone.now() - timedelta(seconds=10)
            ).exists()
            if duplicato:
                msg_duplicato = (
                    f'Movimento {movimento.get_tipo_display()} di {abs(movimento.importo)} € '
                    f'per {movimento.cliente} già registrato pochi istanti fa: doppio invio ignorato.'
                )
                if is_ajax:
                    return JsonResponse({'success': False, 'message': msg_duplicato}, status=409)
                messages.warning(request, msg_duplicato)
                redirect_to = request.POST.get('redirect_to')
                if redirect_to:
                    return redirect(redirect_to)
                from django.urls import reverse
                return redirect(reverse('dettaglio_distinta', args=[distinta.pk]) + '?apri_form=1')

            # Salva il movimento
            db.save_object(movimento)

            # Registra l'azione nei log
            # Crea un dizionario con i dati del movimento per il log
            movimento_data = {
                'tipo': movimento.get_tipo_display(),
                'importo': str(abs(movimento.importo)),
                'cliente': movimento.cliente.nome_completo,
                'distinta': movimento.distinta.id,
                'note': movimento.note if movimento.note else '',
                'saldato': movimento.saldato
            }
            ActivityLog.log_action(
                user=request.user,
                obj=movimento,
                action='create',
                description=f"Creazione movimento {movimento.get_tipo_display()} di {abs(movimento.importo)} € per {movimento.cliente}",
                data_after=movimento_data
            )

            # Aggiorna il saldo del cliente
            cliente = movimento.cliente
            cliente.aggiorna_saldo(user=request.user)

            success_message = f'Movimento {movimento.get_tipo_display()} di {abs(movimento.importo)} € per {movimento.cliente} registrato!'

            # Se è una richiesta AJAX, restituisci una risposta JSON
            if is_ajax:
                # Calcola i totali aggiornati
                from django.db.models import Sum

                # Calcola i totali entrate/uscite
                totale_entrate = distinta.movimenti.filter(importo__gt=0).aggregate(Sum('importo'))['importo__sum'] or 0
                totale_uscite = abs(distinta.movimenti.filter(importo__lt=0).aggregate(Sum('importo'))['importo__sum'] or 0)

                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'movimento': {
                        'id': movimento.id,
                        'tipo': movimento.get_tipo_display(),
                        'tipo_raw': movimento.tipo,
                        'importo': str(abs(movimento.importo)),
                        'importo_raw': str(movimento.importo),
                        'cliente': movimento.cliente.nome_completo,
                        'cliente_id': movimento.cliente.id,
                        'data': timezone.localtime(movimento.data).strftime('%d/%m/%Y %H:%M'),
                        'saldato': movimento.saldato,
                        'operatore': request.user.username,
                        'note': movimento.note if movimento.note else '',
                    },
                    'totali': {
                        'entrate': str(totale_entrate),
                        'uscite': str(totale_uscite),
                        'count': distinta.movimenti.count()
                    }
                })

            # Altrimenti, usa il sistema di messaggi di Django
            messages.success(request, success_message)

            # Controlla se è stato specificato un URL di redirect personalizzato
            redirect_to = request.POST.get('redirect_to')

            if redirect_to:
                # Redirect all'URL specificato nel form
                return redirect(redirect_to)
            else:
                from django.urls import reverse
                # Redirect alla pagina della distinta con parametro per aprire il form
                return redirect(reverse('dettaglio_distinta', args=[distinta.pk]) + '?apri_form=1')
    else:
        form = MovimentoForm(distinta=distinta, user=request.user)

    context = {
        'form': form,
        'distinta': distinta,
        'titolo': 'Nuovo Movimento'
    }

    return render(request, 'app/form_movimento.html', context)

@login_required
def salda_movimento(request, pk):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    movimento = db.get_object_or_404(
        Movimento,
        select_related=['distinta', 'cliente'],
        pk=pk
    )
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Verifica se esiste una distinta aperta
    try:
        distinta = db.get_queryset(DistintaCassa).filter(
            operatore=request.user,
            stato='aperta'
        ).latest('data', 'ora_inizio')
    except DistintaCassa.DoesNotExist:
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Non esiste una distinta aperta'}, status=400)
        messages.error(request, 'Non esiste una distinta aperta. Creane una prima di saldare movimenti.')
        return redirect('nuova_distinta')

    # Verifichiamo se il movimento è già saldato
    if movimento.saldato:
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Movimento già saldato'}, status=400)
        messages.error(request, 'Movimento già saldato.')
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('dettaglio_distinta', pk=distinta.pk)

    # Ottieni il cliente
    cliente = movimento.cliente

    # Dati prima del saldo per il log
    movimento_before = {
        'tipo': movimento.get_tipo_display(),
        'importo': str(abs(movimento.importo)),
        'cliente': movimento.cliente.nome_completo,
        'distinta': movimento.distinta.id,
        'note': movimento.note if movimento.note else '',
        'saldato': movimento.saldato
    }

    # Usiamo il metodo salda che aggiorna correttamente il saldo e crea il movimento opposto
    success = movimento.salda(request.user)
    if not success:
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Impossibile saldare il movimento. Verifica che ci sia una distinta aperta.'}, status=400)
        messages.error(request, 'Impossibile saldare il movimento. Verifica che ci sia una distinta aperta.')
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('lista_movimenti')

    # Dati dopo il saldo per il log
    movimento_after = {
        'tipo': movimento.get_tipo_display(),
        'importo': str(abs(movimento.importo)),
        'cliente': movimento.cliente.nome_completo,
        'distinta': movimento.distinta.id,
        'note': movimento.note if movimento.note else '',
        'saldato': movimento.saldato
    }

    # Registra l'azione nei log
    ActivityLog.log_action(
        user=request.user,
        obj=movimento,
        action='payment',
        description=f"Saldo movimento #{movimento.id} ({movimento.get_tipo_display()}) di {abs(movimento.importo)} € per {movimento.cliente}",
        data_before=movimento_before,
        data_after=movimento_after
    )

    message = f'Movimento {movimento.get_tipo_display()} di {abs(movimento.importo)} € saldato!'

    if is_ajax:
        # Calcola i totali aggiornati
        from django.db.models import Sum

        # Calcola i totali entrate/uscite
        totale_entrate = distinta.movimenti.filter(importo__gt=0).aggregate(Sum('importo'))['importo__sum'] or 0
        totale_uscite = abs(distinta.movimenti.filter(importo__lt=0).aggregate(Sum('importo'))['importo__sum'] or 0)

        # Prepara la risposta JSON
        # Identifica quale movimento di compensazione è stato creato
        tipo_compensazione = ""
        if movimento.importo < 0:  # Schedina o ricarica (negativo)
            tipo_compensazione = "incasso_credito"
        else:  # Prelievo (positivo)
            tipo_compensazione = "pagamento_debito"

        # Trova il movimento di compensazione appena creato
        movimento_compensazione = db.get_queryset(Movimento).filter(
            movimento_origine=movimento,
            distinta=distinta
        ).first()

        return JsonResponse({
            'success': True,
            'message': message,
            'saldato': True,  # Stato aggiornato
            'cliente': {
                'id': cliente.id,
                'nome_completo': cliente.nome_completo,
                'saldo': str(cliente.saldo),
                'fido_massimo': str(cliente.fido_massimo),
                'saldo_disponibile': str(cliente.saldo_disponibile),
            },
            'totali': {
                'entrate': str(totale_entrate),
                'uscite': str(totale_uscite),
                'movimento_importo': str(abs(movimento.importo)),
                'movimento_tipo': movimento.tipo
            },
            # Aggiungi i dati del movimento di compensazione appena creato
            'movimento_compensazione': {
                'id': movimento_compensazione.id if movimento_compensazione else 'NEW',
                'tipo': tipo_compensazione,
                'tipo_display': 'Incasso Credito' if tipo_compensazione == 'incasso_credito' else 'Pagamento Debito',
                'importo': str(abs(movimento.importo)),
                'cliente_nome': cliente.nome_completo,
                'data': timezone.localtime(movimento_compensazione.data).strftime('%d/%m/%Y %H:%M') if movimento_compensazione else timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M'),
                # 'note': movimento_compensazione.note if movimento_compensazione and movimento_compensazione.note else '',
                'data_creazione': timezone.localtime(movimento_compensazione.data_creazione).strftime('%d/%m/%Y %H:%M') if movimento_compensazione else '',
                'data_modifica': timezone.localtime(movimento_compensazione.data_modifica).strftime('%d/%m/%Y %H:%M') if movimento_compensazione else '',
                'creato_da': movimento_compensazione.creato_da.username if movimento_compensazione and movimento_compensazione.creato_da else '',
                'modificato_da': movimento_compensazione.modificato_da.username if movimento_compensazione and movimento_compensazione.modificato_da else '',
                'movimento_origine_id': movimento.id,
                'movimento_origine_tipo': movimento.get_tipo_display(),
                'note': movimento_compensazione.note if movimento_compensazione and movimento_compensazione.note else ''
            } if movimento_compensazione else {}
        })

    messages.success(request, message)

    # Redirect back
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('dettaglio_distinta', pk=distinta.pk)

@login_required
@permission_required('app.view_movimento', raise_exception=True)
def dettaglio_movimento(request, pk):
    """View per visualizzare i dettagli di un movimento (sola lettura)"""
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    movimento = db.get_object_or_404(
        Movimento, 
        select_related=['distinta', 'cliente', 'creato_da'],
        pk=pk
    )
    
    # Recupera i log delle attività relativi a questo movimento
    from django.contrib.contenttypes.models import ContentType
    movimento_content_type = ContentType.objects.get_for_model(Movimento)
    logs = db.get_queryset(ActivityLog).filter(
        content_type=movimento_content_type,
        object_id=movimento.id
    ).order_by('-timestamp')
    
    context = {
        'movimento': movimento,
        'logs': logs,
        'titolo': f'Dettaglio Movimento #{movimento.id}'
    }
    
    return render(request, 'app/dettaglio_movimento.html', context)

@login_required
@permission_required('app.change_movimento', raise_exception=True)
def modifica_movimento(request, pk):
    """Vista per modificare SOLO le note di un movimento"""
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    movimento = db.get_object_or_404(
        Movimento,
        select_related=['distinta', 'cliente'],
        pk=pk
    )

    # Verifica autorizzazioni
    if movimento.distinta.stato != 'aperta':
        messages.error(request, 'Non è possibile modificare un movimento di una distinta chiusa.')
        return redirect('dettaglio_distinta', pk=movimento.distinta.pk)

    if movimento.distinta.operatore != request.user and not request.user.is_superuser:
        messages.error(request, 'Non sei autorizzato a modificare questo movimento.')
        return redirect('dettaglio_distinta', pk=movimento.distinta.pk)

    if request.method == 'POST':
        # Raccoglie i dati prima della modifica per il log
        movimento_before = {
            'note': movimento.note if movimento.note else ''
        }

        # Recupera solo le note dal POST
        nuove_note = request.POST.get('note', '')

        # Aggiorna solo le note
        movimento.note = nuove_note
        movimento.modificato_da_id = request.user.id

        # Salva solo il campo note (NON ricalcola il saldo progressivo)
        db.save_object(movimento)

        # Raccoglie i dati dopo la modifica per il log
        movimento_after = {
            'note': movimento.note if movimento.note else ''
        }

        # Registra l'azione nei log
        ActivityLog.log_action(
            user=request.user,
            obj=movimento,
            action='update',
            description=f"Modifica note movimento #{movimento.id} ({movimento.get_tipo_display()}) per {movimento.cliente}",
            data_before=movimento_before,
            data_after=movimento_after
        )

        messages.success(request, 'Note aggiornate con successo!')
        return redirect('dettaglio_distinta', pk=movimento.distinta.pk)

    context = {
        'movimento': movimento,
    }

    return render(request, 'app/modifica_movimento.html', context)

@login_required
@login_required
@permission_required('app.delete_movimento', raise_exception=True)
def elimina_movimento(request, pk):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    movimento = db.get_object_or_404(
        Movimento,
        select_related=['distinta', 'cliente'],
        pk=pk
    )

    # Se la distinta è verificata, solo un admin può eliminare
    if movimento.distinta.stato == 'verificata' and not is_admin(request.user):
        messages.error(request, 'Non è possibile eliminare un movimento da una distinta verificata.')
        return redirect('lista_movimenti')
    
    if request.method == 'POST':
        # Ottieni il cliente prima di eliminare il movimento
        cliente = movimento.cliente

        # Registra l'azione nei log prima di eliminare il movimento
        movimento_data = {
            'tipo': movimento.get_tipo_display(),
            'importo': str(abs(movimento.importo)),
            'cliente': movimento.cliente.nome_completo,
            'distinta': movimento.distinta.id,
            'note': movimento.note if movimento.note else '',
            'saldato': movimento.saldato
        }

        # Registra l'azione nei log
        ActivityLog.log_action(
            user=request.user,
            obj=movimento,
            action='delete',
            description=f"Eliminazione movimento #{movimento.id} ({movimento.get_tipo_display()}) di {abs(movimento.importo)} € per {movimento.cliente}",
            data_before=movimento_data
        )

        # Elimina il movimento (il metodo delete già aggiorna il saldo considerando solo i movimenti non saldati)
        movimento.delete(user=request.user)
        messages.success(request, 'Movimento eliminato con successo!')
        return redirect('lista_movimenti')
    
    context = {
        'movimento': movimento,
    }
    
    return render(request, 'app/conferma_elimina_movimento.html', context)


# Gestione Distinte di Cassa
@login_required
@permission_required('app.view_distintacassa', raise_exception=True)
def lista_distinte(request):
    db = DatabaseManager(request.user)
    user_db = get_user_database(request.user)
    distinte = db.get_queryset(DistintaCassa).all()
    
    # Prepara il form di filtro
    form_filtro = FiltroDistinteForm(request.GET, user=request.user)
    
    # Applica i filtri se il form è valido
    if form_filtro.is_valid():
        # Filtro per operatore
        operatore_id = form_filtro.cleaned_data.get('operatore')
        if operatore_id:
            distinte = distinte.filter(operatore_id=operatore_id)
        
        # Filtro per stato
        stato = form_filtro.cleaned_data.get('stato')
        if stato:
            distinte = distinte.filter(stato=stato)
        
        # Filtro per data
        data_inizio = form_filtro.cleaned_data.get('data_inizio')
        if data_inizio:
            distinte = distinte.filter(data__gte=data_inizio)
        
        data_fine = form_filtro.cleaned_data.get('data_fine')
        if data_fine:
            distinte = distinte.filter(data__lte=data_fine)
    
    # Ordina per data e ora
    distinte = distinte.order_by('-data', '-ora_inizio')
    
    # Paginazione
    paginator = Paginator(distinte, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Calcola la differenza con la distinta precedente per ogni distinta nella pagina
    from django.db.models import Q
    from datetime import datetime, time

    for distinta in page_obj:
        # Crea un datetime combinato per la distinta corrente
        distinta_datetime = timezone.make_aware(
            datetime.combine(distinta.data, distinta.ora_inizio)
        )

        # Trova TUTTE le distinte precedenti (sia data precedente che stessa data con ora precedente)
        # Cerchiamo la distinta con il datetime immediatamente precedente
        distinta_precedente = db.get_queryset(DistintaCassa).filter(
            Q(data__lt=distinta.data) |
            Q(data=distinta.data, ora_inizio__lt=distinta.ora_inizio)
        ).order_by('-data', '-ora_inizio').first()

        # Calcola la differenza: cassa_iniziale (corrente) - cassa_finale (precedente)
        if distinta_precedente and distinta_precedente.cassa_finale is not None:
            distinta.diff_cassa_precedente = distinta.cassa_iniziale - distinta_precedente.cassa_finale
        else:
            distinta.diff_cassa_precedente = None

    context = {
        'page_obj': page_obj,
        'form_filtro': form_filtro,
    }

    return render(request, 'app/lista_distinte.html', context)

@login_required
@permission_required('app.view_distintacassa', raise_exception=True)
def dettaglio_distinta(request, pk):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    distinta = db.get_object_or_404(DistintaCassa, pk=pk)

    # Verifica se l'utente può modificare la distinta
    can_edit = (
        distinta.stato == 'aperta' or
        (distinta.stato == 'chiusa' and is_manager_or_admin(request.user)) or
        (distinta.data == timezone.now().date() and is_manager_or_admin(request.user)) or
        is_admin(request.user)
    )

    # Verifica se l'utente può riaprire la distinta
    can_reopen = (
        distinta.stato == 'chiusa' and
        (
            # Admin può riaprire qualsiasi distinta chiusa
            is_admin(request.user) or
            # Operatore può riaprire solo le sue distinte della stessa data
            (distinta.operatore == request.user and distinta.data == timezone.now().date())
        )
    )

    # Recupera i movimenti della distinta
    movimenti = list(distinta.movimenti
                     .select_related('cliente', 'creato_da', 'modificato_da')
                     .all().order_by('-data'))

    # Raggruppa i movimenti dello stesso cliente/tipo con timestamp di modifica entro
    # 3 secondi l'uno dall'altro (es. quelli creati insieme da "salda tutti") in
    # un'unica voce espandibile.
    def _raggruppa_movimenti(movs, soglia_secondi=3):
        gruppi = []
        for m in movs:
            dm = m.data_modifica
            g = gruppi[-1] if gruppi else None
            if (g and dm is not None and g['_mod'] is not None
                    and g['_cid'] == m.cliente_id and g['_tipo'] == m.tipo
                    and abs((g['_mod'] - dm).total_seconds()) <= soglia_secondi):
                g['movimenti'].append(m)
                g['totale'] += m.importo
                g['_mod'] = dm
                if not m.saldato:
                    g['tutti_saldati'] = False
            else:
                gruppi.append({'_cid': m.cliente_id, '_tipo': m.tipo, '_mod': dm,
                               'movimenti': [m], 'totale': m.importo, 'tutti_saldati': m.saldato})
        return gruppi

    entrate_gruppi = _raggruppa_movimenti([m for m in movimenti if m.importo > 0])
    uscite_gruppi = _raggruppa_movimenti([m for m in movimenti if m.importo < 0])

    # Calcola totali
    totale_entrate = sum(m.importo for m in movimenti if m.importo > 0)
    totale_uscite = sum(abs(m.importo) for m in movimenti if m.importo < 0)

    # Assicuriamoci che totale_entrate e totale_uscite non siano None
    totale_entrate = totale_entrate or 0
    totale_uscite = totale_uscite or 0

    # Form per nuovo movimento se la distinta è aperta
    form_movimento = None
    movimenti_da_saldare = []
    cliente_selezionato = None

    if distinta.stato == 'aperta' and (distinta.operatore == request.user or is_admin(request.user)):
        form_movimento = MovimentoForm(distinta=distinta, user=request.user)

        # Gestisci la selezione del cliente per vedere i movimenti da saldare
        cliente_id = request.GET.get('cliente')
        if cliente_id:
            try:
                cliente_selezionato = db.get_queryset(Cliente).get(pk=cliente_id)
                movimenti_da_saldare = db.get_queryset(Movimento).filter(
                    cliente=cliente_selezionato,
                    saldato=False
                ).order_by('-data')
            except Cliente.DoesNotExist:
                pass

    # Form per chiusura distinta
    form_chiusura = None
    if distinta.stato == 'aperta' and (distinta.operatore == request.user or is_admin(request.user)):
        form_chiusura = ChiusuraDistintaForm(instance=distinta)

    # Form per verifica distinta
    form_verifica = None
    if distinta.stato == 'chiusa' and is_manager_or_admin(request.user):
        form_verifica = VerificaDistintaForm(instance=distinta)

    context = {
        'distinta': distinta,
        'movimenti': movimenti,
        'entrate_gruppi': entrate_gruppi,
        'uscite_gruppi': uscite_gruppi,
        'totale_entrate': totale_entrate,
        'totale_uscite': totale_uscite,
        'form_movimento': form_movimento,
        'form_chiusura': form_chiusura,
        'form_verifica': form_verifica,
        'cliente_selezionato': cliente_selezionato,
        'movimenti_da_saldare': movimenti_da_saldare,
        'can_edit': can_edit,
        'can_reopen': can_reopen,
    }

    return render(request, 'app/dettaglio_distinta.html', context)

@login_required
@permission_required('app.add_distintacassa', raise_exception=True)
def nuova_distinta(request):
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    
    # Verifica se l'utente ha già una distinta aperta
    distinta_aperta = db.get_queryset(DistintaCassa).filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    if distinta_aperta:
        messages.warning(request, 'Hai già una distinta aperta. Chiudila prima di crearne una nuova.')
        return redirect('lista_distinte')

    # Ottieni il conto cassa
    try:
        # Prima aggiorna il saldo della cassa basandosi sulle distinte chiuse
        ContoFinanziario.aggiorna_saldo_cassa_da_distinte(request.user)
        
        conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
        if not conto_cassa:
            messages.warning(request, 'Nessun conto cassa trovato nel bilancio. Contatta l\'amministratore.')
            return redirect('lista_distinte')
    except:
        messages.error(request, 'Errore nel recupero del conto cassa. Contatta l\'amministratore.')
        return redirect('lista_distinte')

    if request.method == 'POST':
        form = DistintaCassaForm(request.POST, user=request.user)
        if form.is_valid():
            distinta = form.save(commit=False)
            distinta.operatore_id = request.user.id
            distinta.data = timezone.now().date()
            distinta.ora_inizio = timezone.localtime(timezone.now()).time()
            distinta.stato = 'aperta'

            # Recupera i dati dal form
            cassa_iniziale = form.cleaned_data['cassa_iniziale']
            prelievo_parziale = form.cleaned_data.get('prelievo_parziale', False)

            # L'operatore inserisce il contante realmente contato: se supera il saldo di
            # sistema non blocchiamo (va registrata la realtà), ma avvisiamo.
            if cassa_iniziale > conto_cassa.saldo:
                messages.warning(request, f'La cassa iniziale inserita ({cassa_iniziale} €) supera il saldo di sistema ({conto_cassa.saldo} €). Verifica il conteggio: la differenza verrà registrata.')

            # Salva il valore della cassa iniziale
            distinta.cassa_iniziale = cassa_iniziale
            db.save_object(distinta)

            # Aggiorna il saldo del conto cassa (mai sotto zero)
            saldo_precedente = conto_cassa.saldo
            conto_cassa.saldo = max(Decimal('0'), conto_cassa.saldo - cassa_iniziale)
            conto_cassa.modificato_da_id = request.user.id
            db.save_object(conto_cassa)

            # Registra il movimento nel registro movimenti conti
            MovimentoConti.registra_modifica_diretta(
                conto=conto_cassa,
                importo_precedente=saldo_precedente,
                importo_nuovo=conto_cassa.saldo,
                operatore=request.user,
                note=f"Prelievo per apertura Distinta N° {distinta.pk} - Operatore: {request.user.username}"
            )

            # Registra l'azione nei log
            distinta_data = {
                'operatore': request.user.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'stato': 'aperta'
            }
            ActivityLog.log_action(
                user=request.user,
                obj=distinta,
                action='create',
                description=f"Apertura Distinta N° {distinta.pk} con cassa iniziale di {distinta.cassa_iniziale} € {'' if not prelievo_parziale else '(prelievo parziale)'}",
                data_after=distinta_data
            )

            messages.success(request, f'Distinta N° {distinta.pk} aperta con successo! Prelevati {distinta.cassa_iniziale} € dalla cassa.')
            return redirect('dettaglio_distinta', pk=distinta.pk)
    else:
        form = DistintaCassaForm(user=request.user)

    # Suggerimento mostrato in pagina = cassa finale dell'ultima distinta chiusa/verificata
    ultima_chiusa = db.get_queryset(DistintaCassa).filter(
        stato__in=['chiusa', 'verificata']
    ).order_by('-data', '-ora_inizio').first()
    if ultima_chiusa is not None and ultima_chiusa.cassa_finale is not None:
        suggerito = ultima_chiusa.cassa_finale
    else:
        suggerito = conto_cassa.saldo

    return render(request, 'app/form_distinta.html', {
        'form': form, 'titolo': 'Nuova Distinta', 'conto_cassa': conto_cassa, 'suggerito': suggerito,
    })

@login_required
@permission_required('app.change_distintacassa', raise_exception=True)
def chiudi_distinta(request, pk):
    db = DatabaseManager(request.user)
    distinta = get_object_or_404(db.get_queryset(DistintaCassa), pk=pk)

    # Verifica autorizzazioni
    if distinta.operatore != request.user and not is_admin(request.user):
        return HttpResponseForbidden("Non sei autorizzato a chiudere questa distinta.")

    if distinta.stato != 'aperta':
        messages.error(request, 'Questa distinta è già stata chiusa.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    # Ottieni il conto cassa
    try:
        conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
        if not conto_cassa:
            messages.warning(request, 'Nessun conto cassa trovato nel bilancio. La distinta sarà chiusa, ma il saldo della cassa non sarà aggiornato.')
    except:
        messages.error(request, 'Errore nel recupero del conto cassa. La distinta sarà chiusa, ma il saldo della cassa non sarà aggiornato.')
        conto_cassa = None

    if request.method == 'POST':
        form = ChiusuraDistintaForm(request.POST, instance=distinta)
        if form.is_valid():
            distinta = form.save(commit=False)
            distinta.ora_fine = timezone.localtime(timezone.now()).time()
            distinta.stato = 'chiusa'

            # Calcola la differenza di cassa
            totale_entrate = distinta.movimenti.filter(importo__gt=0).aggregate(Sum('importo'))['importo__sum'] or 0
            totale_uscite = distinta.movimenti.filter(importo__lt=0).aggregate(Sum('importo'))['importo__sum'] or 0
            totale_uscite = abs(totale_uscite)

            # Assicuriamoci che i campi di cassa non siano None
            if distinta.cassa_finale is None:
                distinta.cassa_finale = 0
                messages.warning(request, 'Cassa finale non impostata. Impostata automaticamente a 0.')

            if distinta.cassa_iniziale is None:
                distinta.cassa_iniziale = 0
                messages.warning(request, 'Cassa iniziale non impostata. Impostata automaticamente a 0.')

            if distinta.totale_bevande is None:
                distinta.totale_bevande = 0

            distinta.totale_entrate = totale_entrate
            distinta.totale_uscite = totale_uscite

            # Ricalcola SEMPRE la differenza cassa lato server in Decimal.
            # Il valore eventualmente inviato dal form è calcolato in JavaScript
            # (virgola mobile + parsing del numero localizzato con la virgola) e può
            # divergere di centesimi: la fonte autorevole è questo calcolo.
            # cassa_finale e totale_bevande sono già stati normalizzati a 0 se None.
            saldo_totale = (
                distinta.cassa_finale - totale_entrate + totale_uscite - distinta.totale_bevande
            )
            distinta.differenza_cassa = saldo_totale
            if distinta.saldo_terminale:
                distinta.differenza_cassa -= distinta.saldo_terminale

            # Dati prima della chiusura per il log
            distinta_before = {
                'operatore': distinta.operatore.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'stato': 'aperta'
            }

            # Salva la distinta chiusa
            db.save_object(distinta)

            # Alert Telegram se la cassa finale supera la soglia configurata per l'agenzia
            try:
                soglia = telegram_utils.get_soglia(db.user_db)
                if soglia is not None and distinta.cassa_finale is not None and distinta.cassa_finale > soglia:
                    telegram_utils.notifica(
                        db.user_db,
                        telegram_utils.msg_cassa_oltre_soglia(distinta, soglia, db.user_db)
                    )
            except Exception:
                pass

            # Aggiorna il saldo del conto cassa con il valore della cassa finale
            if conto_cassa:
                saldo_precedente = conto_cassa.saldo
                conto_cassa.saldo += distinta.cassa_finale
                conto_cassa.modificato_da_id = request.user.id
                db.save_object(conto_cassa)

                # Registra il movimento nel registro movimenti conti
                MovimentoConti.registra_modifica_diretta(
                    conto=conto_cassa,
                    importo_precedente=saldo_precedente,
                    importo_nuovo=conto_cassa.saldo,
                    operatore=request.user,
                    note=f"Versamento per chiusura Distinta N° {distinta.pk} - Operatore: {request.user.username}"
                )

                messages.info(request, f'Saldo cassa aggiornato con il valore della cassa finale: {distinta.cassa_finale} €')

            # Dati dopo la chiusura per il log
            distinta_after = {
                'operatore': distinta.operatore.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'ora_fine': distinta.ora_fine.strftime('%H:%M'),
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'cassa_finale': str(distinta.cassa_finale),
                'totale_entrate': str(distinta.totale_entrate),
                'totale_uscite': str(distinta.totale_uscite),
                'totale_bevande': str(distinta.totale_bevande),
                'saldo_terminale': str(distinta.saldo_terminale) if distinta.saldo_terminale else "0.00",
                'differenza_cassa': str(distinta.differenza_cassa) if distinta.differenza_cassa else "0.00",
                'stato': 'chiusa'
            }

            # Registra l'azione nei log
            ActivityLog.log_action(
                user=request.user,
                obj=distinta,
                action='status_change',
                description=f"Chiusura Distinta N° {distinta.pk} con cassa finale di {distinta.cassa_finale} € e differenza di {distinta.differenza_cassa} €",
                data_before=distinta_before,
                data_after=distinta_after
            )

            messages.success(request, f'Distinta N° {distinta.pk} chiusa con successo!')

            # Se questa era l'ultima distinta aperta, esegui un eventuale azzeramento
            # conti di servizio programmato (differito perché c'erano distinte aperte).
            esegui_azzeramento_programmato_se_possibile(db, request)

            return redirect('lista_distinte')
    else:
        # Recupera i movimenti della distinta per i totali
        movimenti = distinta.movimenti.all()
        totale_entrate = sum(m.importo for m in movimenti if m.importo > 0)
        totale_uscite = sum(abs(m.importo) for m in movimenti if m.importo < 0)

        # Assicuriamoci che totale_entrate e totale_uscite non siano None
        totale_entrate = totale_entrate or 0
        totale_uscite = totale_uscite or 0

        # Calcola la differenza di cassa per la visualizzazione iniziale
        if distinta.cassa_finale is not None:
            saldo_totale = (
                distinta.cassa_finale - totale_entrate + totale_uscite - (distinta.totale_bevande or 0)
            )
            differenza_cassa_calcolata = saldo_totale
            if distinta.saldo_terminale:
                differenza_cassa_calcolata -= distinta.saldo_terminale
        else:
            differenza_cassa_calcolata = 0

        # Imposta il valore calcolato nella distinta per la visualizzazione
        distinta.differenza_cassa = differenza_cassa_calcolata
        
        form = ChiusuraDistintaForm(instance=distinta)

    # Recupera i movimenti della distinta per i totali (se non già fatto)
    if request.method == 'POST':
        movimenti = distinta.movimenti.all()
        totale_entrate = sum(m.importo for m in movimenti if m.importo > 0)
        totale_uscite = sum(abs(m.importo) for m in movimenti if m.importo < 0)

        # Assicuriamoci che totale_entrate e totale_uscite non siano None
        totale_entrate = totale_entrate or 0
        totale_uscite = totale_uscite or 0

    context = {
        'form': form,
        'distinta': distinta,
        'totale_entrate': totale_entrate,
        'totale_uscite': totale_uscite,
        'titolo': 'Chiudi Distinta',
        'conto_cassa': conto_cassa
    }

    return render(request, 'app/chiudi_distinta.html', context)

@login_required
@login_required
@permission_required('app.change_distintacassa', raise_exception=True)
def verifica_distinta(request, pk):
    db = DatabaseManager(request.user)
    distinta = get_object_or_404(db.get_queryset(DistintaCassa), pk=pk)

    if distinta.stato != 'chiusa':
        messages.error(request, 'Questa distinta non può essere verificata.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    if request.method == 'POST':
        form = VerificaDistintaForm(request.POST, instance=distinta)
        if form.is_valid():
            distinta = form.save(commit=False)
            # Use the model's verifica method for consistency
            distinta.verifica(request.user)

            messages.success(request, f'Distinta N° {distinta.pk} verificata con successo!')
            return redirect('lista_distinte')
    else:
        form = VerificaDistintaForm(instance=distinta)

    context = {
        'form': form,
        'distinta': distinta,
        'titolo': 'Verifica Distinta'
    }

    return render(request, 'app/verifica_distinta.html', context)


@login_required
def riapri_distinta(request, pk):
    db = DatabaseManager(request.user)
    distinta = get_object_or_404(db.get_queryset(DistintaCassa), pk=pk)

    # Verifica autorizzazioni
    can_reopen = False

    # L'admin può riaprire qualsiasi distinta
    if is_admin(request.user):
        can_reopen = True
    # L'operatore può riaprire solo le proprie distinte dello stesso giorno
    elif distinta.operatore == request.user and distinta.data == timezone.now().date():
        can_reopen = True

    if not can_reopen:
        messages.error(request, 'Non sei autorizzato a riaprire questa distinta.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    # Verifica che la distinta sia chiusa (non verificata)
    if distinta.stato != 'chiusa':
        messages.error(request, 'Solo le distinte chiuse (non verificate) possono essere riaperte.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    if request.method == 'POST':
        # Riapri la distinta
        distinta.stato = 'aperta'
        distinta.ora_fine = None
        db.save_object(distinta)

        messages.success(request, f'Distinta N° {distinta.pk} riaperta con successo!')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    context = {
        'distinta': distinta,
        'titolo': 'Riapertura Distinta'
    }

    return render(request, 'app/riapri_distinta.html', context)


# Gestione bilancio finanziario
@login_required
def bilancio_finanziario(request):
    # Verifica esplicita dell'autorizzazione
    if not (request.user.is_superuser or request.user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
        messages.error(request, 'Non sei autorizzato ad accedere alla pagina del bilancio.')
        return redirect('dashboard')
    """Vista principale per il bilancio finanziario"""
    
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    
    # Controlla se esistono i conti predefiniti, altrimenti li crea
    if db.get_queryset(ContoFinanziario).count() == 0:
        try:
            ContoFinanziario.crea_conti_default(request.user)
            messages.success(request, 'Conti finanziari predefiniti creati con successo.')
        except Exception as e:
            messages.error(request, f'Errore nella creazione dei conti predefiniti: {str(e)}. Contatta l\'amministratore.')

    # Calcola il saldo attuale dei clienti
    saldo_clienti_movimenti = Cliente.calcola_saldo_complessivo(request.user)

    # Aggiorna il saldo del conto clienti se esiste (invertendo il segno per il bilancio)
    try:
        conto_clienti = db.get_queryset(ContoFinanziario).filter(tipo='clienti').first()
        saldo_clienti_bilancio = -saldo_clienti_movimenti  # Inverto il segno per il bilancio
        if conto_clienti and conto_clienti.saldo != saldo_clienti_bilancio:
            conto_clienti.saldo = saldo_clienti_bilancio
            conto_clienti.modificato_da_id = request.user.id
            db.save_object(conto_clienti)
            messages.info(request, f'Saldo clienti aggiornato automaticamente: {saldo_clienti_bilancio} €')
    except ContoFinanziario.DoesNotExist:
        pass

    # Ottieni tutti i conti finanziari (dopo l'aggiornamento)
    conti = db.get_queryset(ContoFinanziario)

    # Raggruppa i conti per tipo
    conti_per_tipo = {}
    for tipo, nome in ContoFinanziario.TIPO_CHOICES:
        conti_per_tipo[tipo] = conti.filter(tipo=tipo)

    # Ottieni gli ultimi bilanci periodici
    bilanci = db.get_queryset(BilancioPeriodico).all()[:10]

    # Calcola il saldo totale
    saldo_totale = ContoFinanziario.calcola_saldo_totale(request.user)

    # Calcola saldi per tipo
    saldi_per_tipo = {}
    for tipo, nome in ContoFinanziario.TIPO_CHOICES:
        saldi_per_tipo[tipo] = ContoFinanziario.calcola_saldo_per_tipo(request.user, tipo)

    # Calcola nuovamente la differenza (che dovrebbe essere zero dopo l'aggiornamento)
    saldo_clienti_conti = saldi_per_tipo.get('clienti', 0)
    differenza_saldi = saldo_clienti_conti - (-saldo_clienti_movimenti)  # Confronto con il saldo invertito

    # Form per creare un nuovo bilancio
    if request.method == 'POST':
        form_bilancio = BilancioPeriodoForm(request.POST)
        if form_bilancio.is_valid():
            note = form_bilancio.cleaned_data.get('note')
            bilancio = BilancioPeriodico.crea_bilancio(request.user, note)
            messages.success(request, f'Nuovo bilancio creato con successo: {bilancio}')
            return redirect('bilancio_finanziario')
    else:
        form_bilancio = BilancioPeriodoForm()

    context = {
        'conti': conti,
        'conti_per_tipo': conti_per_tipo,
        'bilanci': bilanci,
        'saldo_totale': saldo_totale,
        'saldi_per_tipo': saldi_per_tipo,
        'saldo_clienti_movimenti': saldo_clienti_movimenti,
        'saldo_clienti_conti': saldo_clienti_conti,
        'differenza_saldi': differenza_saldi,
        'form_bilancio': form_bilancio,
    }

    return render(request, 'app/bilancio_finanziario.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def nuovo_conto(request):
    """Crea un nuovo conto finanziario"""
    if request.method == 'POST':
        form = ContoFinanziarioForm(request.POST)
        if form.is_valid():
            conto = form.save(commit=False)
            conto.creato_da_id = request.user.id
            conto.modificato_da_id = request.user.id
            db.save_object(conto)
            messages.success(request, f'Conto "{conto.nome}" creato con successo!')
            return redirect('bilancio_finanziario')
    else:
        form = ContoFinanziarioForm()

    context = {
        'form': form,
        'titolo': 'Nuovo Conto Finanziario'
    }

    return render(request, 'app/form_conto.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def modifica_conto(request, pk):
    """Modifica un conto finanziario esistente"""
    db = DatabaseManager(request.user)
    conto = get_object_or_404(db.get_queryset(ContoFinanziario), pk=pk)

    if request.method == 'POST':
        form = ContoFinanziarioForm(request.POST, instance=conto)
        if form.is_valid():
            conto = form.save(commit=False)
            conto.modificato_da_id = request.user.id
            db.save_object(conto)
            messages.success(request, f'Conto "{conto.nome}" aggiornato con successo!')
            return redirect('bilancio_finanziario')
    else:
        form = ContoFinanziarioForm(instance=conto)

    context = {
        'form': form,
        'conto': conto,
        'titolo': f'Modifica Conto: {conto.nome}'
    }

    return render(request, 'app/form_conto.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def modifica_saldo(request, pk):
    """Modifica il saldo di un conto finanziario"""
    db = DatabaseManager(request.user)
    conto = get_object_or_404(db.get_queryset(ContoFinanziario), pk=pk)

    if request.method == 'POST':
        form = ModificaSaldoForm(request.POST)
        if form.is_valid():
            importo = form.cleaned_data.get('importo')
            operazione = form.cleaned_data.get('operazione')
            note = form.cleaned_data.get('note')

            # Salva il saldo precedente per il registro movimenti
            saldo_precedente = conto.saldo

            # Modifica il saldo in base all'operazione
            if operazione == 'add':
                conto.saldo += importo
                msg_op = f'aggiunto {importo}€ a'
            elif operazione == 'subtract':
                conto.saldo -= importo
                msg_op = f'sottratto {importo}€ da'
            else:  # set
                conto.saldo = importo
                msg_op = f'impostato il saldo di {importo}€ per'

            conto.modificato_da_id = request.user.id
            db.save_object(conto)

            # Registra il movimento nel database
            MovimentoConti.registra_modifica_diretta(
                conto=conto,
                importo_precedente=saldo_precedente,
                importo_nuovo=conto.saldo,
                operatore=request.user,
                note=note
            )

            messages.success(request, f'Hai {msg_op} "{conto.nome}"')
            return redirect('bilancio_finanziario')
    else:
        form = ModificaSaldoForm()

    context = {
        'form': form,
        'conto': conto,
        'titolo': f'Modifica Saldo: {conto.nome} (Saldo attuale: {conto.saldo}€)'
    }

    return render(request, 'app/form_modifica_saldo.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def elimina_conto(request, pk):
    """Elimina un conto finanziario"""
    db = DatabaseManager(request.user)
    conto = get_object_or_404(db.get_queryset(ContoFinanziario), pk=pk)
    
    if request.method == 'POST':
        # Verifica se il conto ha dei movimenti associati
        if conto.movimenti_entrata.exists() or conto.movimenti_uscita.exists():
            messages.error(request, f'Impossibile eliminare "{conto.nome}": il conto ha movimenti associati.')
            return redirect('bilancio_finanziario')
        
        nome_conto = conto.nome
        conto.delete()
        messages.success(request, f'Conto "{nome_conto}" eliminato con successo!')
        return redirect('bilancio_finanziario')
    
    # Conta i movimenti associati
    movimenti_entrata = conto.movimenti_entrata.all()
    movimenti_uscita = conto.movimenti_uscita.all()
    totale_movimenti = movimenti_entrata.count() + movimenti_uscita.count()
    
    context = {
        'conto': conto,
        'titolo': f'Elimina Conto: {conto.nome}',
        'ha_movimenti': totale_movimenti > 0,
        'movimenti_entrata': movimenti_entrata,
        'movimenti_uscita': movimenti_uscita,
        'totale_movimenti': totale_movimenti
    }
    
    return render(request, 'app/elimina_conto.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def dettaglio_bilancio(request, pk):
    """Visualizza i dettagli di un bilancio periodico"""
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    bilancio = db.get_object_or_404(BilancioPeriodico, pk=pk)

    # Verifica se esiste un bilancio precedente per il confronto
    try:
        bilancio_precedente = db.get_queryset(BilancioPeriodico).filter(
            data_riferimento__lt=bilancio.data_riferimento
        ).latest('data_riferimento')

        # Calcola le differenze per ogni tipo di saldo
        differenze = {
            'totale': bilancio.saldo_totale - bilancio_precedente.saldo_totale,
            'clienti': bilancio.saldo_clienti - bilancio_precedente.saldo_clienti,
            'online': bilancio.saldo_online - bilancio_precedente.saldo_online,
            'agenti': bilancio.saldo_agenti - bilancio_precedente.saldo_agenti,
            'cassa': bilancio.saldo_cassa - bilancio_precedente.saldo_cassa,
            'banca': bilancio.saldo_banca - bilancio_precedente.saldo_banca,
            'ricavi': bilancio.saldo_ricavi - bilancio_precedente.saldo_ricavi,
            'spese': bilancio.saldo_spese - bilancio_precedente.saldo_spese,
            'prelievi': bilancio.saldo_prelievi - bilancio_precedente.saldo_prelievi,
            'versamenti': bilancio.saldo_versamenti - bilancio_precedente.saldo_versamenti,
            'altro': bilancio.saldo_altro - bilancio_precedente.saldo_altro,
        }
    except BilancioPeriodico.DoesNotExist:
        bilancio_precedente = None
        differenze = None

    context = {
        'bilancio': bilancio,
        'bilancio_precedente': bilancio_precedente,
        'differenze': differenze,
    }

    return render(request, 'app/dettaglio_bilancio.html', context)


# Visualizzazione logs
@login_required
@user_passes_test(is_manager_or_admin)
def lista_logs(request):
    """Vista per visualizzare i log di attività"""
    from django.contrib.contenttypes.models import ContentType
    
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    logs = db.get_queryset(ActivityLog).all()

    # Filtraggio per tipo di azione
    action = request.GET.get('action', '')
    if action:
        logs = logs.filter(action=action)

    # Filtraggio per utente
    user_id = request.GET.get('user', '')
    if user_id:
        logs = logs.filter(user_id=user_id)

    # Filtraggio per tipo di contenuto (Movimento o DistintaCassa)
    content_type = request.GET.get('content_type', '')
    if content_type:
        content_type_id = ContentType.objects.get(model=content_type.lower()).id
        logs = logs.filter(content_type_id=content_type_id)

    # Filtraggio per oggetto specifico
    object_id = request.GET.get('object_id', '')
    if object_id:
        logs = logs.filter(object_id=object_id)

    # Filtraggio per data
    data_inizio = request.GET.get('data_inizio', '')
    if data_inizio:
        logs = logs.filter(timestamp__date__gte=data_inizio)

    data_fine = request.GET.get('data_fine', '')
    if data_fine:
        logs = logs.filter(timestamp__date__lte=data_fine)

    # Ordinamento per timestamp (dal più recente)
    logs = logs.order_by('-timestamp')

    # Paginazione
    paginator = Paginator(logs, 20)  # 20 log per pagina
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Lista di utenti per il filtro - forza valutazione per evitare cross-database query
    user_ids = list(db.get_queryset(ActivityLog).values_list('user_id', flat=True).distinct())
    users = User.objects.filter(id__in=user_ids)

    # Lista di tipi di contenuto per il filtro
    # Forza la valutazione della query per evitare subquery cross-database
    content_type_ids = list(db.get_queryset(ActivityLog).values_list('content_type_id', flat=True).distinct())
    content_types = ContentType.objects.filter(id__in=content_type_ids)

    context = {
        'page_obj': page_obj,
        'action_selected': action,
        'user_selected': user_id,
        'content_type_selected': content_type,
        'object_id_selected': object_id,
        'data_inizio': data_inizio,
        'data_fine': data_fine,
        'users': users,
        'content_types': content_types,
        'action_choices': ActivityLog.ACTION_CHOICES,
    }

    return render(request, 'app/lista_logs.html', context)


# Visualizzazione dettaglio log
@login_required
@user_passes_test(is_manager_or_admin)
def dettaglio_log(request, pk):
    """Vista per visualizzare il dettaglio di un log"""
    db = DatabaseManager(request.user)
    log = get_object_or_404(db.get_queryset(ActivityLog), pk=pk)

    # Formatta i dati JSON per una migliore visualizzazione
    import json
    from django.utils.safestring import mark_safe

    # Formatta i dati JSON in maniera leggibile
    if log.data_before:
        try:
            formatted_data = json.dumps(log.data_before, indent=4, ensure_ascii=False)
            log.data_before_formatted = mark_safe(formatted_data)
        except Exception:
            log.data_before_formatted = mark_safe(str(log.data_before))

    if log.data_after:
        try:
            formatted_data = json.dumps(log.data_after, indent=4, ensure_ascii=False)
            log.data_after_formatted = mark_safe(formatted_data)
        except Exception:
            log.data_after_formatted = mark_safe(str(log.data_after))

    context = {
        'log': log,
    }

    return render(request, 'app/dettaglio_log.html', context)


# API per interazioni AJAX
@login_required
def get_movimenti_cliente(request):
    """API per ottenere i movimenti non saldati di un cliente specifico"""
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    
    cliente_id = request.GET.get('cliente_id')

    if not cliente_id:
        return JsonResponse({'error': 'Cliente non specificato'}, status=400)

    try:
        cliente = db.get_queryset(Cliente).get(pk=cliente_id)
        movimenti = db.get_queryset(Movimento).filter(
            cliente=cliente,
            saldato=False
        ).order_by('-data')

        # Prepara i dati per la risposta JSON
        data = {
            'cliente': {
                'id': cliente.id,
                'nome_completo': cliente.nome_completo,
                'saldo': str(cliente.saldo),
                'fido_massimo': str(cliente.fido_massimo),
                'saldo_disponibile': str(cliente.saldo_disponibile),
            },
            'movimenti': []
        }

        for movimento in movimenti:
            data['movimenti'].append({
                'id': movimento.id,
                'tipo': movimento.get_tipo_display(),
                'importo': str(abs(movimento.importo)),
                'data': timezone.localtime(movimento.data).strftime('%d/%m/%Y %H:%M'),
                'distinta_id': movimento.distinta.id,
            })

        return JsonResponse(data)

    except Cliente.DoesNotExist:
        return JsonResponse({'error': 'Cliente non trovato'}, status=404)


@login_required
@user_passes_test(is_manager_or_admin)
def effettua_giroconto(request):
    """Effettua un giroconto tra due conti finanziari"""
    if request.method == 'POST':
        form = GirocontoForm(request.POST, user=request.user)
        if form.is_valid():
            conto_origine = form.cleaned_data.get('conto_origine')
            conto_destinazione = form.cleaned_data.get('conto_destinazione')
            importo = form.cleaned_data.get('importo')
            note = form.cleaned_data.get('note')

            try:
                # Effettua il giroconto
                movimento = MovimentoConti.registra_giroconto(
                    conto_origine=conto_origine,
                    conto_destinazione=conto_destinazione,
                    importo=importo,
                    operatore=request.user,
                    note=note
                )

                messages.success(
                    request,
                    f'Giroconto di {importo}€ effettuato con successo da "{conto_origine.nome}" a "{conto_destinazione.nome}"'
                )
                return redirect('bilancio_finanziario')
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('effettua_giroconto')
    else:
        form = GirocontoForm(user=request.user)

    context = {
        'form': form,
        'titolo': 'Effettua Giroconto',
    }

    return render(request, 'app/form_giroconto.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def lista_movimenti_conti(request):
    """Visualizza la lista dei movimenti tra conti"""
    # Usa il nuovo DatabaseManager
    db = DatabaseManager(request.user)
    movimenti = db.get_queryset(MovimentoConti)

    # Filtraggio per tipo di movimento
    tipo = request.GET.get('tipo', '')
    if tipo:
        movimenti = movimenti.filter(tipo=tipo)

    # Filtraggio per conto
    conto_id = request.GET.get('conto', '')
    if conto_id:
        movimenti = movimenti.filter(
            Q(conto_origine_id=conto_id) | Q(conto_destinazione_id=conto_id)
        )

    # Filtraggio per data
    data_inizio = request.GET.get('data_inizio', '')
    if data_inizio:
        movimenti = movimenti.filter(data__date__gte=data_inizio)

    data_fine = request.GET.get('data_fine', '')
    if data_fine:
        movimenti = movimenti.filter(data__date__lte=data_fine)

    # Paginazione
    paginator = Paginator(movimenti, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Lista dei conti per il filtro
    conti = db.get_queryset(ContoFinanziario)

    context = {
        'page_obj': page_obj,
        'conti': conti,
        'tipo_selezionato': tipo,
        'conto_selezionato': conto_id,
        'data_inizio': data_inizio,
        'data_fine': data_fine,
        'tipi_movimento': MovimentoConti.TIPO_CHOICES,
    }

    return render(request, 'app/lista_movimenti_conti.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def elimina_movimento_conti(request, pk):
    """Elimina un movimento tra conti"""
    db = DatabaseManager(request.user)
    movimento = get_object_or_404(db.get_queryset(MovimentoConti), pk=pk)
    
    if request.method == 'POST':
        # Il metodo delete del modello si occuperà di ripristinare i saldi
        movimento.delete(user=request.user)
        messages.success(request, f'Movimento eliminato con successo!')
        return redirect('lista_movimenti_conti')
    
    context = {
        'movimento': movimento,
        'titolo': f'Elimina Movimento: {movimento}'
    }

    return render(request, 'app/elimina_movimento_conti.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def riepilogo_crediti(request):
    """Tabella riepilogativa per data: crediti clienti, cassa finale, bevande, differenza distinta"""
    db = DatabaseManager(request.user)
    alias = db.user_db

    # 1) Tutte le distinte (campi minimi) in UNA query, aggregate in Python per giorno:
    #    somma bevande/differenza e cassa finale (ultima distinta del giorno per ora_inizio).
    per_giorno = {}
    distinte = (db.get_queryset(DistintaCassa)
                .values('data', 'cassa_finale', 'totale_bevande', 'differenza_cassa')
                .order_by('data', 'ora_inizio'))
    for d in distinte:
        info = per_giorno.setdefault(
            d['data'],
            {'bevande': Decimal('0'), 'diff': Decimal('0'), 'cassa_finale': None}
        )
        info['bevande'] += d['totale_bevande'] or Decimal('0')
        info['diff'] += d['differenza_cassa'] or Decimal('0')
        # le distinte sono ordinate per ora_inizio crescente: l'ultima vista è quella più tarda
        info['cassa_finale'] = d['cassa_finale']

    # 2) Crediti per giorno = saldo_progressivo dell'ultimo movimento del giorno.
    #    Una sola query indicizzata su (data, id): scorrendo in ordine crescente,
    #    l'ultimo valore scritto per ciascun giorno è quello dell'ultimo movimento.
    #    NB: si ricalcola la progressione escludendo i conti di servizio (POS, spese,
    #    aggiustamenti), che non sono crediti clienti. Non si usa saldo_progressivo
    #    (catena globale che li include).
    crediti_map = {}
    servizio_map = {}
    corr = Decimal('0')
    corr_serv = Decimal('0')
    for m in (Movimento.objects.using(alias)
              .values('data', 'importo', 'cliente__conto_servizio')
              .order_by('data', 'id')):
        if m['cliente__conto_servizio']:
            corr_serv += m['importo']
        else:
            corr += m['importo']
        giorno = timezone.localtime(m['data']).date()
        crediti_map[giorno] = corr
        servizio_map[giorno] = corr_serv

    # 2b) Valori esterni per giorno e per tipo, dal DB default per l'agenzia corrente
    from .models import SaldoEsterno, Agenzia
    esterni = {}  # tipo -> {data: valore}
    agenzia = Agenzia.objects.using('default').filter(database_name=alias).first()
    if agenzia:
        for s in (SaldoEsterno.objects.using('default')
                  .filter(agenzia=agenzia).values('tipo', 'data', 'saldo')):
            esterni.setdefault(s['tipo'], {})[s['data']] = s['saldo']

    def ext(tipo, giorno):
        return esterni.get(tipo, {}).get(giorno)

    # 3) Costruisce le righe ordinate per data decrescente, con Totale e Differenza
    def num(x):
        return x if x is not None else Decimal('0')

    righe = []
    for giorno, info in sorted(per_giorno.items(), reverse=True):
        r = {
            'data': giorno,
            'crediti': crediti_map.get(giorno),
            'conti_servizio': servizio_map.get(giorno),
            'cassa_finale': info['cassa_finale'],
            'saldo_bevande': info['bevande'],
            'differenza_distinta': info['diff'],
            'saldo_cast': ext('cast_agent', giorno),
            'giroconto_online': ext('giroconto_online', giorno),
            'giroconto_terrestre': ext('giroconto_terrestre', giorno),
            'saldo_online': ext('saldo_online', giorno),
            'prelievi': ext('prelievi', giorno),
            'versamenti': ext('versamenti', giorno),
            'altro': ext('altro', giorno),
            'giroconto_conti_servizio': ext('giroconto_conti_servizio', giorno),
        }
        # Totale (quadratura giornaliera):
        # -crediti + cassa finale + saldo online + saldo ced - bevande
        # - differenza distinta - giroconto online - giroconto terrestre + prelievi - versamenti + altro
        r['totale'] = (
            -num(r['crediti']) - num(r['conti_servizio'])
            + num(r['cassa_finale']) + num(r['saldo_online'])
            + num(r['saldo_cast']) - num(r['saldo_bevande']) - num(r['differenza_distinta'])
            - num(r['giroconto_online']) - num(r['giroconto_terrestre'])
            - num(r['giroconto_conti_servizio'])
            + num(r['prelievi']) - num(r['versamenti']) + num(r['altro'])
        )
        righe.append(r)

    # Differenza rispetto al giorno precedente (riga successiva in ordine decrescente):
    # -(totale_ieri - totale_oggi + bevande_ieri + diff_distinta_ieri + giroconti_ieri
    #   + versamenti_ieri - prelievi_ieri)
    # = totale_oggi - totale_ieri - bevande_ieri - diff_distinta_ieri
    #   - giroconto_online_ieri - giroconto_terrestre_ieri - versamenti_ieri + prelievi_ieri
    for i, r in enumerate(righe):
        if i + 1 < len(righe):
            y = righe[i + 1]  # ieri
            r['differenza'] = (
                r['totale'] - y['totale']
                - num(y['saldo_bevande']) - num(y['differenza_distinta'])
                - num(y['giroconto_online']) - num(y['giroconto_terrestre'])
                - num(y['giroconto_conti_servizio'])
                - num(y['versamenti']) + num(y['prelievi']) + num(y['altro'])
            )
            # Differenza reale = differenza depurata dalla differenza distinta del giorno
            r['differenza_reale'] = r['differenza'] + num(r['differenza_distinta'])
        else:
            r['differenza'] = None
            r['differenza_reale'] = None

    context = {'righe': righe}
    return render(request, 'app/riepilogo_crediti.html', context)


# ===== ESTRAZIONE SALDI DA PORTALI ESTERNI (CAST Agent) =====

@login_required
@user_passes_test(is_manager_or_admin)
def estrazione_saldi(request):
    """
    Pagina per rilevare i saldi dal portale CAST Agent.
    L'operatore inserisce utente, password e il codice CAPTCHA mostrato in
    pagina; il sistema esegue l'accesso e registra il saldo. Le credenziali
    non vengono salvate. E' possibile anche l'inserimento manuale per i
    giorni mancanti.
    """
    from datetime import timedelta
    from . import cast_agent
    from .models import SaldoEsterno

    # Agenzia dell'operatore (i saldi esterni sono per agenzia, sul DB default)
    try:
        agenzia = request.user.profiloutente.agenzia
    except Exception:
        agenzia = None
    if not agenzia:
        messages.error(request, 'Il tuo utente non è associato ad alcuna agenzia.')
        return redirect('home')

    diagnostica = None

    tipi_validi = {t for t, _ in SaldoEsterno.TIPO_CHOICES}

    if request.method == 'POST' and request.POST.get('azione') == 'reset_conto_cast':
        agenzia.cast_account_id = ''
        agenzia.save(using='default')
        messages.info(request, 'Conto CAST associato azzerato: la prossima estrazione lo riassocerà automaticamente.')
        return redirect('estrazione_saldi')

    if request.method == 'POST' and request.POST.get('azione') == 'manuale':
        # Inserimento/correzione manuale di un giorno per un tipo
        data_str = request.POST.get('data_manuale', '')
        saldo_str = (request.POST.get('saldo_manuale', '') or '').replace(',', '.')
        tipo_manuale = request.POST.get('tipo_manuale', 'cast_agent')
        if tipo_manuale not in tipi_validi:
            tipo_manuale = 'cast_agent'
        try:
            from datetime import date as _date
            data_manuale = _date.fromisoformat(data_str)
            saldo_manuale = Decimal(saldo_str)
            SaldoEsterno.objects.using('default').update_or_create(
                agenzia=agenzia, tipo=tipo_manuale, data=data_manuale,
                defaults={'saldo': saldo_manuale}
            )
            etichetta = dict(SaldoEsterno.TIPO_CHOICES).get(tipo_manuale, tipo_manuale)
            messages.success(request, f'{etichetta} del {data_manuale.strftime("%d/%m/%Y")} salvato: {saldo_manuale} €')
            return redirect('estrazione_saldi')
        except Exception:
            messages.error(request, 'Data o importo non validi per l\'inserimento manuale.')

    # Saldi registrati di recente e giorni mancanti (ultimi 30 giorni)
    oggi = timezone.localdate()
    saldi_recenti = list(
        SaldoEsterno.objects.using('default')
        .filter(agenzia=agenzia)
        .order_by('-data', 'tipo')[:25]
    )
    presenti = set(
        SaldoEsterno.objects.using('default')
        .filter(agenzia=agenzia, tipo='cast_agent', data__gte=oggi - timedelta(days=30))
        .values_list('data', flat=True)
    )
    giorni_mancanti = [
        oggi - timedelta(days=i) for i in range(0, 31)
        if (oggi - timedelta(days=i)) not in presenti
    ]

    context = {
        'titolo': 'Estrazione Saldi CAST',
        'agenzia': agenzia,
        'diagnostica': diagnostica,
        'saldi_recenti': saldi_recenti,
        'giorni_mancanti': giorni_mancanti,
        'token_estrazione': estrazione_token(agenzia),
        'tipi_saldo': SaldoEsterno.TIPO_CHOICES,
    }
    return render(request, 'app/estrazione_saldi.html', context)


# ----- Estrazione dal browser dell'operatore (bookmarklet) -----
# Il portale CAST è raggiungibile solo da IP italiani, quindi l'estrazione la fa
# il browser dell'operatore (già loggato al portale) e invia i saldi al gestionale.

def estrazione_token(agenzia):
    """Token per-agenzia (derivato dalla SECRET_KEY) che autorizza l'invio dei saldi dal browser."""
    import hashlib
    import hmac
    from django.conf import settings
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f'cast-estrazione-{agenzia.pk}'.encode(),
        hashlib.sha256
    ).hexdigest()[:32]


def _cors(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def _agenzia_da_token(token):
    from .models import Agenzia
    if not token:
        return None
    for agenzia in Agenzia.objects.using('default').all():
        if estrazione_token(agenzia) == token:
            return agenzia
    return None


def api_giorni_mancanti(request):
    """Giorni da estrarre (mancanti ultimi 30 + oggi). Autenticazione via token."""
    from datetime import timedelta
    from .models import SaldoEsterno

    agenzia = _agenzia_da_token(request.GET.get('token'))
    if not agenzia:
        return _cors(JsonResponse({'errore': 'token non valido'}, status=403))

    # Numero di giorni indietro da coprire (default 30, max 400)
    try:
        ngiorni = int(request.GET.get('giorni', 30))
    except (TypeError, ValueError):
        ngiorni = 30
    ngiorni = max(1, min(ngiorni, 400))
    # forza=1: ri-estrae TUTTI i giorni del periodo (per riscrivere valori sbagliati),
    # non solo quelli mancanti.
    forza = str(request.GET.get('forza', '')).lower() in ('1', 'true', 'si', 'yes')

    oggi = timezone.localdate()
    tutti = sorted({oggi - timedelta(days=i) for i in range(0, ngiorni + 1)})
    if forza:
        giorni = tutti
    else:
        presenti = set(
            SaldoEsterno.objects.using('default')
            .filter(agenzia=agenzia, tipo='cast_agent', data__gte=oggi - timedelta(days=ngiorni))
            .values_list('data', flat=True)
        )
        # Oggi viene sempre incluso (può cambiare in giornata); gli altri solo se mancanti.
        giorni = [g for g in tutti if g == oggi or g not in presenti]
    inizio = oggi - timedelta(days=ngiorni)
    return _cors(JsonResponse({
        'giorni': [g.isoformat() for g in giorni],
        'range': {'inizio': inizio.isoformat(), 'fine': oggi.isoformat()},
    }))


@csrf_exempt
def api_ricevi_saldi(request):
    """Riceve i saldi estratti dal browser (bookmarklet) e li registra. Token per autenticazione."""
    import json as _json
    from datetime import date as _date
    from .models import SaldoEsterno

    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    if request.method != 'POST':
        return _cors(JsonResponse({'errore': 'solo POST'}, status=405))

    try:
        corpo = _json.loads(request.body.decode('utf-8'))
    except Exception:
        return _cors(JsonResponse({'errore': 'payload non valido'}, status=400))

    agenzia = _agenzia_da_token(corpo.get('token'))
    if not agenzia:
        return _cors(JsonResponse({'errore': 'token non valido'}, status=403))

    tipi_validi = {t for t, _ in SaldoEsterno.TIPO_CHOICES}
    # Payload: {'dati': {tipo: {isodate: valore}}}. Compat: 'saldi' -> cast_agent.
    dati = dict(corpo.get('dati') or {})
    if corpo.get('saldi'):
        dati.setdefault('cast_agent', {}).update(corpo['saldi'])

    # Anti-contaminazione tra agenzie: il conto CAST deve corrispondere a quello
    # associato all'agenzia (impostato alla prima estrazione). Impedisce che un
    # bookmarklet con token di un'agenzia scriva i saldi CAST di un'altra.
    cast_tipi = {'cast_agent', 'giroconto_online', 'giroconto_terrestre'}
    has_cast = any(t in dati for t in cast_tipi)
    conto_cast = (str(corpo.get('conto_cast') or '')).strip()
    if has_cast:
        associato = (agenzia.cast_account_id or '').strip()
        if associato:
            if conto_cast != associato:
                return _cors(JsonResponse({
                    'errore': f'Conto CAST non corrispondente a questa agenzia ({agenzia.nome}). '
                              f'Atteso il conto associato, ricevuto "{conto_cast or "sconosciuto"}". '
                              f'Verifica di essere sulla pagina CAST giusta, oppure svuota il conto CAST associato in Agenzia per riassociarlo.',
                    'conto_atteso': associato, 'conto_ricevuto': conto_cast,
                }, status=409))
        elif conto_cast:
            # Prima estrazione: associa il conto CAST all'agenzia.
            agenzia.cast_account_id = conto_cast
            agenzia.save(using='default')

    salvati = 0
    scartati = []
    for tipo, valori in dati.items():
        if tipo not in tipi_validi:
            continue
        for data_str, valore in (valori or {}).items():
            try:
                giorno = _date.fromisoformat(data_str)
                saldo = Decimal(str(valore).replace(',', '.')).quantize(Decimal('0.01'))
            except Exception:
                scartati.append(f'{tipo}:{data_str}')
                continue
            SaldoEsterno.objects.using('default').update_or_create(
                agenzia=agenzia, tipo=tipo, data=giorno,
                defaults={'saldo': saldo}
            )
            salvati += 1

    return _cors(JsonResponse({'salvati': salvati, 'scartati': scartati,
                               'conto_cast': (agenzia.cast_account_id or '')}))


@login_required
@user_passes_test(is_manager_or_admin)
def salva_valore_esterno(request):
    """Salva/aggiorna un singolo valore esterno (editing inline dal riepilogo crediti)."""
    from datetime import date as _date
    from .models import SaldoEsterno

    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        agenzia = request.user.profiloutente.agenzia
    except Exception:
        agenzia = None
    if not agenzia:
        return JsonResponse({'ok': False, 'errore': 'Nessuna agenzia associata'}, status=400)

    tipo = request.POST.get('tipo')
    if tipo not in {t for t, _ in SaldoEsterno.TIPO_CHOICES}:
        return JsonResponse({'ok': False, 'errore': 'tipo non valido'}, status=400)
    try:
        giorno = _date.fromisoformat(request.POST.get('data', ''))
    except Exception:
        return JsonResponse({'ok': False, 'errore': 'data non valida'}, status=400)

    valore_str = (request.POST.get('valore', '') or '').strip().replace(',', '.')
    if valore_str == '':
        # Valore svuotato: rimuovi la registrazione
        SaldoEsterno.objects.using('default').filter(
            agenzia=agenzia, tipo=tipo, data=giorno
        ).delete()
        return JsonResponse({'ok': True, 'vuoto': True})
    try:
        valore = Decimal(valore_str).quantize(Decimal('0.01'))
    except Exception:
        return JsonResponse({'ok': False, 'errore': 'valore non valido'}, status=400)

    SaldoEsterno.objects.using('default').update_or_create(
        agenzia=agenzia, tipo=tipo, data=giorno, defaults={'saldo': valore}
    )
    return JsonResponse({'ok': True})


def _calcola_piano_azzeramento(db, checked_ids):
    """Ricostruisce lo stato corrente dei conti di servizio e il piano di azzeramento
    per i movimenti selezionati. Ritorna (piano, is_full)."""
    from django.db.models import Sum
    checked_ids = set(int(x) for x in checked_ids)

    conti = []
    for c in db.get_queryset(Cliente).filter(conto_servizio=True).order_by('cognome', 'nome'):
        movimenti = list(db.get_queryset(Movimento).filter(cliente=c, saldato=False).order_by('-data'))
        cumulativo = db.get_queryset(Movimento).filter(cliente=c).aggregate(t=Sum('importo'))['t'] or Decimal('0')
        if cumulativo == 0 and not movimenti:
            continue
        conti.append({'cliente': c, 'movimenti': movimenti, 'cumulativo': cumulativo})

    tutte_open = [m for info in conti for m in info['movimenti']]
    total_open = len(tutte_open)
    total_checked = sum(1 for m in tutte_open if m.pk in checked_ids)
    is_full = (total_checked == total_open)

    piano = []
    for info in conti:
        cliente = info['cliente']
        open_movs = info['movimenti']
        cumulativo = info['cumulativo']
        sel = [m for m in open_movs if m.pk in checked_ids]
        if open_movs:
            if not sel:
                continue  # niente spuntato: il conto resta aperto
            if len(sel) == len(open_movs):
                piano.append({'cliente': cliente, 'ids': [m.pk for m in open_movs], 'importo': cumulativo})
            else:
                s = sum((m.importo for m in sel), Decimal('0'))
                piano.append({'cliente': cliente, 'ids': [m.pk for m in sel], 'importo': s})
        elif is_full and cumulativo != 0:
            piano.append({'cliente': cliente, 'ids': [], 'importo': cumulativo})
    return piano, is_full


def _esegui_azzeramento(db, operatore, checked_ids):
    """Esegue l'azzeramento dei conti di servizio per i movimenti selezionati.

    Ricalcola il piano dallo stato corrente (i movimenti possono essere cambiati), crea
    la distinta di azzeramento neutra sulla cassa, salda i movimenti selezionati, aggiunge
    le compensazioni e registra il giroconto conti di servizio. Ritorna un dict riassuntivo
    oppure None se non c'è nulla da azzerare.
    """
    from django.db import transaction
    from .models import SaldoEsterno, Agenzia

    alias = db.user_db
    piano, is_full = _calcola_piano_azzeramento(db, checked_ids)
    if not piano:
        return None

    # Cassa finale da riportare (per non alterare la colonna Cassa Finale del riepilogo)
    ultima = db.get_queryset(DistintaCassa).order_by('-data', '-ora_inizio').first()
    if ultima and ultima.cassa_finale is not None:
        cassa_carry = ultima.cassa_finale
    else:
        conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
        cassa_carry = conto_cassa.saldo if conto_cassa else Decimal('0')

    totale_azzerato = Decimal('0')
    n_conti = 0
    n_movimenti = 0

    with transaction.atomic(using=alias):
        ora = timezone.localtime(timezone.now()).time()
        reset_dist = DistintaCassa(
            operatore=operatore, data=timezone.localdate(),
            ora_inizio=ora, ora_fine=ora,
            cassa_iniziale=cassa_carry, cassa_finale=cassa_carry,
            totale_entrate=Decimal('0'), totale_uscite=Decimal('0'), totale_bevande=Decimal('0'),
            differenza_cassa=Decimal('0'), stato='verificata',
            verificata_da=operatore, data_verifica=timezone.now(),
            note_distinta='Azzeramento conti di servizio',
        )
        db.save_object(reset_dist)

        for p in piano:
            cliente = p['cliente']
            imp = p['importo']
            # 1) marca come saldati i soli movimenti selezionati
            if p['ids']:
                db.get_queryset(Movimento).filter(pk__in=p['ids']).update(saldato=True)
                n_movimenti += len(p['ids'])
            # 2) movimento di compensazione che riduce la progressione dell'importo saldato
            if imp != 0:
                tipo_comp = 'pagamento_debito' if imp > 0 else 'incasso_credito'
                comp = Movimento(
                    cliente=cliente, tipo=tipo_comp, importo=abs(imp),
                    distinta=reset_dist, creato_da_id=operatore.id,
                    saldato=True, note='Azzeramento conto di servizio',
                )
                db.save_object(comp)
            cliente.aggiorna_saldo(user=operatore)
            totale_azzerato += imp
            n_conti += 1

    # 3) registra l'importo azzerato nella voce giroconto conti di servizio (oggi)
    agenzia = Agenzia.objects.using('default').filter(database_name=alias).first()
    if agenzia and totale_azzerato != 0:
        oggi = timezone.localdate()
        esistente = SaldoEsterno.objects.using('default').filter(
            agenzia=agenzia, tipo='giroconto_conti_servizio', data=oggi
        ).first()
        nuovo = (esistente.saldo if esistente else Decimal('0')) + totale_azzerato
        SaldoEsterno.objects.using('default').update_or_create(
            agenzia=agenzia, tipo='giroconto_conti_servizio', data=oggi,
            defaults={'saldo': nuovo}
        )

    return {'n_movimenti': n_movimenti, 'n_conti': n_conti, 'totale': totale_azzerato,
            'reset_dist': reset_dist, 'is_full': is_full}


def esegui_azzeramento_programmato_se_possibile(db, request=None):
    """Se non ci sono distinte aperte ed esiste un azzeramento programmato in attesa,
    lo esegue (con claim atomico anti-doppia-esecuzione). Da chiamare dopo la chiusura
    di una distinta. Non solleva eccezioni verso il chiamante."""
    try:
        if db.get_queryset(DistintaCassa).filter(stato='aperta').exists():
            return
        pend = db.get_queryset(AzzeramentoProgrammato).filter(stato='in_attesa').order_by('data_richiesta').first()
        if not pend:
            return
        # Claim atomico: solo un chiamante passa da 'in_attesa' a 'in_esecuzione'
        claimed = db.get_queryset(AzzeramentoProgrammato).filter(
            pk=pend.pk, stato='in_attesa'
        ).update(stato='in_esecuzione')
        if claimed != 1:
            return
        pend.refresh_from_db(using=db.user_db)
        try:
            # L'operatore va caricato dal DB 'default' (dove vive il ProfiloUtente), altrimenti
            # DatabaseManager(operatore) non risolve l'agenzia e ricadrebbe su 'default'.
            from django.contrib.auth.models import User
            operatore = User.objects.using('default').get(pk=pend.operatore_id)
            ids = [x.strip() for x in (pend.movimento_ids or '').split(',') if x.strip()]
            res = _esegui_azzeramento(db, operatore, ids)
            pend.stato = 'eseguito'
            pend.data_esecuzione = timezone.now()
            if res:
                pend.note = f"{res['n_movimenti']} movimenti su {res['n_conti']} conti, totale {res['totale']:.2f} € (distinta #{res['reset_dist'].pk})"
            else:
                pend.note = 'Nessun movimento da azzerare al momento dell\'esecuzione.'
            db.save_object(pend)
            if request is not None and res:
                messages.info(request, f"Azzeramento programmato eseguito automaticamente: {res['n_movimenti']} movimenti su {res['n_conti']} conti (totale {res['totale']:.2f} €). Distinta di azzeramento #{res['reset_dist'].pk} creata.")
            # Notifica Telegram all'agenzia
            if res:
                try:
                    telegram_utils.notifica(
                        db.user_db,
                        f"🧹 Azzeramento conti di servizio eseguito\nMovimenti: {res['n_movimenti']} · Conti: {res['n_conti']}\nTotale: {res['totale']:.2f} €\nDistinta di azzeramento #{res['reset_dist'].pk}\nRichiesto da: {operatore.username}"
                    )
                except Exception:
                    pass
        except Exception as e:
            pend.stato = 'errore'
            pend.note = f'Errore in esecuzione: {e}'
            db.save_object(pend)
            if request is not None:
                messages.error(request, f'Azzeramento programmato non riuscito: {e}')
    except Exception:
        # Non bloccare mai la chiusura della distinta per un problema qui.
        pass


@login_required
@user_passes_test(is_manager_or_admin)
def azzeramento_conti_servizio(request):
    """
    Pagina di controllo e azzeramento dei conti di servizio.
    GET: elenca ogni conto di servizio con i suoi movimenti aperti (da verificare/spuntare).
    POST: se non ci sono distinte aperte esegue subito; altrimenti programma l'azzeramento
    che verrà eseguito automaticamente alla chiusura dell'ultima distinta aperta.
    """
    from django.db.models import Sum

    db = DatabaseManager(request.user)

    def dati_conti():
        conti = []
        for c in db.get_queryset(Cliente).filter(conto_servizio=True).order_by('cognome', 'nome'):
            movimenti = list(db.get_queryset(Movimento)
                             .filter(cliente=c, saldato=False)
                             .select_related('creato_da', 'distinta')
                             .order_by('-data'))
            cumulativo = db.get_queryset(Movimento).filter(cliente=c).aggregate(t=Sum('importo'))['t'] or Decimal('0')
            if cumulativo == 0 and not movimenti:
                continue
            conti.append({'cliente': c, 'movimenti': movimenti, 'saldo': c.saldo, 'cumulativo': cumulativo})
        return conti

    if request.method == 'POST':
        # Annulla un azzeramento programmato in attesa
        if request.POST.get('azione') == 'annulla_programmato':
            db.get_queryset(AzzeramentoProgrammato).filter(stato='in_attesa').update(stato='annullato')
            messages.info(request, 'Azzeramento programmato annullato.')
            return redirect('azzeramento_conti_servizio')

        if not dati_conti():
            messages.info(request, 'Nessun conto di servizio da azzerare.')
            return redirect('riepilogo_crediti')

        # Movimenti spuntati (azzeramento parziale): solo questi vengono saldati.
        # Gli ID arrivano in un unico campo separato da virgole per non superare il
        # limite DATA_UPLOAD_MAX_NUMBER_FIELDS quando i movimenti sono molte migliaia.
        checked_ids = [x.strip() for x in request.POST.get('mov_ids', '').split(',') if x.strip()]

        piano, is_full = _calcola_piano_azzeramento(db, checked_ids)
        if not piano:
            messages.warning(request, 'Nessun movimento selezionato: spunta i movimenti da azzerare.')
            return redirect('azzeramento_conti_servizio')

        # Se c'è QUALSIASI distinta aperta, l'azzeramento va differito: il carry di cassa
        # non è affidabile finché c'è contante "fuori" in un turno aperto.
        distinte_aperte = list(db.get_queryset(DistintaCassa).filter(stato='aperta'))
        if distinte_aperte:
            # Una sola richiesta attiva per volta: sostituisce l'eventuale precedente.
            db.get_queryset(AzzeramentoProgrammato).filter(stato='in_attesa').update(stato='annullato')
            pend = AzzeramentoProgrammato(
                operatore=request.user,
                movimento_ids=','.join(checked_ids),
                stato='in_attesa',
            )
            db.save_object(pend)
            operatori = ', '.join(sorted({d.operatore.username for d in distinte_aperte}))
            messages.info(request, f'Ci sono distinte aperte ({operatori}): azzeramento PROGRAMMATO. Verrà eseguito automaticamente alla chiusura dell\'ultima distinta aperta.')
            return redirect('azzeramento_conti_servizio')

        # Nessuna distinta aperta: esecuzione immediata (comportamento invariato).
        res = _esegui_azzeramento(db, request.user, checked_ids)
        if not res:
            messages.warning(request, 'Nessun movimento selezionato: spunta i movimenti da azzerare.')
            return redirect('azzeramento_conti_servizio')
        parziale = '' if res['is_full'] else ' (parziale)'
        messages.success(request, f"Azzerati {res['n_movimenti']} movimenti su {res['n_conti']} conti{parziale} (totale {res['totale']:.2f} €). Distinta di azzeramento #{res['reset_dist'].pk} creata.")
        return redirect('riepilogo_crediti')

    conti = dati_conti()
    totale = sum((x['cumulativo'] for x in conti), Decimal('0'))
    pending = db.get_queryset(AzzeramentoProgrammato).filter(stato='in_attesa').order_by('-data_richiesta').first()
    distinte_aperte = list(db.get_queryset(DistintaCassa).filter(stato='aperta').order_by('ora_inizio'))
    context = {
        'titolo': 'Azzeramento Conti di Servizio',
        'conti': conti,
        'totale': totale,
        'n_movimenti': sum(len(x['movimenti']) for x in conti),
        'pending': pending,
        'distinte_aperte': distinte_aperte,
    }
    return render(request, 'app/azzeramento_conti_servizio.html', context)
