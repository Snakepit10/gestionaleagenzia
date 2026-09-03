from django import forms
from django.utils import timezone
from .models import (Cliente, Movimento, DistintaCassa, Comunicazione, ContoFinanziario, BilancioPeriodico,
                     ProdottoRicavo, CategoriaSpesa, CategoriaProdotto, VoceCosto, Agenzia)


MESI_CHOICES = [
    (1, 'Gennaio'), (2, 'Febbraio'), (3, 'Marzo'), (4, 'Aprile'),
    (5, 'Maggio'), (6, 'Giugno'), (7, 'Luglio'), (8, 'Agosto'),
    (9, 'Settembre'), (10, 'Ottobre'), (11, 'Novembre'), (12, 'Dicembre'),
]


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'cognome', 'email', 'telefono', 'fido_massimo', 'notifica_movimenti', 'conto_servizio', 'note']
        labels = {
            'notifica_movimenti': 'Notifica Telegram su ogni movimento',
            'conto_servizio': 'Conto di servizio (escluso dai totali clienti)',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Disabilita i campi riservati ai gestori per gli operatori
        if user and not (user.is_superuser or user.groups.filter(name__in=['Manager', 'Amministratore']).exists()):
            self.fields['fido_massimo'].disabled = True
            self.fields['notifica_movimenti'].disabled = True
            self.fields['conto_servizio'].disabled = True


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

        # La cassa iniziale è un CONTEGGIO reale: l'operatore deve inserirla a mano.
        # Non prefilliamo il campo; come suggerimento mostriamo la cassa finale
        # dell'ultima distinta chiusa (valore autorevole e stabile), non il saldo
        # ricalcolato che a volte diverge.
        self.fields['cassa_iniziale'].required = True
        self.fields['cassa_iniziale'].initial = None

        try:
            from .models import ContoFinanziario, DistintaCassa
            from .database_utils import DatabaseManager

            if user:
                db = DatabaseManager(user)
                conto_cassa = db.get_queryset(ContoFinanziario).filter(tipo='cassa').first()
                ultima = (db.get_queryset(DistintaCassa)
                          .filter(stato__in=['chiusa', 'verificata'])
                          .order_by('-data', '-ora_inizio').first())

                suggerito = None
                if ultima is not None and ultima.cassa_finale is not None:
                    suggerito = ultima.cassa_finale
                elif conto_cassa is not None:
                    suggerito = conto_cassa.saldo
                saldo_sys = conto_cassa.saldo if conto_cassa else None

                parti = []
                if suggerito is not None:
                    parti.append(f"Suggerito (cassa finale ultima distinta): {suggerito} €")
                if saldo_sys is not None and (suggerito is None or saldo_sys != suggerito):
                    parti.append(f"saldo di sistema: {saldo_sys} €")
                parti.append("inserisci il contante realmente presente in cassa.")
                self.fields['cassa_iniziale'].help_text = " · ".join(parti)

                attrs = {'placeholder': 'Conta e inserisci il contante in cassa', 'autocomplete': 'off'}
                if suggerito is not None:
                    attrs['data-suggerito'] = suggerito
                if saldo_sys is not None:
                    attrs['data-max-value'] = saldo_sys
                self.fields['cassa_iniziale'].widget.attrs.update(attrs)
            else:
                self.fields['cassa_iniziale'].help_text = "Utente non specificato"
        except Exception as e:
            self.fields['cassa_iniziale'].help_text = f"Errore nel recupero del saldo cassa: {str(e)}"

    def clean_cassa_iniziale(self):
        # L'operatore inserisce il contante realmente contato: non blocchiamo se
        # differisce dal saldo di sistema (la differenza va registrata, non impedita).
        cassa_iniziale = self.cleaned_data.get('cassa_iniziale')
        if cassa_iniziale is None:
            raise forms.ValidationError("Inserisci il contante presente in cassa.")
        if cassa_iniziale <= 0:
            raise forms.ValidationError("La cassa iniziale deve essere maggiore di zero.")
        return cassa_iniziale


class ChiusuraDistintaForm(forms.ModelForm):
    class Meta:
        model = DistintaCassa
        fields = ['cassa_finale', 'totale_bevande', 'saldo_terminale', 'differenza_cassa', 'note_distinta', 'note_verifica']
        labels = {
            'totale_bevande': 'Saldo 2 (Bevande)',
        }
        widgets = {
            'cassa_finale': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            # Saldo 2 (Bevande): ammette anche valori negativi (nessun min)
            'totale_bevande': forms.NumberInput(attrs={'step': '0.01'}),
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


# ===========================================================================
# Conto Economico
# ===========================================================================

class CategoriaProdottoForm(forms.ModelForm):
    class Meta:
        model = CategoriaProdotto
        fields = ['nome', 'codice', 'ordine', 'attivo']
        help_texts = {'codice': 'Lascia vuoto per generarlo automaticamente dal nome.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codice'].required = False

    def clean_codice(self):
        from django.utils.text import slugify
        codice = self.cleaned_data.get('codice') or ''
        if not codice:
            codice = slugify(self.cleaned_data.get('nome', ''))
        return codice


class ProdottoRicavoForm(forms.ModelForm):
    class Meta:
        model = ProdottoRicavo
        fields = ['nome', 'codice', 'categoria_codice', 'ordine', 'attivo']
        help_texts = {
            'codice': 'Lascia vuoto per generarlo automaticamente dal nome.',
        }
        labels = {'categoria_codice': 'Categoria prodotto'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codice'].required = False
        cats = CategoriaProdotto.objects.using('default').filter(attivo=True).order_by('ordine', 'nome')
        self.fields['categoria_codice'] = forms.ChoiceField(
            choices=[('', '— Senza categoria —')] + [(c.codice, c.nome) for c in cats],
            required=False, label='Categoria prodotto',
            initial=(self.instance.categoria_codice if self.instance and self.instance.pk else ''))

    def clean_codice(self):
        from django.utils.text import slugify
        codice = self.cleaned_data.get('codice') or ''
        if not codice:
            codice = slugify(self.cleaned_data.get('nome', ''))
        return codice


class CategoriaSpesaForm(forms.ModelForm):
    class Meta:
        model = CategoriaSpesa
        fields = ['nome', 'codice', 'ordine', 'deducibile', 'attivo']
        help_texts = {
            'codice': 'Lascia vuoto per generarlo automaticamente dal nome.',
            'deducibile': 'Se attivo, concorre alla stima delle imposte.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codice'].required = False

    def clean_codice(self):
        from django.utils.text import slugify
        codice = self.cleaned_data.get('codice') or ''
        if not codice:
            codice = slugify(self.cleaned_data.get('nome', ''))
        return codice


class VoceCostoForm(forms.ModelForm):
    """Inserimento manuale di una voce di costo. La categoria attinge alla tassonomia globale."""
    class Meta:
        model = VoceCosto
        fields = ['categoria_codice', 'descrizione', 'importo', 'data']
        widgets = {
            'importo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'data': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {'categoria_codice': 'Categoria'}

    importo = forms.DecimalField(
        max_digits=12, decimal_places=2, localize=True,
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'class': 'form-control', 'placeholder': '0,00'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorie = CategoriaSpesa.objects.using('default').filter(attivo=True).order_by('ordine', 'nome')
        scelte = [('', '— Da classificare —')] + [(c.codice, c.nome) for c in categorie]
        self.fields['categoria_codice'] = forms.ChoiceField(
            choices=scelte, required=False, label='Categoria'
        )
        self.fields['descrizione'].required = True


class VoceRicavoManualeForm(forms.Form):
    """Voce di ricavo aggiuntiva/manuale (non legata a un prodotto)."""
    descrizione = forms.CharField(max_length=200, label='Descrizione')
    importo = forms.DecimalField(
        max_digits=12, decimal_places=2, localize=True,
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'class': 'form-control', 'placeholder': '0,00'}))


class UploadEstrattoForm(forms.Form):
    """Upload del CSV dell'estratto conto (elaborato in memoria, nessuno storage)."""
    file = forms.FileField(label='File CSV estratto conto',
                           widget=forms.ClearableFileInput(attrs={'accept': '.csv,text/csv,text/plain'}))


class ConsolidatoForm(forms.Form):
    """Selezione anno + mesi + agenzie per la vista consolidata (super-admin)."""
    anno = forms.IntegerField(min_value=2000, max_value=2100,
                              widget=forms.NumberInput(attrs={'class': 'form-control'}))
    mesi = forms.MultipleChoiceField(
        choices=MESI_CHOICES, widget=forms.CheckboxSelectMultiple, label='Mesi')
    agenzie = forms.ModelMultipleChoiceField(
        queryset=Agenzia.objects.using('default').filter(attiva=True).order_by('nome'),
        widget=forms.CheckboxSelectMultiple,
        label='Agenzie da includere',
    )
