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
    
    CATEGORIA_CHOICES = [
        # STATO FINANZIARIO
        ('liquidita', 'Liquidità'),  # Cassa, Banche
        ('crediti', 'Crediti'),      # Da clienti, agenti
        ('debiti', 'Debiti'),        # Verso fornitori, agenti
        
        # GESTIONE (per calcolo utile/imposte)
        ('ricavi', 'Ricavi'),                # Commissioni, vendite
        ('costi', 'Costi Operativi'),       # Affitto, utenze, personale
        ('imposte', 'Imposte e Tasse'),     # Per tracking separato
    ]

    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='liquidita', help_text="Categoria contabile per bilancio")
    saldo = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tassabile = models.BooleanField(default=True, help_text="Concorre al calcolo delle imposte")
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
    def calcola_saldo_per_categoria(cls, user, categoria, tassabile=None):
        """Calcola il saldo totale per una categoria contabile"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        queryset = db.get_queryset(cls).filter(categoria=categoria)
        
        if tassabile is not None:
            queryset = queryset.filter(tassabile=tassabile)
            
        return queryset.aggregate(total=Sum('saldo'))['total'] or 0
    
    @classmethod
    def calcola_situazione_fiscale(cls, user):
        """Calcola utile lordo e stima imposte"""
        ricavi_tassabili = cls.calcola_saldo_per_categoria(user, 'ricavi', tassabile=True)
        costi_deducibili = cls.calcola_saldo_per_categoria(user, 'costi', tassabile=True)
        
        utile_lordo = ricavi_tassabili - costi_deducibili
        stima_imposte = max(0, utile_lordo * 0.24)  # IRPEF + addizionali stimate (24%)
        
        return {
            'ricavi_tassabili': ricavi_tassabili,
            'costi_deducibili': costi_deducibili,
            'utile_lordo': utile_lordo,
            'stima_imposte': stima_imposte,
            'utile_netto_stimato': utile_lordo - stima_imposte
        }
    
    @classmethod
    def calcola_situazione_finanziaria(cls, user):
        """Calcola situazione finanziaria (liquidità disponibile)"""
        liquidita = cls.calcola_saldo_per_categoria(user, 'liquidita')
        crediti = cls.calcola_saldo_per_categoria(user, 'crediti')
        debiti = cls.calcola_saldo_per_categoria(user, 'debiti')
        imposte_accantonate = cls.calcola_saldo_per_categoria(user, 'imposte')
        
        situazione_fiscale = cls.calcola_situazione_fiscale(user)
        
        return {
            'liquidita': liquidita,
            'crediti': crediti,
            'debiti': debiti,
            'imposte_accantonate': imposte_accantonate,
            'situazione_finanziaria_netta': liquidita + crediti - debiti,
            'liquidita_effettiva': liquidita - situazione_fiscale['stima_imposte'] + imposte_accantonate,
        }

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


class SnapshotSaldoCassa(MultiDatabaseMixin, models.Model):
    """Storicizza gli snapshots del saldo cassa agenzia per audit e tracciabilità"""
    
    data_snapshot = models.DateTimeField(default=timezone.now)
    saldo_precedente = models.DecimalField(max_digits=15, decimal_places=2)
    saldo_nuovo = models.DecimalField(max_digits=15, decimal_places=2)
    differenza = models.DecimalField(max_digits=15, decimal_places=2)
    causale = models.CharField(max_length=100, help_text="Motivo della variazione")
    riferimento_id = models.PositiveIntegerField(null=True, blank=True, help_text="ID del record correlato (distinta, movimento, etc.)")
    riferimento_tipo = models.CharField(max_length=50, null=True, blank=True, help_text="Tipo di record correlato")
    operatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='snapshots_cassa')
    note = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = "Snapshot Saldo Cassa"
        verbose_name_plural = "Snapshots Saldo Cassa"
        ordering = ['-data_snapshot']
    
    def __str__(self):
        return f"Cassa: {self.saldo_precedente} → {self.saldo_nuovo} € ({self.causale}) - {self.data_snapshot.strftime('%d/%m/%Y %H:%M')}"
    
    @classmethod
    def registra_snapshot(cls, saldo_precedente, saldo_nuovo, causale, operatore, riferimento_id=None, riferimento_tipo=None, note=None):
        """Registra un nuovo snapshot del saldo cassa"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(operatore)
        
        snapshot = cls(
            saldo_precedente=saldo_precedente,
            saldo_nuovo=saldo_nuovo,
            differenza=saldo_nuovo - saldo_precedente,
            causale=causale,
            riferimento_id=riferimento_id,
            riferimento_tipo=riferimento_tipo,
            operatore=operatore,
            note=note
        )
        
        db.save_object(snapshot)
        return snapshot
    
    @classmethod
    def get_ultimo_saldo(cls, user):
        """Recupera l'ultimo saldo registrato"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        ultimo_snapshot = db.get_queryset(cls).first()
        
        if ultimo_snapshot:
            return ultimo_snapshot.saldo_nuovo
        else:
            return 0


class MovimentoCassa(MultiDatabaseMixin, models.Model):
    """Traccia tutti i movimenti che influenzano la cassa agenzia"""
    
    TIPO_MOVIMENTO_CHOICES = [
        ('apertura_distinta', 'Apertura Distinta'),
        ('chiusura_distinta', 'Chiusura Distinta'),
        ('verifica_distinta', 'Verifica Distinta'),
        ('giroconto_entrata', 'Giroconto in Entrata'),
        ('giroconto_uscita', 'Giroconto in Uscita'),
        ('deposito', 'Deposito Manuale'),
        ('prelievo', 'Prelievo Manuale'),
        ('correzione', 'Correzione Manuale'),
        ('inizializzazione', 'Inizializzazione Sistema'),
    ]
    
    data_movimento = models.DateTimeField(default=timezone.now)
    tipo_movimento = models.CharField(max_length=30, choices=TIPO_MOVIMENTO_CHOICES)
    importo = models.DecimalField(max_digits=15, decimal_places=2, help_text="Positivo per entrate, negativo per uscite")
    saldo_precedente = models.DecimalField(max_digits=15, decimal_places=2)
    saldo_nuovo = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Collegamenti ai record correlati
    distinta = models.ForeignKey(DistintaCassa, on_delete=models.PROTECT, null=True, blank=True, related_name='movimenti_cassa')
    movimento_conti = models.ForeignKey(MovimentoConti, on_delete=models.PROTECT, null=True, blank=True, related_name='movimenti_cassa')
    
    descrizione = models.TextField(help_text="Descrizione dettagliata del movimento")
    operatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='movimenti_cassa')
    
    class Meta:
        verbose_name = "Movimento Cassa"
        verbose_name_plural = "Movimenti Cassa"
        ordering = ['-data_movimento']
    
    def __str__(self):
        simbolo = "+" if self.importo >= 0 else ""
        return f"{simbolo}{self.importo} € - {self.get_tipo_movimento_display()} ({self.data_movimento.strftime('%d/%m/%Y %H:%M')})"
    
    @classmethod
    def registra_movimento(cls, tipo_movimento, importo, saldo_precedente, descrizione, operatore, distinta=None, movimento_conti=None):
        """Registra un nuovo movimento cassa"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(operatore)
        saldo_nuovo = saldo_precedente + importo
        
        movimento = cls(
            tipo_movimento=tipo_movimento,
            importo=importo,
            saldo_precedente=saldo_precedente,
            saldo_nuovo=saldo_nuovo,
            distinta=distinta,
            movimento_conti=movimento_conti,
            descrizione=descrizione,
            operatore=operatore
        )
        
        db.save_object(movimento)
        
        # Registra anche il snapshot
        SnapshotSaldoCassa.registra_snapshot(
            saldo_precedente=saldo_precedente,
            saldo_nuovo=saldo_nuovo,
            causale=movimento.get_tipo_movimento_display(),
            operatore=operatore,
            riferimento_id=movimento.pk,
            riferimento_tipo='MovimentoCassa',
            note=descrizione
        )
        
        return movimento, saldo_nuovo
    
    @classmethod
    def calcola_saldo_attuale(cls, user):
        """Calcola il saldo attuale dalla somma progressiva di tutti i movimenti"""
        from django.db.models import Sum
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        
        # Alternativa 1: usa l'ultimo movimento registrato
        ultimo_movimento = db.get_queryset(cls).first()
        if ultimo_movimento:
            return ultimo_movimento.saldo_nuovo
        
        # Alternativa 2: calcola dalla somma (più sicura per verifiche)
        totale_movimenti = db.get_queryset(cls).aggregate(
            total=Sum('importo')
        )['total'] or 0
        
        return totale_movimenti


