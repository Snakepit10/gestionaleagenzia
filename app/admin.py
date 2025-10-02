from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import Cliente, Movimento, DistintaCassa, Comunicazione, Agenzia, ProfiloUtente
from .database_utils import AGENZIA_DATABASE_MAP


class DatabaseSelectorMixin:
    """Mixin per aggiungere selezione database"""
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        selected_db = request.GET.get('db', 'goldbet_db')
        
        # Se c'è un parametro 'e' ma non 'db', è un redirect - mantieni il database dalla sessione
        if 'e' in request.GET and 'db' not in request.GET:
            selected_db = request.session.get('admin_selected_db', 'goldbet_db')
        else:
            # Salva il database selezionato nella sessione
            request.session['admin_selected_db'] = selected_db
        
        # Aggiungi informazioni database al context
        extra_context['db_selector'] = {
            'current': selected_db,
            'options': [
                ('default', 'Default'),
                ('goldbet_db', 'Goldbet'),
                ('better_db', 'Better'),
                ('planet_db', 'Planet')
            ],
            'current_label': dict([
                ('default', 'Default'),
                ('goldbet_db', 'Goldbet'),
                ('better_db', 'Better'),
                ('planet_db', 'Planet')
            ]).get(selected_db, 'Unknown')
        }
        
        # Imposta il database selezionato come attributo per get_queryset
        self._selected_db = selected_db
        
        return super().changelist_view(request, extra_context)
    
    def get_queryset(self, request):
        # Prima prova a usare il database dalla changelist_view
        if hasattr(self, '_selected_db'):
            selected_db = self._selected_db
        else:
            # Fallback sui parametri GET o sessione
            if 'e' in request.GET and 'db' not in request.GET:
                selected_db = request.session.get('admin_selected_db', 'goldbet_db')
            else:
                selected_db = request.GET.get('db', 'goldbet_db')
                request.session['admin_selected_db'] = selected_db
        
        try:
            queryset = self.model.objects.using(selected_db).all()
            return queryset
        except Exception as e:
            return self.model.objects.using('default').none()


@admin.register(Cliente)
class ClienteAdmin(DatabaseSelectorMixin, admin.ModelAdmin):
    list_display = ('cognome', 'nome', 'saldo', 'fido_massimo', 'rating', 'telefono')
    list_filter = ('rating',)
    search_fields = ('cognome', 'nome', 'email', 'telefono')
    fieldsets = (
        ('Informazioni Personali', {
            'fields': ('nome', 'cognome', 'email', 'telefono')
        }),
        ('Dati Contabili', {
            'fields': ('saldo', 'fido_massimo', 'rating')
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
    list_display = ('nome', 'codice', 'database_name', 'attiva', 'data_creazione')
    list_filter = ('attiva', 'data_creazione')
    search_fields = ('nome', 'codice')
    readonly_fields = ('data_creazione',)
    
    fieldsets = (
        ('Informazioni Agenzia', {
            'fields': ('nome', 'codice', 'database_name', 'attiva')
        }),
        ('Date', {
            'fields': ('data_creazione',)
        }),
    )


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