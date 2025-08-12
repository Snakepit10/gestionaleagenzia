from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from .database_utils import MultiDatabaseMixin


def get_current_time():
    return timezone.localtime(timezone.now()).time()


class Agenzia(models.Model):
    """Modello per rappresentare le agenzie (goldbet, better, etc.)"""
    nome = models.CharField(max_length=100, unique=True)
    codice = models.CharField(max_length=20, unique=True, help_text="Codice agenzia per il database")
    database_name = models.CharField(max_length=100, help_text="Nome del database per questa agenzia")
    attiva = models.BooleanField(default=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Agenzia"
        verbose_name_plural = "Agenzie"
        ordering = ['nome']
    
    def __str__(self):
        return self.nome


class ProfiloUtente(models.Model):
    """Estende il modello User per collegarlo a un'agenzia"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    agenzia = models.ForeignKey(Agenzia, on_delete=models.CASCADE, related_name='utenti')
    
    class Meta:
        verbose_name = "Profilo Utente"
        verbose_name_plural = "Profili Utente"
    
    def __str__(self):
        return f"{self.user.username} - {self.agenzia.nome}"


class Cliente(MultiDatabaseMixin, models.Model):
    RATING_CHOICES = [
        ('A', 'Eccellente'),
        ('B', 'Buono'),
        ('C', 'Medio'),
        ('D', 'Rischio'),
        ('E', 'Alto Rischio'),
    ]

    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fido_massimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rating = models.CharField(max_length=1, choices=RATING_CHOICES, default='C')
    note = models.TextField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_modifica = models.DateTimeField(auto_now=True)
    creato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='clienti_creati')
    modificato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='clienti_modificati')

    @classmethod
    def calcola_saldo_complessivo(cls, user):
        """Calcola il saldo complessivo di tutti i clienti"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        return db.get_queryset(cls).aggregate(total=Sum('saldo'))['total'] or 0

    def aggiorna_saldo(self, user=None):
        """Ricalcola il saldo del cliente in base ai movimenti non saldati"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        if user:
            db = DatabaseManager(user)
            movimenti_sum = db.get_queryset(Movimento).filter(cliente=self, saldato=False).aggregate(Sum('importo'))['importo__sum']
            self.saldo = movimenti_sum if movimenti_sum is not None else 0
            db.save_object(self, update_fields=['saldo'])
        else:
            # Fallback per compatibilità - usa il MultiDatabaseMixin
            movimenti_sum = self.movimenti.filter(saldato=False).aggregate(Sum('importo'))['importo__sum']
            self.saldo = movimenti_sum if movimenti_sum is not None else 0
            self.save(update_fields=['saldo'])
    
    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clienti"
        ordering = ['cognome', 'nome']
    
    def __str__(self):
        return f"{self.cognome} {self.nome}"
    
    def calcola_rating(self):
        # Logica per calcolare automaticamente il rating
        # Basato su volume di gioco, puntualità pagamenti, frequenza
        # Da implementare successivamente
        pass
    
    @property
    def saldo_disponibile(self):
        """
        Ritorna il credito ancora disponibile entro il fido.
        Se il saldo è negativo, ritorna quanto ancora si può spendere entro il fido.
        Se il saldo è positivo, ritorna il fido + il saldo positivo.
        """
        if self.saldo < 0:
            # Saldo negativo: quanto ancora posso spendere
            return self.fido_massimo - abs(self.saldo)
        else:
            # Saldo positivo o zero: posso spendere il fido + il credito disponibile
            return self.fido_massimo + self.saldo

    @property
    def fido_superato(self):
        """
        Verifica se il cliente ha superato il fido.
        Ritorna True se il saldo negativo numericamente supera il fido massimo.
        Es: Se il fido è 50€ e il saldo è -55€, il cliente ha superato il fido di 5€.
        """
        return self.saldo < 0 and abs(self.saldo) > self.fido_massimo

    @property
    def importo_fido_superato(self):
        """
        Ritorna l'importo di cui il cliente ha superato il fido.
        Es: Se il fido è 50€ e il saldo è -55€, l'importo restituito è 5€.
        """
        if self.fido_superato:
            return abs(self.saldo) - self.fido_massimo
        return 0
    
    @property
    def nome_completo(self):
        return f"{self.cognome} {self.nome}"


class DistintaCassa(MultiDatabaseMixin, models.Model):
    STATO_CHOICES = [
        ('aperta', 'Aperta'),
        ('chiusa', 'Chiusa'),
        ('verificata', 'Verificata'),
    ]
    
    operatore = models.ForeignKey(User, on_delete=models.PROTECT, related_name='distinte_create')
    data = models.DateField(default=timezone.now)
    ora_inizio = models.TimeField(default=get_current_time)
    ora_fine = models.TimeField(null=True, blank=True)
    cassa_iniziale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cassa_finale = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    totale_entrate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    totale_uscite = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    totale_bevande = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_terminale = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    differenza_cassa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stato = models.CharField(max_length=10, choices=STATO_CHOICES, default='aperta')
    verificata_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='distinte_verificate')
    data_verifica = models.DateTimeField(null=True, blank=True)
    note_verifica = models.TextField(blank=True, null=True)
    note_distinta = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Distinta di Cassa"
        verbose_name_plural = "Distinte di Cassa"
        ordering = ['-data', '-ora_inizio']
    
    def __str__(self):
        return f"Distinta {self.pk} - {self.data} - {self.operatore.username}"
    
    def chiudi(self, user=None):
        from .database_utils import DatabaseManager
        
        self.ora_fine = timezone.localtime(timezone.now()).time()
        self.stato = 'chiusa'

        # Calcola saldo totale secondo la formula: cassa finale - entrate + uscite - bevande
        saldo_totale = self.cassa_finale - self.totale_entrate + self.totale_uscite - self.totale_bevande

        # Calcola differenza cassa (saldo totale - saldo terminale)
        self.differenza_cassa = saldo_totale

        # Se c'è un saldo terminale, consideralo nella differenza
        if self.saldo_terminale:
            self.differenza_cassa -= self.saldo_terminale

        if user:
            db = DatabaseManager(user)
            db.save_object(self)
        else:
            self.save()
    
    def verifica(self, utente):
        from .database_utils import DatabaseManager
        
        self.stato = 'verificata'
        self.verificata_da_id = utente.id
        self.data_verifica = timezone.now()
        
        db = DatabaseManager(utente)
        db.save_object(self)
        
        # Aggiorna automaticamente il saldo della cassa dopo la verifica
        ContoFinanziario.aggiorna_saldo_cassa_da_distinte(user=utente)
    
    @property
    def get_movimenti(self):
        return self.movimenti.all()


class Movimento(MultiDatabaseMixin, models.Model):
    TIPO_CHOICES = [
        ('schedina', 'Schedina'),
        ('ricarica', 'Ricarica'),
        ('prelievo', 'Prelievo'),
        ('incasso_credito', 'Incasso Credito'),
        ('pagamento_debito', 'Pagamento Debito'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='movimenti')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    importo = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateTimeField(default=timezone.now)
    saldato = models.BooleanField(default=False)
    distinta = models.ForeignKey(DistintaCassa, on_delete=models.PROTECT, related_name='movimenti')
    creato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='movimenti_creati')
    data_creazione = models.DateTimeField(auto_now_add=True)
    modificato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='movimenti_modificati')
    data_modifica = models.DateTimeField(auto_now=True)
    movimento_origine = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='movimento_saldo')
    note = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Movimento"
        verbose_name_plural = "Movimenti"
        ordering = ['-data']
    
    def __str__(self):
        return f"{self.tipo} - {self.cliente} - {self.importo} €"
    
    def save(self, *args, **kwargs):
        nuovo_record = self.pk is None

        # Se non è un nuovo record, salva il vecchio importo per aggiornare il saldo
        if not nuovo_record:
            try:
                # Usa il MultiDatabaseMixin per ottenere la query dal database corretto
                vecchio_movimento = self.__class__.objects.using(self._state.db).get(pk=self.pk)
                vecchio_importo = vecchio_movimento.importo
            except Movimento.DoesNotExist:
                vecchio_importo = 0

        # Cambiamo il segno dell'importo in base al tipo
        if self.tipo in ['schedina', 'ricarica', 'pagamento_debito']:
            self.importo = abs(self.importo) * -1  # Segno negativo (uscite)
        elif self.tipo in ['prelievo', 'incasso_credito']:
            self.importo = abs(self.importo)  # Segno positivo (entrate)

        # Salviamo il record
        super().save(*args, **kwargs)

        # Aggiorniamo il saldo usando il metodo di ricalcolo completo
        self.cliente.aggiorna_saldo()
    
    def salda(self, utente):
        """
        Marca questo movimento come saldato, crea un movimento opposto nella distinta corrente
        e aggiorna il saldo del cliente
        """
        if self.saldato:
            return False

        # Ottieni la distinta corrente dell'utente
        from django.utils import timezone
        try:
            # Usa il database corretto basato sull'utente
            from .database_utils import DatabaseManager
            db = DatabaseManager(utente)
            distinta_corrente = db.get_queryset(DistintaCassa).filter(
                operatore=utente,
                stato='aperta'
            ).latest('data', 'ora_inizio')
        except DistintaCassa.DoesNotExist:
            # Se non c'è una distinta aperta, non possiamo saldare
            return False

        # Crea un movimento opposto nella distinta corrente per registrare il pagamento
        from django.db import models
        from decimal import Decimal

        # Per il movimento opposto, dobbiamo invertire il segno rispetto al tipo
        # Se il movimento originale è una schedina/ricarica (importo negativo)
        # il movimento di saldo sarà positivo (entrata di cassa)
        # Se il movimento originale è un prelievo (importo positivo)
        # il movimento di saldo sarà negativo (uscita di cassa)

        # Creiamo un nuovo tipo di movimento per rappresentare il saldo
        # ma manteniamo il riferimento al tipo originale
        tipo_movimento = self.tipo

        # L'importo avrà il segno opposto rispetto al movimento originale
        # ma dobbiamo passarlo in modo che il metodo save() lo gestisca correttamente
        # Il metodo save() inverte il segno in base al tipo
        if self.importo < 0:  # Movimento originale è negativo (schedina/ricarica)
            # Per schedina/ricarica (importo negativo) creiamo un incasso credito (importo positivo)
            tipo_movimento = 'incasso_credito'
            importo_da_salvare = abs(self.importo)  # Sarà positivo (entrata di cassa)
        else:  # Movimento originale è positivo (prelievo)
            # Per prelievo (importo positivo) creiamo un pagamento debito (importo negativo)
            tipo_movimento = 'pagamento_debito'
            importo_da_salvare = abs(self.importo)  # Sarà negativo (uscita di cassa)

        # Prepariamo messaggio informativo per il movimento di compensazione
        if self.importo < 0:  # Schedina o ricarica
            note_movimento = f"Incasso credito per saldo movimento #{self.id} ({self.get_tipo_display()}) del {self.data.strftime('%d/%m/%Y')}"
        else:  # Prelievo
            note_movimento = f"Pagamento debito per saldo movimento #{self.id} ({self.get_tipo_display()}) del {self.data.strftime('%d/%m/%Y')}"

        # Creiamo il nuovo movimento di compensazione
        movimento_opposto = Movimento(
            cliente=self.cliente,
            tipo=tipo_movimento,  # Modifichiamo il tipo per ottenere il segno corretto
            importo=importo_da_salvare,
            distinta=distinta_corrente,
            creato_da_id=utente.id,
            modificato_da_id=utente.id,
            movimento_origine=self,  # Riferimento al movimento originale
            saldato=True,  # Il movimento di compensazione è già saldato
            note=note_movimento  # Ora possiamo salvare la nota
        )

        # Salviamo il movimento usando il database manager
        db.save_object(movimento_opposto)

        # Marchiamo questo movimento come saldato
        self.saldato = True
        self.modificato_da_id = utente.id

        # Salviamo il record usando il database corretto
        db.save_object(self)

        # Aggiorna il saldo del cliente manualmente
        self.cliente.aggiorna_saldo(user=utente)

        return True

    def delete(self, user=None, *args, **kwargs):
        """Override delete to update cliente's saldo after deletion"""
        cliente = self.cliente
        super().delete(*args, **kwargs)
        if user:
            cliente.aggiorna_saldo(user=user)
        else:
            cliente.aggiorna_saldo()


class Comunicazione(MultiDatabaseMixin, models.Model):
    TIPO_CHOICES = [
        ('avviso', 'Avviso'),
        ('sollecito', 'Sollecito'),
        ('informativa', 'Informativa'),
    ]

    STATO_CHOICES = [
        ('non_letta', 'Non Letta'),
        ('letta', 'Letta'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='comunicazioni')
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES)
    contenuto = models.TextField()
    data = models.DateTimeField(auto_now_add=True)
    operatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='comunicazioni_inviate')
    stato = models.CharField(max_length=10, choices=STATO_CHOICES, default='non_letta')

    class Meta:
        verbose_name = "Comunicazione"
        verbose_name_plural = "Comunicazioni"
        ordering = ['-data']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cliente} - {self.data.strftime('%d/%m/%Y')}"

    def marca_come_letta(self, user=None):
        from .database_utils import DatabaseManager
        
        self.stato = 'letta'
        if user:
            db = DatabaseManager(user)
            db.save_object(self)
        else:
            self.save()