class ControlloQuadratura(MultiDatabaseMixin, models.Model):
    """Sistema di controllo quadratura per verificare coerenza saldi"""
    
    STATO_CHOICES = [
        ('in_corso', 'Controllo in Corso'),
        ('quadrato', 'Quadrato'),
        ('differenza', 'Con Differenze'),
        ('ammanco', 'Ammanco Rilevato'),
    ]
    
    data_controllo = models.DateTimeField(default=timezone.now)
    operatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='controlli_quadratura')
    
    # Riferimenti temporali del periodo controllato
    data_inizio_periodo = models.DateTimeField(help_text="Inizio periodo di controllo")
    data_fine_periodo = models.DateTimeField(help_text="Fine periodo di controllo")
    
    # Saldi di controllo
    saldo_iniziale = models.DecimalField(max_digits=15, decimal_places=2, help_text="Saldo all'inizio del periodo")
    saldo_finale_reale = models.DecimalField(max_digits=15, decimal_places=2, help_text="Saldo effettivo rilevato")
    saldo_finale_calcolato = models.DecimalField(max_digits=15, decimal_places=2, help_text="Saldo teorico da movimenti")
    
    differenza = models.DecimalField(max_digits=15, decimal_places=2, help_text="Ammanco/Surplus rilevato", editable=False)
    
    # Dettaglio movimenti nel periodo
    totale_entrate = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    totale_uscite = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    numero_movimenti = models.IntegerField(default=0)
    
    # Controllo specifico
    conto_controllato = models.ForeignKey(ContoFinanziario, on_delete=models.PROTECT, null=True, blank=True, help_text="Conto specifico controllato")
    controllo_generale = models.BooleanField(default=True, help_text="True se controllo generale, False se su conto specifico")
    
    note_controllo = models.TextField(blank=True, null=True)
    stato = models.CharField(max_length=20, choices=STATO_CHOICES, default='in_corso')
    
    class Meta:
        verbose_name = "Controllo Quadratura"
        verbose_name_plural = "Controlli Quadratura"
        ordering = ['-data_controllo']
    
    def save(self, *args, **kwargs):
        # Calcola automaticamente la differenza
        self.differenza = self.saldo_finale_reale - self.saldo_finale_calcolato
        
        # Determina lo stato automaticamente
        if abs(self.differenza) < 0.01:  # Considera quadrato se differenza < 1 centesimo
            self.stato = 'quadrato'
        elif self.differenza < 0:
            self.stato = 'ammanco'
        else:
            self.stato = 'differenza'
            
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.controllo_generale:
            return f"Controllo Generale - {self.data_controllo.strftime('%d/%m/%Y %H:%M')} - {self.get_stato_display()}"
        else:
            return f"Controllo {self.conto_controllato} - {self.data_controllo.strftime('%d/%m/%Y %H:%M')} - {self.get_stato_display()}"
    
    @classmethod
    def esegui_controllo_cassa(cls, user, saldo_reale_rilevato, data_ultimo_controllo=None):
        """Esegue controllo di quadratura specifico per la cassa agenzia"""
        from .database_utils import DatabaseManager
        from django.db.models import Sum
        
        db = DatabaseManager(user)
        
        # Determina il periodo di controllo
        if data_ultimo_controllo:
            data_inizio = data_ultimo_controllo
        else:
            # Se è il primo controllo, usa la data del primo movimento
            primo_movimento = db.get_queryset(MovimentoCassa).last()
            data_inizio = primo_movimento.data_movimento if primo_movimento else timezone.now() - timezone.timedelta(days=30)
        
        data_fine = timezone.now()
        
        # Recupera conto cassa agenzia
        try:
            conto_cassa = db.get_queryset(ContoFinanziario).get(tipo='cassa', nome='Cassa Agenzia')
        except ContoFinanziario.DoesNotExist:
            raise ValueError("Conto Cassa Agenzia non trovato")
        
        # Calcola saldo iniziale (dall'ultimo controllo o dal sistema)
        ultimo_controllo = db.get_queryset(cls).filter(
            conto_controllato=conto_cassa
        ).first()
        
        saldo_iniziale = ultimo_controllo.saldo_finale_reale if ultimo_controllo else 0
        
        # Calcola movimenti nel periodo
        movimenti_periodo = db.get_queryset(MovimentoCassa).filter(
            data_movimento__gte=data_inizio,
            data_movimento__lte=data_fine
        )
        
        totale_entrate = movimenti_periodo.filter(importo__gt=0).aggregate(
            total=Sum('importo')
        )['total'] or 0
        
        totale_uscite = abs(movimenti_periodo.filter(importo__lt=0).aggregate(
            total=Sum('importo')
        )['total'] or 0)
        
        saldo_finale_calcolato = saldo_iniziale + totale_entrate - totale_uscite
        
        # Crea il controllo
        controllo = cls(
            operatore=user,
            data_inizio_periodo=data_inizio,
            data_fine_periodo=data_fine,
            saldo_iniziale=saldo_iniziale,
            saldo_finale_reale=saldo_reale_rilevato,
            saldo_finale_calcolato=saldo_finale_calcolato,
            totale_entrate=totale_entrate,
            totale_uscite=totale_uscite,
            numero_movimenti=movimenti_periodo.count(),
            conto_controllato=conto_cassa,
            controllo_generale=False
        )
        
        db.save_object(controllo)
        return controllo
    
    @classmethod
    def esegui_controllo_generale(cls, user, saldi_reali_per_categoria):
        """Esegue controllo di quadratura generale su tutte le categorie"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        
        # Calcola situazione teorica
        situazione_teorica = ContoFinanziario.calcola_situazione_finanziaria(user)
        
        # Confronta con saldi reali forniti
        differenze = {}
        differenza_totale = 0
        
        for categoria, saldo_reale in saldi_reali_per_categoria.items():
            if categoria in ['liquidita', 'crediti', 'debiti']:
                saldo_teorico = situazione_teorica.get(categoria, 0)
                differenza = saldo_reale - saldo_teorico
                differenze[categoria] = {
                    'teorico': saldo_teorico,
                    'reale': saldo_reale,
                    'differenza': differenza
                }
                differenza_totale += abs(differenza)
        
        # Crea controllo generale
        controllo = cls(
            operatore=user,
            data_inizio_periodo=timezone.now() - timezone.timedelta(days=30),  # Ultimo mese
            data_fine_periodo=timezone.now(),
            saldo_iniziale=0,  # Non applicabile per controllo generale
            saldo_finale_reale=sum(saldi_reali_per_categoria.values()),
            saldo_finale_calcolato=situazione_teorica['situazione_finanziaria_netta'],
            controllo_generale=True,
            note_controllo=f"Controllo generale - Differenze per categoria: {differenze}"
        )
        
        db.save_object(controllo)
        return controllo
    
    @classmethod
    def get_ultimo_controllo(cls, user, conto=None):
        """Recupera l'ultimo controllo effettuato"""
        from .database_utils import DatabaseManager
        
        db = DatabaseManager(user)
        queryset = db.get_queryset(cls)
        
        if conto:
            queryset = queryset.filter(conto_controllato=conto)
        
        return queryset.first()
    
    @property
    def has_anomalie(self):
        """Verifica se il controllo ha rilevato anomalie"""
        return abs(self.differenza) >= 0.01
    
    @property
    def percentuale_scostamento(self):
        """Calcola la percentuale di scostamento"""
        if self.saldo_finale_calcolato != 0:
            return (self.differenza / self.saldo_finale_calcolato) * 100
        return 0

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