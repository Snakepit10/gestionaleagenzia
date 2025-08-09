# Railway Setup per Multi-Tenancy

## Passaggi per il deployment:

### 1. Crea il progetto su Railway
1. Vai su railway.app
2. Clicca "New Project" 
3. Collega il tuo repository GitHub

### 2. Configura i database PostgreSQL
Dovrai creare **3 database PostgreSQL**:

#### Database Principale (default):
```bash
railway add --database postgresql
```
Questo genererà la variabile `DATABASE_URL`

#### Database Goldbet:
```bash
railway add --database postgresql  
```
Rinomina questa variabile come `GOLDBET_DATABASE_URL` nelle impostazioni

#### Database Better:
```bash
railway add --database postgresql
```  
Rinomina questa variabile come `BETTER_DATABASE_URL` nelle impostazioni

### 3. Configura le variabili d'ambiente
Nel dashboard Railway, vai su Settings > Environment Variables:

```
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=*.railway.app,your-domain.com
DATABASE_URL=(generato automaticamente)
GOLDBET_DATABASE_URL=(url del database Goldbet)
BETTER_DATABASE_URL=(url del database Better)
```

### 4. Deploy
Il deploy avviene automaticamente. Il Procfile eseguirà:
1. Migrazioni sul database principale
2. Migrazioni sul database Goldbet  
3. Migrazioni sul database Better
4. Setup delle agenzie e utenti

### 5. Utenti creati automaticamente:
- **daniele** (Goldbet) - password: password123
- **salvo** (Better) - password: password123

### 6. Accesso admin:
L'utente **daniele** è superuser e può accedere all'admin Django.