class ContoFinanziario(MultiDatabaseMixin, models.Model):
    TIPO_CHOICES = [
        ('cassa', 'Cassa'),
        ('banca', 'Conto Bancario'),
        ('online', 'Conto Online'),
        ('clienti', 'Crediti Clienti'),
        ('agenti', 'Saldo Agent'),
        ('spese', 'Spese'),
        ('ricavi', 'Ricavi'),
        ('prelievi', 'Prelievi Soci'),
        ('versamenti', 'Versamenti Soci'),
        ('altro', 'Altro'),
    ]

    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    saldo = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    descrizione = models.TextField(blank=True, null=True)
    creato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='conti_creati')
    data_creazione = models.DateTimeField(auto_now_add=True)
    modificato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='conti_modificati')
    data_modifica = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conto Finanziario"
        verbose_name_plural = "Conti Finanziari"
        ordering = ['tipo', 'nome']

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"

    @classmethod
    def calcola_saldo_totale(cls, user):
        """Calcola il saldo totale di tutti i conti finanziari"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        return db.get_queryset(cls).aggregate(total=Sum('saldo'))['total'] or 0

    @classmethod
    def calcola_saldo_per_tipo(cls, user, tipo):
        """Calcola il saldo totale per un tipo specifico di conto"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        return db.get_queryset(cls).filter(tipo=tipo).aggregate(total=Sum('saldo'))['total'] or 0

    @classmethod
    def aggiorna_saldo_cassa_da_distinte(cls, user):
        """Aggiorna il saldo della cassa agenzia considerando distinte chiuse e movimenti successivi"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        
        try:
            conto_cassa = db.get_queryset(cls).get(tipo='cassa', nome='Cassa Agenzia')
            
            # Trova l'ultima distinta chiusa nel database dell'utente
            ultima_distinta = db.get_queryset(DistintaCassa).filter(stato='chiusa').order_by('-data', '-ora_inizio').first()
            
            if ultima_distinta:
                # Usa la cassa finale dell'ultima distinta chiusa come base
                saldo_base = ultima_distinta.cassa_finale
                
                # Calcola data/ora di chiusura della distinta per filtrare movimenti successivi
                data_chiusura = timezone.make_aware(
                    timezone.datetime.combine(ultima_distinta.data, ultima_distinta.ora_fine or ultima_distinta.ora_inizio)
                )
                
                # Somma movimenti DOPO la chiusura della distinta
                movimenti_entrata = db.get_queryset(MovimentoConti).filter(
                    conto_destinazione=conto_cassa,
                    data__gt=data_chiusura
                ).aggregate(total=Sum('importo'))['total'] or 0
                
                movimenti_uscita = db.get_queryset(MovimentoConti).filter(
                    conto_origine=conto_cassa,
                    data__gt=data_chiusura
                ).aggregate(total=Sum('importo'))['total'] or 0
                
                # Calcola il nuovo saldo: base + entrate - uscite
                nuovo_saldo = saldo_base + movimenti_entrata - movimenti_uscita
                
            else:
                # Se non ci sono distinte chiuse, calcola da tutti i movimenti
                movimenti_entrata = db.get_queryset(MovimentoConti).filter(
                    conto_destinazione=conto_cassa
                ).aggregate(total=Sum('importo'))['total'] or 0
                
                movimenti_uscita = db.get_queryset(MovimentoConti).filter(
                    conto_origine=conto_cassa
                ).aggregate(total=Sum('importo'))['total'] or 0
                
                nuovo_saldo = movimenti_entrata - movimenti_uscita
            
            # Aggiorna il saldo del conto cassa
            conto_cassa.saldo = nuovo_saldo
            db.save_object(conto_cassa)
            
            return nuovo_saldo
            
        except cls.DoesNotExist:
            return 0

    @classmethod
    def crea_conti_default(cls, user):
        """Crea i conti predefiniti se non esistono nel database dell'agenzia"""
        from .database_utils import DatabaseManager
        
        # Usa il DatabaseManager per il database corretto
        db = DatabaseManager(user)
        
        conti_default = [
            ('Cassa Agenzia', 'cassa', 'Contante fisico presente in agenzia'),
            ('Conto Corrente Principale', 'banca', 'Conto corrente aziendale principale'),
            ('Conto Gioco Online', 'online', 'Saldo disponibile su piattaforme di gioco online'),
            ('Saldo Clienti', 'clienti', 'Crediti/debiti verso clienti calcolato automaticamente'),
            ('Saldo Agent', 'agenti', 'Crediti/debiti verso agent'),
            ('Spese Generali', 'spese', 'Spese di gestione e amministrazione'),
            ('Ricavi Operativi', 'ricavi', 'Ricavi generati dall\'attività'),
            ('Prelievi Soci', 'prelievi', 'Prelievi effettuati dai soci'),
            ('Versamenti Soci', 'versamenti', 'Versamenti effettuati dai soci')
        ]

        # Ottieni il saldo totale dei clienti dal database dell'agenzia
        saldo_clienti = Cliente.calcola_saldo_complessivo(user)

        for nome, tipo, descrizione in conti_default:
            # Controlla se il conto esiste già nel database dell'agenzia
            conto_esistente = db.get_queryset(cls).filter(nome=nome, tipo=tipo).first()
            
            if not conto_esistente:
                # Crea il nuovo conto nel database dell'agenzia
                conto = cls(
                    nome=nome,
                    tipo=tipo,
                    descrizione=descrizione,
                    creato_da_id=user.id,
                    modificato_da_id=user.id,
                    saldo=saldo_clienti if tipo == 'clienti' else 0
                )
                db.save_object(conto)
                print(f"Creato conto {nome} nel database {db.user_db}")
                created = True
            else:
                conto = conto_esistente
                created = False

            # Se il conto clienti esiste già, aggiorna comunque il saldo
            if not created and tipo == 'clienti':
                conto.saldo = saldo_clienti
                db.save_object(conto)


