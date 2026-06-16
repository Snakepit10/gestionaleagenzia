from django import forms
from django.utils import timezone
from .models import Cliente, Movimento, DistintaCassa, Comunicazione, ContoFinanziario, BilancioPeriodico, RiepilogoGiornaliero


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'cognome', 'email', 'telefono', 'fido_massimo', 'notifica_movimenti', 'note']
        labels = {
            'notifica_movimenti': 'Notifica Telegram su ogni movimento',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Disabilita i campi riservati ai gestori per gli operatori
        if user and not (user.is_superuser or user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
            self.fields['fido_massimo'].disabled = True
            self.fields['notifica_movimenti'].disabled = True


class MovimentoForm(forms.ModelForm):
    class Meta:
        model = Movimento
        fields = ['cliente', 'tipo', 'importo', 'saldato', 'note']
        widgets = {
            'importo': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        distinta = kwargs.pop('distinta', None)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Imposta la queryset dei clienti dal database corretto
        if user:
            from .database_utils import DatabaseManager
            db = DatabaseManager(user)
            self.fields['cliente'].queryset = db.get_queryset(Cliente)

        # Personalizza il campo cliente con ricerca avanzata
        self.fields['cliente'].widget.attrs.update({
            'class': 'select2',
            'data-placeholder': 'Cerca cliente...'
        })

        # Assicurati che l'importo sia sempre positivo nel form
        if 'importo' in self.initial:
            self.initial['importo'] = abs(self.initial['importo'])

        # Salva la distinta per usarla nel save
        self.distinta = distinta


class DistintaCassaForm(forms.ModelForm):
    prelievo_parziale = forms.BooleanField(
        required=False,
        label="Prelievo parziale dalla cassa",
        help_text="Seleziona questa opzione se vuoi prelevare solo una parte del contante disponibile in cassa"
    )

    class Meta:
        model = DistintaCassa
        fields = ['cassa_iniziale']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user

        # Ottieni il saldo del conto cassa dal database dell'utente
        try:
            from .models import ContoFinanziario
            from .database_utils import DatabaseManager
            
            if user:
                db = DatabaseManager(user)
                conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
                if conto_cassa:
                    self.fields['cassa_iniziale'].help_text = f"Saldo disponibile in cassa: {conto_cassa.saldo} €"
                    self.fields['cassa_iniziale'].initial = conto_cassa.saldo
                    # Imposta l'attributo data-max-value per il campo cassa_iniziale
                    self.fields['cassa_iniziale'].widget.attrs.update({'data-max-value': conto_cassa.saldo})
                else:
                    self.fields['cassa_iniziale'].help_text = "Nessun conto cassa trovato nel bilancio"
            else:
                self.fields['cassa_iniziale'].help_text = "Utente non specificato"
        except Exception as e:
            self.fields['cassa_iniziale'].help_text = f"Errore nel recupero del saldo cassa: {str(e)}"

    def clean_cassa_iniziale(self):
        cassa_iniziale = self.cleaned_data.get('cassa_iniziale')
        prelievo_parziale = self.cleaned_data.get('prelievo_parziale')

        if cassa_iniziale <= 0:
            raise forms.ValidationError("La cassa iniziale deve essere maggiore di zero.")

        try:
            from .models import ContoFinanziario
            from .database_utils import DatabaseManager
            
            if self.user:
                db = DatabaseManager(self.user)
                conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
                if conto_cassa and cassa_iniziale > conto_cassa.saldo:
                    raise forms.ValidationError(f"Il valore immesso ({cassa_iniziale} €) supera il saldo disponibile in cassa ({conto_cassa.saldo} €).")
        except forms.ValidationError:
            raise
        except:
            pass

        return cassa_iniziale


class ChiusuraDistintaForm(forms.ModelForm):
    class Meta:
        model = DistintaCassa
        fields = ['cassa_finale', 'totale_bevande', 'saldo_terminale', 'differenza_cassa', 'note_distinta', 'note_verifica']
        widgets = {
            'cassa_finale': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'totale_bevande': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'saldo_terminale': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'differenza_cassa': forms.NumberInput(attrs={'readonly': 'readonly', 'step': '0.01'}),
            'note_distinta': forms.Textarea(attrs={'rows': 4}),
        }


class VerificaDistintaForm(forms.ModelForm):
    class Meta:
        model = DistintaCassa
        fields = ['note_verifica']
        widgets = {
            'note_verifica': forms.Textarea(attrs={'rows': 4}),
        }


class ComunicazioneForm(forms.ModelForm):
    class Meta:
        model = Comunicazione
        fields = ['cliente', 'tipo', 'contenuto']
        widgets = {
            'contenuto': forms.Textarea(attrs={'rows': 4}),
        }


class FiltroMovimentiForm(forms.Form):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.none(),  # Inizialmente vuoto
        required=False,
        widget=forms.Select(attrs={'class': 'select2'})
    )
    tipo = forms.ChoiceField(
        choices=[('', 'Tutti')] + list(Movimento.TIPO_CHOICES),
        required=False
    )
    data_inizio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    data_fine = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    saldato = forms.ChoiceField(
        choices=[('', 'Tutti'), ('True', 'Saldato'), ('False', 'Non Saldato')],
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            from .database_utils import DatabaseManager
            db = DatabaseManager(user)
            self.fields['cliente'].queryset = db.get_queryset(Cliente)


class FiltroDistinteForm(forms.Form):
    operatore = forms.ChoiceField(required=False)
    stato = forms.ChoiceField(
        choices=[('', 'Tutti')] + list(DistintaCassa.STATO_CHOICES),
        required=False
    )
    data_inizio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    data_fine = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Rimuovi user ma non lo usi
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import User
        operatori = User.objects.filter(
            movimenti_creati__isnull=False
        ).distinct().values_list('id', 'username')
        self.fields['operatore'].choices = [('', 'Tutti')] + list(operatori)


class ContoFinanziarioForm(forms.ModelForm):
    class Meta:
        model = ContoFinanziario
        fields = ['nome', 'tipo', 'saldo', 'notifica_telegram', 'descrizione']
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'saldo': forms.NumberInput(attrs={'step': '0.01'}),
        }
        labels = {
            'notifica_telegram': 'Notifica Telegram sui movimenti',
        }


class ModificaSaldoForm(forms.Form):
    importo = forms.DecimalField(max_digits=15, decimal_places=2, widget=forms.NumberInput(attrs={'step': '0.01'}))
    operazione = forms.ChoiceField(choices=[
        ('add', 'Aggiungi'),
        ('subtract', 'Sottrai'),
        ('set', 'Imposta valore')
    ])
    note = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)


class GirocontoForm(forms.Form):
    conto_origine = forms.ModelChoiceField(
        queryset=ContoFinanziario.objects.none(),
        label="Conto di Origine",
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    conto_destinazione = forms.ModelChoiceField(
        queryset=ContoFinanziario.objects.none(),
        label="Conto di Destinazione",
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    importo = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'})
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            from .database_utils import DatabaseManager
            db = DatabaseManager(user)
            conti = db.get_queryset(ContoFinanziario)
            self.fields['conto_origine'].queryset = conti
            self.fields['conto_destinazione'].queryset = conti

    def clean(self):
        cleaned_data = super().clean()
        conto_origine = cleaned_data.get('conto_origine')
        conto_destinazione = cleaned_data.get('conto_destinazione')
        importo = cleaned_data.get('importo')

        if conto_origine and conto_destinazione and conto_origine == conto_destinazione:
            raise forms.ValidationError("Il conto di origine e di destinazione non possono essere uguali.")

        if conto_origine and importo and importo > conto_origine.saldo:
            raise forms.ValidationError(f"Il conto di origine ha un saldo insufficiente ({conto_origine.saldo}€).")

        return cleaned_data


class BilancioPeriodoForm(forms.ModelForm):
    class Meta:
        model = BilancioPeriodico
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Inserisci note aggiuntive sul bilancio'}),
        }


class RiepilogoGiornalieroForm(forms.ModelForm):
    """Form per creare e modificare riepiloghi giornalieri"""

    class Meta:
        model = RiepilogoGiornaliero
        fields = [
            'data',
            'saldo_ced',
            'saldo_pvonline',
            'giroconto_ced',
            'giroconto_online',
            'sovvenzione',
            'restituzione'
        ]
        widgets = {
            'data': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'saldo_ced': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
            'saldo_pvonline': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
            'giroconto_ced': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
            'giroconto_online': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
            'sovvenzione': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
            'restituzione': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control'
            }),
        }
        labels = {
            'data': 'Data',
            'saldo_ced': 'Saldo CED',
            'saldo_pvonline': 'Saldo PV Online',
            'giroconto_ced': 'Giroconto CED',
            'giroconto_online': 'Giroconto Online',
            'sovvenzione': 'Sovvenzione',
            'restituzione': 'Restituzione',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user

        # Se stiamo modificando, mostra anche i campi calcolati come readonly
        if self.instance and self.instance.pk:
            # Aggiungi i campi readonly per visualizzare i valori calcolati
            self.fields['saldo_crediti_display'] = forms.DecimalField(
                label='Saldo Totale Crediti',
                required=False,
                disabled=True,
                initial=self.instance.saldo_crediti,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )
            self.fields['saldo_cassa_display'] = forms.DecimalField(
                label='Saldo Cassa',
                required=False,
                disabled=True,
                initial=self.instance.saldo_cassa,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )
            self.fields['cassa_2_display'] = forms.DecimalField(
                label='Cassa 2 (Bevande)',
                required=False,
                disabled=True,
                initial=self.instance.cassa_2,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )
            self.fields['differenza_distinta_display'] = forms.DecimalField(
                label='Differenza Distinta',
                required=False,
                disabled=True,
                initial=self.instance.differenza_distinta,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )
            self.fields['totale_display'] = forms.DecimalField(
                label='Totale',
                required=False,
                disabled=True,
                initial=self.instance.totale,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )
            self.fields['saldo_progressivo_display'] = forms.DecimalField(
                label='Saldo Progressivo',
                required=False,
                disabled=True,
                initial=self.instance.saldo_progressivo,
                widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
            )


class FiltroRiepiloghiForm(forms.Form):
    """Form per filtrare i riepiloghi giornalieri"""

    data_da = forms.DateField(
        required=False,
        label="Data Da",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    data_a = forms.DateField(
        required=False,
        label="Data A",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )