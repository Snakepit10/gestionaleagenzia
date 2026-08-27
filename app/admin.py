from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import Cliente, Movimento, DistintaCassa, Comunicazione, Agenzia, ProfiloUtente, RiepilogoGiornaliero, SaldoEsterno, AzzeramentoProgrammato
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
    list_display = ('cognome', 'nome', 'saldo', 'fido_massimo', 'rating', 'telefono', 'notifica_movimenti', 'conto_servizio')
    list_filter = ('rating', 'notifica_movimenti', 'conto_servizio')
    search_fields = ('cognome', 'nome', 'email', 'telefono')
    fieldsets = (
        ('Informazioni Personali', {
            'fields': ('nome', 'cognome', 'email', 'telefono')
        }),
        ('Dati Contabili', {
            'fields': ('saldo', 'fido_massimo', 'rating', 'conto_servizio'),
            'description': 'Conto di servizio: POS, spese, aggiustamenti cassa. Escluso dai totali crediti clienti.'
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


@admin.register(RiepilogoGiornaliero)
class RiepilogoGiornalieroAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = (
        'data',
        'saldo_crediti',
        'saldo_cassa',
        'cassa_2',
        'differenza_distinta',
        'saldo_ced',
        'saldo_pvonline',
        'totale',
        'saldo_progressivo'
    )
    list_filter = ('data',)
    search_fields = ('data',)
    date_hierarchy = 'data'

    fieldsets = (
        ('Data', {
            'fields': ('data',)
        }),
        ('Campi Calcolati Automaticamente', {
            'fields': ('saldo_crediti', 'saldo_cassa', 'cassa_2', 'differenza_distinta'),
            'description': 'Questi campi vengono calcolati automaticamente dalle distinte chiuse/verificate.'
        }),
        ('Campi Manuali', {
            'fields': ('saldo_ced', 'saldo_pvonline', 'giroconto_ced', 'giroconto_online', 'sovvenzione', 'restituzione')
        }),
        ('Totali', {
            'fields': ('totale', 'saldo_progressivo'),
            'description': 'Totale e saldo progressivo calcolati automaticamente.'
        }),
        ('Informazioni di Audit', {
            'fields': ('creato_da', 'data_creazione', 'modificato_da', 'data_modifica'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = (
        'saldo_crediti',
        'saldo_cassa',
        'cassa_2',
        'differenza_distinta',
        'totale',
        'saldo_progressivo',
        'data_creazione',
        'data_modifica'
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creato_da = request.user
        else:
            obj.modificato_da = request.user

        # Ottieni il database selezionato
        selected_db = request.GET.get('db', 'goldbet_db')

        # Salva usando il database selezionato
        obj.save(using=selected_db)

    def delete_model(self, request, obj):
        # Ottieni il database selezionato
        selected_db = request.GET.get('db', 'goldbet_db')
        obj.delete(using=selected_db)