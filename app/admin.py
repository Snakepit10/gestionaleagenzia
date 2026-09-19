from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import (Cliente, Movimento, DistintaCassa, Comunicazione, Agenzia, ProfiloUtente,
                     SaldoEsterno, AzzeramentoProgrammato, RichiestaGiroconto, TaskAgenzia,
                     CategoriaTask, PubblicitaLedwall, ImpostazioniLedwall)
from .database_utils import AGENZIA_DATABASE_MAP


class DatabaseSelectorMixin:
    """Mixin per aggiungere selezione database nell'admin.

    Il database selezionato viene memorizzato in sessione: quando il parametro
    'db' non è presente nell'URL (paginazione, ricerca, ordinamento, redirect) si
    usa l'ultimo database scelto, invece di ricadere sul default.
    """

    DB_OPTIONS = [
        ('default', 'Default'),
        ('goldbet_db', 'Goldbet'),
        ('better_db', 'Better'),
        ('planet_db', 'Planet'),
        ('better_ravanusa_db', 'Better Ravanusa'),
    ]
    DB_DEFAULT = 'goldbet_db'

    def _database_selezionato(self, request):
        valid = {k for k, _ in self.DB_OPTIONS}
        if 'db' in request.GET and request.GET['db'] in valid:
            selected = request.GET['db']
            request.session['admin_selected_db'] = selected
            return selected
        return request.session.get('admin_selected_db', self.DB_DEFAULT)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        selected_db = self._database_selezionato(request)
        extra_context['db_selector'] = {
            'current': selected_db,
            'options': self.DB_OPTIONS,
            'current_label': dict(self.DB_OPTIONS).get(selected_db, 'Unknown'),
        }
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        selected_db = self._database_selezionato(request)
        try:
            return self.model.objects.using(selected_db).all()
        except Exception:
            return self.model.objects.using('default').none()


@admin.register(Cliente)
class ClienteAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('cognome', 'nome', 'saldo', 'fido_massimo', 'rating', 'telefono', 'notifica_movimenti', 'conto_servizio', 'nascosto', 'conto_giroconto', 'giroconto_agenzia')
    list_filter = ('rating', 'notifica_movimenti', 'conto_servizio', 'nascosto', 'conto_giroconto')
    list_editable = ('nascosto',)
    search_fields = ('cognome', 'nome', 'email', 'telefono')
    fieldsets = (
        ('Informazioni Personali', {
            'fields': ('nome', 'cognome', 'email', 'telefono')
        }),
        ('Dati Contabili', {
            'fields': ('saldo', 'fido_massimo', 'rating', 'conto_servizio', 'nascosto',
                       'conto_giroconto', 'giroconto_agenzia'),
            'description': 'Conto di servizio: POS, spese, aggiustamenti cassa. Escluso dai totali crediti clienti. '
                           'Nascosto: il cliente non compare più nella lista clienti agli operatori. '
                           'Conto di giroconto: un movimento su questo conto genera una richiesta da '
                           'accettare presso l\'agenzia partner indicata in "Giroconto agenzia".'
        }),
        ('Notifiche', {
            'fields': ('notifica_movimenti',),
            'description': 'Se attivo, invia una notifica Telegram per ogni movimento del cliente.'
        }),
        ('Note', {
            'fields': ('note',)
        }),
    )
    readonly_fields = ('saldo',)
    
    def get_db_info(self, obj):
        if hasattr(obj, '_state') and hasattr(obj._state, 'db'):
            return obj._state.db or 'default'
        return 'unknown'
    get_db_info.short_description = 'DB'


@admin.register(Movimento)
class MovimentoAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('cliente', 'tipo', 'importo', 'data', 'saldato', 'distinta')
    list_filter = ('tipo', 'saldato', 'data')
    search_fields = ('cliente__cognome', 'cliente__nome', 'distinta__id')
    date_hierarchy = 'data'
    readonly_fields = ('data_creazione', 'creato_da', 'data_modifica', 'modificato_da')
    
    def get_db_info(self, obj):
        if hasattr(obj, '_state') and hasattr(obj._state, 'db'):
            return obj._state.db or 'default'
        return 'unknown'
    get_db_info.short_description = 'DB'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Se è un nuovo oggetto
            obj.creato_da = request.user
        else:
            obj.modificato_da = request.user
        super().save_model(request, obj, form, change)


@admin.register(DistintaCassa)
class DistintaCassaAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('id', 'data', 'operatore', 'stato', 'cassa_iniziale', 'cassa_finale', 'differenza_cassa')
    list_filter = ('stato', 'data', 'operatore')
    search_fields = ('id', 'operatore__username')
    date_hierarchy = 'data'
    readonly_fields = ('differenza_cassa', 'verificata_da', 'data_verifica')
    
    def get_db_info(self, obj):
        if hasattr(obj, '_state') and hasattr(obj._state, 'db'):
            return obj._state.db or 'default'
        return 'unknown'
    get_db_info.short_description = 'DB'
    
    fieldsets = (
        ('Informazioni Generali', {
            'fields': ('operatore', 'data', 'ora_inizio', 'ora_fine', 'stato')
        }),
        ('Dati Contabili', {
            'fields': ('cassa_iniziale', 'cassa_finale', 'totale_entrate', 'totale_uscite', 
                      'totale_bevande', 'saldo_terminale', 'differenza_cassa')
        }),
        ('Verifica', {
            'fields': ('verificata_da', 'data_verifica', 'note_verifica')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        
        # Se l'utente non è un amministratore
        if not request.user.is_superuser:
            # Se la distinta è verificata, rendi tutto readonly
            if obj and obj.stato == 'verificata':
                return ['operatore', 'data', 'ora_inizio', 'ora_fine', 'stato',
                       'cassa_iniziale', 'cassa_finale', 'totale_entrate', 'totale_uscite',
                       'totale_bevande', 'saldo_terminale', 'differenza_cassa',
                       'verificata_da', 'data_verifica', 'note_verifica']
            
            # Se la distinta è di un altro giorno, rendi tutto readonly per manager
            if obj and obj.data != timezone.now().date() and not request.user.groups.filter(name='Amministratore').exists():
                return ['operatore', 'data', 'ora_inizio', 'ora_fine', 'stato',
                       'cassa_iniziale', 'cassa_finale', 'totale_entrate', 'totale_uscite',
                       'totale_bevande', 'saldo_terminale', 'differenza_cassa',
                       'verificata_da', 'data_verifica', 'note_verifica']
        
        return readonly_fields


@admin.register(Comunicazione)
class ComunicazioneAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'tipo', 'operatore', 'data', 'stato')
    list_filter = ('tipo', 'stato', 'data')
    search_fields = ('cliente__cognome', 'cliente__nome', 'contenuto')
    date_hierarchy = 'data'
    readonly_fields = ('data',)


@admin.register(Agenzia)
class AgenziaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'codice', 'database_name', 'attiva', 'telegram_chat_id', 'soglia_cassa', 'data_creazione')
    list_filter = ('attiva', 'data_creazione')
    search_fields = ('nome', 'codice')
    readonly_fields = ('data_creazione',)

    fieldsets = (
        ('Informazioni Agenzia', {
            'fields': ('nome', 'codice', 'database_name', 'attiva')
        }),
        ('Notifiche Telegram', {
            'fields': ('telegram_chat_id', 'soglia_cassa'),
            'description': 'Chat/gruppo Telegram per le notifiche. Soglia cassa: se la cassa finale di una distinta la supera, invia un alert (impostabile anche da Telegram con "soglia <valore>").'
        }),
        ('Estrazione CAST', {
            'fields': ('cast_account_id',),
            'description': 'ID conto CAST associato (impostato alla prima estrazione). Svuota il campo per riassociarlo.'
        }),
        ('Date', {
            'fields': ('data_creazione',)
        }),
    )


@admin.register(AzzeramentoProgrammato)
class AzzeramentoProgrammatoAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('id', 'operatore', 'stato', 'data_richiesta', 'data_esecuzione', 'note')
    list_filter = ('stato',)
    date_hierarchy = 'data_richiesta'
    ordering = ('-data_richiesta',)


@admin.register(SaldoEsterno)
class SaldoEsternoAdmin(admin.ModelAdmin):
    list_display = ('data', 'agenzia', 'tipo', 'saldo', 'rilevato_il')
    list_filter = ('agenzia', 'tipo')
    date_hierarchy = 'data'
    ordering = ('-data',)


@admin.register(RichiestaGiroconto)
class RichiestaGirocontoAdmin(admin.ModelAdmin):
    """Richieste di giroconto inter-agenzia (dati sul DB 'default')."""
    list_display = ('id', 'agenzia_origine', 'agenzia_destinazione', 'conto_origine_nome',
                    'tipo', 'importo', 'stato', 'data_creazione', 'data_risposta')
    list_filter = ('stato', 'agenzia_origine', 'agenzia_destinazione', 'tipo')
    search_fields = ('conto_origine_nome', 'note', 'note_risposta')
    date_hierarchy = 'data_creazione'
    ordering = ('-data_creazione',)
    readonly_fields = ('data_creazione', 'data_risposta', 'movimento_origine_id',
                       'movimento_dest_id', 'conto_dest_id')


@admin.register(CategoriaTask)
class CategoriaTaskAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('nome', 'ordine', 'attivo')
    list_filter = ('attivo',)
    list_editable = ('ordine', 'attivo')
    search_fields = ('nome',)
    ordering = ('ordine', 'nome')


@admin.register(TaskAgenzia)
class TaskAgenziaAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('titolo', 'categoria', 'priorita', 'stato', 'assegnato_a', 'scadenza', 'data_creazione')
    list_filter = ('stato', 'priorita', 'categoria')
    search_fields = ('titolo', 'descrizione', 'note')
    date_hierarchy = 'data_creazione'
    ordering = ('-data_creazione',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creato_da = request.user
        else:
            obj.modificato_da = request.user
        super().save_model(request, obj, form, change)


class PubblicitaLedwallForm(forms.ModelForm):
    upload = forms.FileField(required=False, label='Immagine',
                             help_text='Carica un\'immagine (PNG/JPG). Consigliato orizzontale, es. 320×140.')

    class Meta:
        model = PubblicitaLedwall
        fields = ['titolo', 'attivo', 'ordine', 'transizione', 'secondi']

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get('upload'):
            raise ValidationError('Carica un\'immagine.')
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        f = self.cleaned_data.get('upload')
        if f:
            obj.dati = f.read()
            obj.content_type = getattr(f, 'content_type', None) or 'image/png'
        if commit:
            obj.save()
        return obj


@admin.register(PubblicitaLedwall)
class PubblicitaLedwallAdmin(admin.ModelAdmin):
    form = PubblicitaLedwallForm
    list_display = ('anteprima', 'titolo', 'attivo', 'ordine', 'transizione', 'secondi', 'data_caricamento')
    list_display_links = ('titolo',)
    list_editable = ('attivo', 'ordine', 'transizione', 'secondi')
    ordering = ('ordine', 'id')

    def anteprima(self, obj):
        if obj.pk:
            return format_html(
                '<img src="/ledwall/api/ad/{}" style="height:44px;max-width:160px;'
                'border:1px solid #ccc;background:#000">', obj.pk)
        return '—'
    anteprima.short_description = 'Anteprima'


@admin.register(ImpostazioniLedwall)
class ImpostazioniLedwallAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'secondi_scheda', 'ogni_n_schede', 'secondi_pubblicita')

    def has_add_permission(self, request):
        # Riga unica: consenti l'aggiunta solo se non esiste ancora.
        return not ImpostazioniLedwall.objects.using('default').exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProfiloUtente)
class ProfiloUtenteAdmin(admin.ModelAdmin):
    list_display = ('user', 'agenzia', 'get_user_email')
    list_filter = ('agenzia',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'agenzia__nome')

    def get_user_email(self, obj):
        return obj.user.email
    get_user_email.short_description = 'Email'

    fieldsets = (
        ('Associazione', {
            'fields': ('user', 'agenzia')
        }),
    )
