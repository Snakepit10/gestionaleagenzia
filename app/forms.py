from django import forms
from django.utils import timezone
from .models import Cliente, Movimento, DistintaCassa, Comunicazione, ContoFinanziario, BilancioPeriodico


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'cognome', 'email', 'telefono', 'fido_massimo', 'note']
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Disabilita il campo fido_massimo per gli operatori
        if user and not (user.is_superuser or user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
            self.fields['fido_massimo'].disabled = True


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
        super().__init__(*args, **kwargs)

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

        # Ottieni il saldo del conto cassa
        try:
            from .models import ContoFinanziario
            conto_cassa = ContoFinanziario.objects.filter(tipo='cassa').first()
            if conto_cassa:
                self.fields['cassa_iniziale'].help_text = f"Saldo disponibile in cassa: {conto_cassa.saldo} €"
                self.fields['cassa_iniziale'].initial = conto_cassa.saldo
                # Imposta l'attributo data-max-value per il campo cassa_iniziale
                self.fields['cassa_iniziale'].widget.attrs.update({'data-max-value': conto_cassa.saldo})
            else:
                self.fields['cassa_iniziale'].help_text = "Nessun conto cassa trovato nel bilancio"
        except:
            self.fields['cassa_iniziale'].help_text = "Errore nel recupero del saldo cassa"

    def clean_cassa_iniziale(self):
        cassa_iniziale = self.cleaned_data.get('cassa_iniziale')
        prelievo_parziale = self.cleaned_data.get('prelievo_parziale')

        if cassa_iniziale <= 0:
            raise forms.ValidationError("La cassa iniziale deve essere maggiore di zero.")

        try:
            from .models import ContoFinanziario
            conto_cassa = ContoFinanziario.objects.filter(tipo='cassa').first()
            if conto_cassa and cassa_iniziale > conto_cassa.saldo:
                raise forms.ValidationError(f"Il valore immesso ({cassa_iniziale} €) supera il saldo disponibile in cassa ({conto_cassa.saldo} €).")
        except:
            pass

        return cassa_iniziale


class ChiusuraDistintaForm(forms.ModelForm):
    class Meta:
        model = DistintaCassa
        fields = ['cassa_finale', 'totale_bevande', 'saldo_terminale', 'differenza_cassa', 'note_verifica']
        widgets = {
            'cassa_finale': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'totale_bevande': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'saldo_terminale': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'differenza_cassa': forms.HiddenInput(),
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
        queryset=Cliente.objects.all(),
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
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import User
        operatori = User.objects.filter(
            movimenti_creati__isnull=False
        ).distinct().values_list('id', 'username')
        self.fields['operatore'].choices = [('', 'Tutti')] + list(operatori)


class ContoFinanziarioForm(forms.ModelForm):
    class Meta:
        model = ContoFinanziario
        fields = ['nome', 'tipo', 'saldo', 'descrizione']
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'saldo': forms.NumberInput(attrs={'step': '0.01'}),
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
        queryset=ContoFinanziario.objects.all(),
        label="Conto di Origine",
        widget=forms.Select(attrs={'class': 'form-select select2'})
    )
    conto_destinazione = forms.ModelChoiceField(
        queryset=ContoFinanziario.objects.all(),
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