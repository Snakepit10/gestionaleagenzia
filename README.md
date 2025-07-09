# Gestionale Agenzia - Sistema di Gestione Crediti

Un sistema di gestione completo per il monitoraggio dei crediti, distinte di cassa e clienti per un'agenzia di scommesse.

## Caratteristiche Principali

- Gestione completa dei clienti con rating automatico
- Registrazione movimenti (schedine, ricariche, prelievi)
- Gestione distinte di cassa con verifica
- Monitoraggio fidi e saldi clienti
- Dashboard con statistiche e avvisi
- Sistema di ruoli (Operatore, Manager, Amministratore)

## Requisiti Tecnici 

- Python 3.9+
- Django 4.0+
- PostgreSQL (produzione) / SQLite (sviluppo)
- Bootstrap 5
- jQuery e Select2

## Installazione

1. Clona il repository:
```
git clone https://github.com/tuonome/agenzia.git
cd agenzia
```

2. Crea un ambiente virtuale e attivalo:
```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Installa le dipendenze:
```
pip install -r requirements.txt
```

4. Esegui le migrazioni del database:
```
python manage.py migrate
```

5. Crea un superuser:
```
python manage.py createsuperuser
```

6. Avvia il server di sviluppo:
```
python manage.py runserver
```

## Struttura del Progetto

- `app/` - L'applicazione principale
  - `models.py` - Definizione modelli dati
  - `views.py` - Logica di business e viste
  - `forms.py` - Form per l'inserimento dati
  - `admin.py` - Interfaccia amministrativa
  - `urls.py` - Routing URL
- `templates/` - Template HTML
- `static/` - Asset statici (CSS, JS, immagini)

## Modelli Dati

### Cliente
- Dati anagrafici (nome, cognome, email, telefono)
- Saldo attuale e fido massimo
- Rating (calcolato automaticamente)
- Note e storico comunicazioni

### Movimento
- Collegamento al cliente
- Tipo (schedina, ricarica, prelievo)
- Importo e data
- Stato (saldato/non saldato)
- Collegamento alla distinta di cassa
- Movimento di origine (per i saldi)

### Distinta Cassa
- Operatore, data, ora inizio/fine turno
- Cassa iniziale e finale
- Totale entrate/uscite
- Totale bevande
- Saldo terminale
- Differenza di cassa
- Stato (aperta/chiusa/verificata)

### Comunicazione
- Collegamento al cliente
- Tipo (avviso, sollecito, informativa)
- Contenuto e data
- Operatore e stato (letta/non letta)

## Ruoli Utente

1. **Operatore**:
   - Gestione base clienti e movimenti
   - Creazione/chiusura distinte
   - Non può cancellare movimenti o aumentare fidi
   - Non può modificare distinte dei giorni precedenti

2. **Manager**:
   - Tutto ciò che può fare l'operatore
   - Modifica fidi
   - Cancellazione controllata movimenti
   - Verifica distinte chiuse
   - Non può modificare distinte dei giorni precedenti

3. **Amministratore**:
   - Accesso completo
   - Configurazione parametri di sistema
   - Può modificare distinte di giorni precedenti
   - Può annullare verifiche e richiedere revisioni

## Licenza

Questo progetto è concesso in licenza con [Licenza MIT](LICENSE).

## Contatti

Per supporto o informazioni: tuaemail@esempio.com