class MovimentoConti(MultiDatabaseMixin, models.Model):
    TIPO_CHOICES = [
        ('deposito', 'Deposito'),
        ('prelievo', 'Prelievo'),
        ('giroconto', 'Giroconto'),
        ('modifica', 'Modifica Diretta'),
    ]

    data = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    importo = models.DecimalField(max_digits=15, decimal_places=2)
    conto_origine = models.ForeignKey(ContoFinanziario, on_delete=models.PROTECT, related_name='movimenti_uscita', null=True, blank=True)
    conto_destinazione = models.ForeignKey(ContoFinanziario, on_delete=models.PROTECT, related_name='movimenti_entrata', null=True, blank=True)
    saldo_origine_pre = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    saldo_origine_post = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    saldo_destinazione_pre = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    saldo_destinazione_post = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True, null=True)
    operatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='movimenti_conti')

    class Meta:
        verbose_name = "Movimento tra Conti"
        verbose_name_plural = "Movimenti tra Conti"
        ordering = ['-data']

    def __str__(self):
        if self.tipo == 'giroconto':
            return f"Giroconto di {self.importo} € da {self.conto_origine} a {self.conto_destinazione} ({self.data.strftime('%d/%m/%Y %H:%M')})"
        elif self.tipo == 'deposito':
            return f"Deposito di {self.importo} € su {self.conto_destinazione} ({self.data.strftime('%d/%m/%Y %H:%M')})"
        elif self.tipo == 'prelievo':
            return f"Prelievo di {self.importo} € da {self.conto_origine} ({self.data.strftime('%d/%m/%Y %H:%M')})"
        else:
            return f"Modifica di {self.importo} € su {self.conto_origine or self.conto_destinazione} ({self.data.strftime('%d/%m/%Y %H:%M')})"

    @classmethod
    def registra_modifica_diretta(cls, conto, importo_precedente, importo_nuovo, operatore, note=None):
        """Registra una modifica diretta del saldo di un conto"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(operatore)
        differenza = importo_nuovo - importo_precedente

        movimento = cls(
            tipo='modifica',
            importo=abs(differenza),
            conto_origine=conto if differenza < 0 else None,
            conto_destinazione=conto if differenza >= 0 else None,
            saldo_origine_pre=importo_precedente if differenza < 0 else None,
            saldo_origine_post=importo_nuovo if differenza < 0 else None,
            saldo_destinazione_pre=importo_precedente if differenza >= 0 else None,
            saldo_destinazione_post=importo_nuovo if differenza >= 0 else None,
            note=note,
            operatore_id=operatore.id
        )
        
        db.save_object(movimento)
        return movimento

    @classmethod
    def registra_giroconto(cls, conto_origine, conto_destinazione, importo, operatore, note=None):
        """Registra un giroconto tra due conti"""
        from .database_utils import DatabaseManager
        
        if importo <= 0:
            raise ValueError("L'importo deve essere positivo")

        db = DatabaseManager(operatore)
        
        # Salva i saldi precedenti
        saldo_origine_pre = conto_origine.saldo
        saldo_destinazione_pre = conto_destinazione.saldo

        # Aggiorna i saldi
        conto_origine.saldo -= importo
        conto_destinazione.saldo += importo

        # Salva i conti nel database corretto
        db.save_object(conto_origine)
        db.save_object(conto_destinazione)

        # Registra il movimento
        movimento = cls(
            tipo='giroconto',
            importo=importo,
            conto_origine=conto_origine,
            conto_destinazione=conto_destinazione,
            saldo_origine_pre=saldo_origine_pre,
            saldo_origine_post=conto_origine.saldo,
            saldo_destinazione_pre=saldo_destinazione_pre,
            saldo_destinazione_post=conto_destinazione.saldo,
            note=note,
            operatore_id=operatore.id
        )
        
        db.save_object(movimento)
        return movimento

    def delete(self, user=None, *args, **kwargs):
        """Override delete to revert account balances"""
        from .database_utils import DatabaseManager
        
        # Ripristina i saldi precedenti quando si elimina un movimento
        if user:
            db = DatabaseManager(user)
            
            if self.tipo == 'giroconto':
                if self.conto_origine and self.saldo_origine_pre is not None:
                    self.conto_origine.saldo = self.saldo_origine_pre
                    db.save_object(self.conto_origine)
                if self.conto_destinazione and self.saldo_destinazione_pre is not None:
                    self.conto_destinazione.saldo = self.saldo_destinazione_pre
                    db.save_object(self.conto_destinazione)
            elif self.tipo == 'modifica':
                # Per le modifiche dirette, ripristina il saldo precedente
                if self.conto_origine and self.saldo_origine_pre is not None:
                    self.conto_origine.saldo = self.saldo_origine_pre
                    db.save_object(self.conto_origine)
                elif self.conto_destinazione and self.saldo_destinazione_pre is not None:
                    self.conto_destinazione.saldo = self.saldo_destinazione_pre
                    db.save_object(self.conto_destinazione)
        else:
            # Fallback per compatibilità
            if self.tipo == 'giroconto':
                if self.conto_origine and self.saldo_origine_pre is not None:
                    self.conto_origine.saldo = self.saldo_origine_pre
                    self.conto_origine.save()
                if self.conto_destinazione and self.saldo_destinazione_pre is not None:
                    self.conto_destinazione.saldo = self.saldo_destinazione_pre
                    self.conto_destinazione.save()
            elif self.tipo == 'modifica':
                # Per le modifiche dirette, ripristina il saldo precedente
                if self.conto_origine and self.saldo_origine_pre is not None:
                    self.conto_origine.saldo = self.saldo_origine_pre
                    self.conto_origine.save()
                elif self.conto_destinazione and self.saldo_destinazione_pre is not None:
                    self.conto_destinazione.saldo = self.saldo_destinazione_pre
                    self.conto_destinazione.save()
        
        super().delete(*args, **kwargs)


class BilancioPeriodico(MultiDatabaseMixin, models.Model):
    data_riferimento = models.DateTimeField(default=timezone.now)
    saldo_totale = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_clienti = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_online = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_agenti = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_cassa = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_banca = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_ricavi = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_spese = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_prelievi = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_versamenti = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    saldo_altro = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    note = models.TextField(blank=True, null=True)
    creato_da = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bilanci_creati')

    class Meta:
        verbose_name = "Bilancio Periodico"
        verbose_name_plural = "Bilanci Periodici"
        ordering = ['-data_riferimento']

    def __str__(self):
        return f"Bilancio del {self.data_riferimento.strftime('%d/%m/%Y %H:%M')}"

    def differenza_precedente(self, user=None):
        """Calcola la differenza rispetto al bilancio precedente"""
        from decimal import Decimal
        from .database_utils import DatabaseManager
        
        try:
            if user:
                db = DatabaseManager(user)
                precedente = db.get_queryset(BilancioPeriodico).filter(
                    data_riferimento__lt=self.data_riferimento
                ).latest('data_riferimento')
            else:
                # Fallback per compatibilità
                precedente = BilancioPeriodico.objects.filter(
                    data_riferimento__lt=self.data_riferimento
                ).latest('data_riferimento')
            return self.saldo_totale - precedente.saldo_totale
        except BilancioPeriodico.DoesNotExist:
            return Decimal('0.00')

    @property
    def stato_liquidita(self):
        """Determina lo stato della liquidità basato sulla differenza col bilancio precedente"""
        diff = self.differenza_precedente
        if diff < 0:
            return 'ammanco'
        elif diff > 0:
            return 'surplus'
        else:
            return 'stabile'

    @classmethod
    def crea_bilancio(cls, user, note=None):
        """Crea un nuovo bilancio con i saldi correnti"""
        from .database_utils import DatabaseManager
        
        # Calcola i saldi per ogni tipo di conto
        saldi = {}
        for tipo, _ in ContoFinanziario.TIPO_CHOICES:
            saldi[f'saldo_{tipo}'] = ContoFinanziario.calcola_saldo_per_tipo(user, tipo)

        # Calcola il saldo totale
        saldo_totale = ContoFinanziario.calcola_saldo_totale(user)

        # Aggiorna anche con il saldo clienti dal modello Cliente
        saldo_clienti_model = Cliente.calcola_saldo_complessivo(user)

        # Crea il nuovo bilancio nel database dell'utente
        db = DatabaseManager(user)
        bilancio = cls(
            saldo_totale=saldo_totale,
            saldo_clienti=saldi['saldo_clienti'] or saldo_clienti_model,  # Usa uno dei due valori
            saldo_online=saldi['saldo_online'],
            saldo_agenti=saldi['saldo_agenti'],
            saldo_cassa=saldi['saldo_cassa'],
            saldo_banca=saldi['saldo_banca'],
            saldo_ricavi=saldi['saldo_ricavi'],
            saldo_spese=saldi['saldo_spese'],
            saldo_prelievi=saldi['saldo_prelievi'],
            saldo_versamenti=saldi['saldo_versamenti'],
            saldo_altro=saldi.get('saldo_altro', 0),
            note=note,
            creato_da_id=user.id
        )
        
        db.save_object(bilancio)
        return bilancio


class ActivityLog(MultiDatabaseMixin, models.Model):
    """
    Modello per registrare le attività e modifiche effettuate ai movimenti e alle distinte.
    Utilizza il sistema di contenttypes di Django per relazioni generiche.
    """

    ACTION_CHOICES = [
        ('create', 'Creazione'),
        ('update', 'Modifica'),
        ('delete', 'Eliminazione'),
        ('status_change', 'Cambio di stato'),
        ('payment', 'Pagamento'),
        ('reopen', 'Riapertura'),
    ]

    # Utente che ha eseguito l'azione
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')

    # Tipo di azione eseguita
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # Timestamp dell'azione
    timestamp = models.DateTimeField(auto_now_add=True)

    # Descrizione dell'azione
    description = models.TextField()

    # Campo per memorizzare i dati precedenti in formato JSON (opzionale)
    data_before = models.JSONField(null=True, blank=True)

    # Campo per memorizzare i dati dopo la modifica in formato JSON (opzionale)
    data_after = models.JSONField(null=True, blank=True)

    # Campi per la relazione generica (può puntare a Movimento o DistintaCassa)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = "Log Attività"
        verbose_name_plural = "Log Attività"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} di {self.content_type} #{self.object_id} da {self.user.username} il {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

    @classmethod
    def log_action(cls, user, obj, action, description=None, data_before=None, data_after=None):
        """
        Metodo di utilità per registrare facilmente un'azione nei log.

        Args:
            user: L'utente che ha eseguito l'azione
            obj: L'oggetto su cui è stata eseguita l'azione (Movimento o DistintaCassa)
            action: Il tipo di azione (create, update, delete, ecc.)
            description: Descrizione opzionale dell'azione
            data_before: Dati opzionali prima dell'azione
            data_after: Dati opzionali dopo l'azione

        Returns:
            L'istanza di ActivityLog creata
        """

        # Se non è fornita una descrizione, creane una predefinita
        if description is None:
            if action == 'create':
                description = f"Creazione di {obj._meta.verbose_name} #{obj.pk}"
            elif action == 'update':
                description = f"Modifica di {obj._meta.verbose_name} #{obj.pk}"
            elif action == 'delete':
                description = f"Eliminazione di {obj._meta.verbose_name} #{obj.pk}"
            elif action == 'status_change':
                description = f"Cambio di stato di {obj._meta.verbose_name} #{obj.pk}"
            elif action == 'payment':
                description = f"Pagamento di {obj._meta.verbose_name} #{obj.pk}"
            elif action == 'reopen':
                description = f"Riapertura di {obj._meta.verbose_name} #{obj.pk}"

        # Crea e salva il log
        from .database_utils import DatabaseManager
        from django.contrib.contenttypes.models import ContentType
        
        log = cls(
            user=user,
            action=action,
            description=description,
            data_before=data_before,
            data_after=data_after,
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk
        )
        
        # Usa DatabaseManager per salvare nel database corretto
        db = DatabaseManager(user)
        db.save_object(log)

        return log