from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.db.models import Sum, Q, F
from django.core.paginator import Paginator
from decimal import Decimal

from .models import (
    Cliente, Movimento, DistintaCassa, Comunicazione,
    ContoFinanziario, BilancioPeriodico, MovimentoConti, ActivityLog
)
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

# Dashboard (accesso ristretto)
@login_required
def dashboard(request):
    # Verifica esplicita dell'accesso: solo Manager e Amministratore possono accedere
    if not (request.user.is_superuser or
            request.user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
        messages.error(request, 'Non sei autorizzato ad accedere alla dashboard.')
        return redirect('home')
    
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    
    # Assicuriamoci che tutti i saldi siano aggiornati
    for cliente in Cliente.objects.using(user_db).all():
        cliente.aggiorna_saldo(using=user_db)

    # Recupera i clienti con fido superato (saldo negativo che supera il fido massimo in valore assoluto)
    clienti_fido_superato = Cliente.objects.using(user_db).filter(saldo__lt=0).filter(saldo__lt=-F('fido_massimo'))

    # Recupera i clienti con saldo negativo in ritardo da più di 3 giorni
    from datetime import timedelta
    data_limite = timezone.now() - timedelta(days=3)
    
    clienti_in_ritardo = []
    for cliente in Cliente.objects.filter(saldo__lt=0):
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
    distinte_da_verificare = DistintaCassa.objects.filter(stato='chiusa')

    # Recupera statistiche generali
    totale_clienti = Cliente.objects.count()
    saldo_complessivo = Cliente.calcola_saldo_complessivo()
    
    # Aggiorna automaticamente il saldo della cassa dalle distinte e recupera il valore
    try:
        # Prima aggiorna il saldo della cassa basandosi sulle distinte verificate
        ContoFinanziario.aggiorna_saldo_cassa_da_distinte()
        
        # Poi recupera il saldo aggiornato
        conto_cassa = ContoFinanziario.objects.get(tipo='cassa', nome='Cassa Agenzia')
        saldo_cassa_agenzia = conto_cassa.saldo
    except ContoFinanziario.DoesNotExist:
        # Se il conto non esiste, crealo automaticamente
        try:
            ContoFinanziario.crea_conti_default(request.user)
            conto_cassa = ContoFinanziario.objects.get(tipo='cassa', nome='Cassa Agenzia')
            saldo_cassa_agenzia = conto_cassa.saldo
        except Exception as e:
            messages.error(request, f'Errore nella creazione dei conti predefiniti: {str(e)}. Contatta l\'amministratore.')
            saldo_cassa_agenzia = 0

    # Recupera l'ultima distinta aperta dall'operatore corrente
    try:
        distinta_corrente = DistintaCassa.objects.filter(
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
        'saldo_cassa_agenzia': saldo_cassa_agenzia,
        'distinta_corrente': distinta_corrente,
    }

    return render(request, 'app/dashboard.html', context)


# Gestione Clienti
@login_required
def lista_clienti(request):
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    
    # Aggiorna i saldi di tutti i clienti
    for cliente in Cliente.objects.using(user_db).all():
        cliente.aggiorna_saldo(using=user_db)

    clienti = Cliente.objects.using(user_db).all()

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
def dettaglio_cliente(request, pk):
    user_db = get_user_database(request.user)
    cliente = get_object_or_404(Cliente.objects.using(user_db), pk=pk)

    # Aggiorna il saldo del cliente
    cliente.aggiorna_saldo(using=user_db)

    # Recupera i movimenti del cliente
    movimenti = cliente.movimenti.all().order_by('-data')[:20]

    # Recupera le comunicazioni del cliente
    comunicazioni = cliente.comunicazioni.all().order_by('-data')[:10]

    # Verifica se c'è una distinta aperta per la funzionalità saldo
    distinta_aperta = DistintaCassa.objects.using(user_db).filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    context = {
        'cliente': cliente,
        'movimenti': movimenti,
        'comunicazioni': comunicazioni,
        'distinta_aperta': distinta_aperta,
    }
    
    return render(request, 'app/dettaglio_cliente.html', context)

@login_required
def nuovo_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST, user=request.user)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.creato_da = request.user
            
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
def modifica_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente, user=request.user)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.modificato_da = request.user
            cliente.save()
            messages.success(request, f'Cliente {cliente.nome_completo} aggiornato con successo!')
            return redirect('dettaglio_cliente', pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente, user=request.user)
    
    return render(request, 'app/form_cliente.html', {'form': form, 'cliente': cliente, 'titolo': 'Modifica Cliente'})


# Gestione Movimenti
@login_required
def lista_movimenti(request):
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    
    # Aggiorna i saldi di tutti i clienti prima di mostrare i movimenti
    for cliente in Cliente.objects.using(user_db).all():
        cliente.aggiorna_saldo(using=user_db)

    movimenti = Movimento.objects.using(user_db).select_related('cliente', 'distinta').filter(cliente__isnull=False, distinta__isnull=False)

    # Verifica se c'è una distinta aperta (per la funzionalità saldo)
    distinta_aperta = DistintaCassa.objects.using(user_db).filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    # Prepara il form di filtro
    form_filtro = FiltroMovimentiForm(request.GET)
    
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
def nuovo_movimento(request):
    user_db = get_user_database(request.user)
    # Verifica se esiste una distinta aperta
    try:
        distinta = DistintaCassa.objects.using(user_db).filter(
            operatore=request.user,
            stato='aperta'
        ).latest('data', 'ora_inizio')
    except DistintaCassa.DoesNotExist:
        messages.error(request, 'Non esiste una distinta aperta. Creane una prima di registrare movimenti.')
        return redirect('nuova_distinta')

    # Verifica se la richiesta è AJAX
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = MovimentoForm(request.POST, distinta=distinta)
        if form.is_valid():
            movimento = form.save(commit=False)
            movimento.distinta = distinta
            movimento.creato_da = request.user

            # Salva la nota dal campo manuale
            if request.POST.get('note'):
                movimento.note = request.POST.get('note')

            # Salva il movimento
            movimento.save()

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
            cliente.aggiorna_saldo(using=user_db)

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
                        'data': movimento.data.strftime('%d/%m/%Y %H:%M'),
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
        form = MovimentoForm(distinta=distinta)

    context = {
        'form': form,
        'distinta': distinta,
        'titolo': 'Nuovo Movimento'
    }

    return render(request, 'app/form_movimento.html', context)

