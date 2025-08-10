from django.contrib import admin
from .models import Cliente, Movimento, DistintaCassa, Comunicazione, Agenzia, ProfiloUtente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
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


@admin.register(Movimento)
class MovimentoAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'tipo', 'importo', 'data', 'saldato', 'distinta')
    list_filter = ('tipo', 'saldato', 'data')
    search_fields = ('cliente__cognome', 'cliente__nome', 'distinta__id')
    date_hierarchy = 'data'
    readonly_fields = ('data_creazione', 'creato_da', 'data_modifica', 'modificato_da')
    
    def save_model(self, request, obj, form, change):
        if not change:  # Se è un nuovo oggetto
            obj.creato_da = request.user
        else:
            obj.modificato_da = request.user
        super().save_model(request, obj, form, change)


@admin.register(DistintaCassa)
class DistintaCassaAdmin(admin.ModelAdmin):
    list_display = ('id', 'data', 'operatore', 'stato', 'cassa_iniziale', 'cassa_finale', 'differenza_cassa')
    list_filter = ('stato', 'data', 'operatore')
    search_fields = ('id', 'operatore__username')
    date_hierarchy = 'data'
    readonly_fields = ('differenza_cassa', 'verificata_da', 'data_verifica')
    
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