@login_required
def salda_movimento(request, pk):
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    movimento = get_object_or_404(Movimento.objects.using(user_db), pk=pk)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Verifica se esiste una distinta aperta
    try:
        distinta = DistintaCassa.objects.using(user_db).filter(
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
        movimento_compensazione = Movimento.objects.filter(
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
                'data': movimento_compensazione.data.strftime('%d/%m/%Y %H:%M') if movimento_compensazione else timezone.now().strftime('%d/%m/%Y %H:%M'),
                # 'note': movimento_compensazione.note if movimento_compensazione and movimento_compensazione.note else '',
                'data_creazione': movimento_compensazione.data_creazione.strftime('%d/%m/%Y %H:%M') if movimento_compensazione else '',
                'data_modifica': movimento_compensazione.data_modifica.strftime('%d/%m/%Y %H:%M') if movimento_compensazione else '',
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
def dettaglio_movimento(request, pk):
    """View per visualizzare i dettagli di un movimento (sola lettura)"""
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    movimento = get_object_or_404(Movimento.objects.using(user_db), pk=pk)
    
    # Verifica autorizzazioni base - l'utente deve poter vedere la distinta
    if movimento.distinta.operatore != request.user and not request.user.is_superuser:
        messages.error(request, 'Non sei autorizzato a visualizzare questo movimento.')
        return redirect('home')
    
    # Recupera i log delle attività relativi a questo movimento
    from django.contrib.contenttypes.models import ContentType
    movimento_content_type = ContentType.objects.get_for_model(Movimento)
    logs = ActivityLog.objects.filter(
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
def modifica_movimento(request, pk):
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    movimento = get_object_or_404(Movimento.objects.using(user_db), pk=pk)

    # Verifica autorizzazioni
    if movimento.distinta.stato != 'aperta':
        messages.error(request, 'Non è possibile modificare un movimento di una distinta chiusa.')
        return redirect('dettaglio_distinta', pk=movimento.distinta.pk)

    if movimento.distinta.operatore != request.user and not request.user.is_superuser:
        messages.error(request, 'Non sei autorizzato a modificare questo movimento.')
        return redirect('dettaglio_distinta', pk=movimento.distinta.pk)

    if request.method == 'POST':
        # Raccoglie i dati prima della modifica per il log (prima di processare il form)
        movimento_before = {
            'tipo': movimento.get_tipo_display(),
            'importo': str(abs(movimento.importo)),
            'cliente': movimento.cliente.nome_completo,
            'distinta': movimento.distinta.id,
            'note': movimento.note if movimento.note else '',
            'saldato': movimento.saldato
        }
        
        form = MovimentoForm(request.POST, instance=movimento, distinta=movimento.distinta)
        if form.is_valid():
            # Salva il movimento aggiornato
            movimento = form.save(commit=False)
            movimento.modificato_da = request.user

            # Imposta manualmente l'importo con il segno corretto per non modificarlo nel save
            from decimal import Decimal
            if movimento.tipo in ['schedina', 'ricarica']:
                importo_con_segno = -abs(Decimal(str(form.cleaned_data['importo'])))
            else:
                importo_con_segno = abs(Decimal(str(form.cleaned_data['importo'])))

            # Imposta manualmente l'importo per evitare che il save lo cambi nuovamente
            movimento.importo = importo_con_segno

            # Assicurati che la nota venga salvata
            if form.cleaned_data.get('note'):
                movimento.note = form.cleaned_data['note']

            movimento.save()

            # Raccoglie i dati dopo la modifica per il log
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
                action='update',
                description=f"Modifica movimento #{movimento.id} ({movimento.get_tipo_display()}) per {movimento.cliente}",
                data_before=movimento_before,
                data_after=movimento_after
            )

            # Il metodo save aggiorna automaticamente il saldo del cliente
            # considerando solo i movimenti non saldati

            messages.success(request, f'Movimento {movimento.get_tipo_display()} aggiornato con successo!')
            return redirect('dettaglio_distinta', pk=movimento.distinta.pk)
    else:
        # Per il form, usiamo l'importo in valore assoluto
        movimento.importo = abs(movimento.importo)
        form = MovimentoForm(instance=movimento, distinta=movimento.distinta)

    context = {
        'form': form,
        'movimento': movimento,
    }

    return render(request, 'app/modifica_movimento.html', context)

@login_required
@user_passes_test(is_manager_or_admin)
def elimina_movimento(request, pk):
    # Ottieni il database dell'agenzia dell'utente
    user_db = get_user_database(request.user)
    movimento = get_object_or_404(Movimento.objects.using(user_db), pk=pk)

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
        movimento.delete()
        messages.success(request, 'Movimento eliminato con successo!')
        return redirect('lista_movimenti')
    
    context = {
        'movimento': movimento,
    }
    
    return render(request, 'app/conferma_elimina_movimento.html', context)


# Gestione Distinte di Cassa
@login_required
def lista_distinte(request):
    user_db = get_user_database(request.user)
    distinte = DistintaCassa.objects.using(user_db).all()
    
    # Prepara il form di filtro
    form_filtro = FiltroDistinteForm(request.GET)
    
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
    
    context = {
        'page_obj': page_obj,
        'form_filtro': form_filtro,
    }
    
    return render(request, 'app/lista_distinte.html', context)

@login_required
def dettaglio_distinta(request, pk):
    distinta = get_object_or_404(DistintaCassa, pk=pk)

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
    movimenti = distinta.movimenti.all().order_by('-data')

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
        form_movimento = MovimentoForm(distinta=distinta)

        # Gestisci la selezione del cliente per vedere i movimenti da saldare
        cliente_id = request.GET.get('cliente')
        if cliente_id:
            try:
                cliente_selezionato = Cliente.objects.get(pk=cliente_id)
                movimenti_da_saldare = Movimento.objects.filter(
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
def nuova_distinta(request):
    # Verifica se l'utente ha già una distinta aperta
    distinta_aperta = DistintaCassa.objects.filter(
        operatore=request.user,
        stato='aperta'
    ).exists()

    if distinta_aperta:
        messages.warning(request, 'Hai già una distinta aperta. Chiudila prima di crearne una nuova.')
        return redirect('lista_distinte')

    # Ottieni il conto cassa
    try:
        conto_cassa = ContoFinanziario.objects.filter(tipo='cassa').first()
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
            distinta.operatore = request.user
            distinta.data = timezone.now().date()
            distinta.ora_inizio = timezone.now().time()
            distinta.stato = 'aperta'

            # Recupera i dati dal form
            cassa_iniziale = form.cleaned_data['cassa_iniziale']
            prelievo_parziale = form.cleaned_data.get('prelievo_parziale', False)

            # Controlla che il saldo cassa sia sufficiente
            if cassa_iniziale > conto_cassa.saldo:
                messages.error(request, f'Il valore di cassa iniziale ({cassa_iniziale} €) supera il saldo disponibile in cassa ({conto_cassa.saldo} €).')
                return redirect('nuova_distinta')

            # Salva il valore della cassa iniziale
            distinta.cassa_iniziale = cassa_iniziale
            distinta.save()

            # Aggiorna il saldo del conto cassa
            saldo_precedente = conto_cassa.saldo
            conto_cassa.saldo -= cassa_iniziale
            conto_cassa.modificato_da = request.user
            conto_cassa.save()

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

    return render(request, 'app/form_distinta.html', {'form': form, 'titolo': 'Nuova Distinta', 'conto_cassa': conto_cassa})

@login_required
def chiudi_distinta(request, pk):
    distinta = get_object_or_404(DistintaCassa, pk=pk)

    # Verifica autorizzazioni
    if distinta.operatore != request.user and not is_admin(request.user):
        return HttpResponseForbidden("Non sei autorizzato a chiudere questa distinta.")

    if distinta.stato != 'aperta':
        messages.error(request, 'Questa distinta è già stata chiusa.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    # Ottieni il conto cassa
    try:
        conto_cassa = ContoFinanziario.objects.filter(tipo='cassa').first()
        if not conto_cassa:
            messages.warning(request, 'Nessun conto cassa trovato nel bilancio. La distinta sarà chiusa, ma il saldo della cassa non sarà aggiornato.')
    except:
        messages.error(request, 'Errore nel recupero del conto cassa. La distinta sarà chiusa, ma il saldo della cassa non sarà aggiornato.')
        conto_cassa = None

    if request.method == 'POST':
        form = ChiusuraDistintaForm(request.POST, instance=distinta)
        if form.is_valid():
            distinta = form.save(commit=False)
            distinta.ora_fine = timezone.now().time()
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

            # Se il form ha inviato un valore per differenza_cassa, usa quello
            # altrimenti ricalcola
            if form.cleaned_data.get('differenza_cassa') is None:
                # Verifica che cassa_finale sia stato impostato prima di calcolare
                if distinta.cassa_finale is not None:
                    # Calcola saldo totale secondo la formula: cassa finale - entrate + uscite - bevande
                    saldo_totale = (
                        distinta.cassa_finale - totale_entrate + totale_uscite - distinta.totale_bevande
                    )

                    # Calcola differenza cassa (saldo totale - saldo terminale)
                    distinta.differenza_cassa = saldo_totale

                    # Se c'è un saldo terminale, consideralo nella differenza
                    if distinta.saldo_terminale:
                        distinta.differenza_cassa -= distinta.saldo_terminale
                else:
                    # Se cassa_finale non è impostato, imposta differenza_cassa a 0 come valore predefinito
                    distinta.differenza_cassa = 0
                    messages.warning(request, 'Cassa finale non impostata. La differenza di cassa è stata impostata a 0.')

            # Dati prima della chiusura per il log
            distinta_before = {
                'operatore': distinta.operatore.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'stato': 'aperta'
            }

            # Salva la distinta chiusa
            distinta.save()

            # Aggiorna il saldo del conto cassa con il valore della cassa finale
            if conto_cassa:
                saldo_precedente = conto_cassa.saldo
                conto_cassa.saldo += distinta.cassa_finale
                conto_cassa.modificato_da = request.user
                conto_cassa.save()

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
@user_passes_test(is_manager_or_admin)
def verifica_distinta(request, pk):
    distinta = get_object_or_404(DistintaCassa, pk=pk)

    if distinta.stato != 'chiusa':
        messages.error(request, 'Questa distinta non può essere verificata.')
        return redirect('dettaglio_distinta', pk=distinta.pk)

    if request.method == 'POST':
        form = VerificaDistintaForm(request.POST, instance=distinta)
        if form.is_valid():
            distinta = form.save(commit=False)
            distinta.stato = 'verificata'
            distinta.verificata_da = request.user
            distinta.data_verifica = timezone.now()
            distinta.save()

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
    distinta = get_object_or_404(DistintaCassa, pk=pk)

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
        distinta.save()

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
    # Controlla se esistono i conti predefiniti, altrimenti li crea
    if ContoFinanziario.objects.count() == 0:
        try:
            ContoFinanziario.crea_conti_default(request.user)
            messages.success(request, 'Conti finanziari predefiniti creati con successo.')
        except Exception as e:
            messages.error(request, f'Errore nella creazione dei conti predefiniti: {str(e)}. Contatta l\'amministratore.')

    # Calcola il saldo attuale dei clienti
    saldo_clienti_movimenti = Cliente.calcola_saldo_complessivo()

    # Aggiorna il saldo del conto clienti se esiste (invertendo il segno per il bilancio)
    try:
        conto_clienti = ContoFinanziario.objects.filter(tipo='clienti').first()
        saldo_clienti_bilancio = -saldo_clienti_movimenti  # Inverto il segno per il bilancio
        if conto_clienti and conto_clienti.saldo != saldo_clienti_bilancio:
            conto_clienti.saldo = saldo_clienti_bilancio
            conto_clienti.modificato_da = request.user
            conto_clienti.save()
            messages.info(request, f'Saldo clienti aggiornato automaticamente: {saldo_clienti_bilancio} €')
    except ContoFinanziario.DoesNotExist:
        pass

    # Ottieni tutti i conti finanziari (dopo l'aggiornamento)
    conti = ContoFinanziario.objects.all()

    # Raggruppa i conti per tipo
    conti_per_tipo = {}
    for tipo, nome in ContoFinanziario.TIPO_CHOICES:
        conti_per_tipo[tipo] = conti.filter(tipo=tipo)

    # Ottieni gli ultimi bilanci periodici
    bilanci = BilancioPeriodico.objects.all()[:10]

    # Calcola il saldo totale
    saldo_totale = ContoFinanziario.calcola_saldo_totale()

    # Calcola saldi per tipo
    saldi_per_tipo = {}
    for tipo, nome in ContoFinanziario.TIPO_CHOICES:
        saldi_per_tipo[tipo] = ContoFinanziario.calcola_saldo_per_tipo(tipo)

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
            conto.creato_da = request.user
            conto.modificato_da = request.user
            conto.save()
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
    conto = get_object_or_404(ContoFinanziario, pk=pk)

    if request.method == 'POST':
        form = ContoFinanziarioForm(request.POST, instance=conto)
        if form.is_valid():
            conto = form.save(commit=False)
            conto.modificato_da = request.user
            conto.save()
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
    conto = get_object_or_404(ContoFinanziario, pk=pk)

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

            conto.modificato_da = request.user
            conto.save()

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
    conto = get_object_or_404(ContoFinanziario, pk=pk)
    
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
    bilancio = get_object_or_404(BilancioPeriodico, pk=pk)

    # Verifica se esiste un bilancio precedente per il confronto
    try:
        bilancio_precedente = BilancioPeriodico.objects.filter(
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

    logs = ActivityLog.objects.all()

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

    # Lista di utenti per il filtro
    users = User.objects.filter(activity_logs__isnull=False).distinct()

    # Lista di tipi di contenuto per il filtro
    content_types = ContentType.objects.filter(
        id__in=ActivityLog.objects.values_list('content_type_id', flat=True).distinct()
    )

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
    log = get_object_or_404(ActivityLog, pk=pk)

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
    cliente_id = request.GET.get('cliente_id')

    if not cliente_id:
        return JsonResponse({'error': 'Cliente non specificato'}, status=400)

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
        movimenti = Movimento.objects.filter(
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
                'data': movimento.data.strftime('%d/%m/%Y %H:%M'),
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
        form = GirocontoForm(request.POST)
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
        form = GirocontoForm()

    context = {
        'form': form,
        'titolo': 'Effettua Giroconto',
    }

    return render(request, 'app/form_giroconto.html', context)


@login_required
@user_passes_test(is_manager_or_admin)
def lista_movimenti_conti(request):
    """Visualizza la lista dei movimenti tra conti"""
    movimenti = MovimentoConti.objects.all()

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
    conti = ContoFinanziario.objects.all()

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
    movimento = get_object_or_404(MovimentoConti, pk=pk)
    
    if request.method == 'POST':
        # Il metodo delete del modello si occuperà di ripristinare i saldi
        movimento.delete()
        messages.success(request, f'Movimento eliminato con successo!')
        return redirect('lista_movimenti_conti')
    
    context = {
        'movimento': movimento,
        'titolo': f'Elimina Movimento: {movimento}'
    }
    
    return render(request, 'app/elimina_movimento_conti.html', context)