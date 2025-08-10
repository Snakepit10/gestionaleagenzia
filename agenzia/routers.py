"""
Database router per multi-tenancy per agenzia
Ogni agenzia ha il suo database separato
"""
from django.contrib.auth.models import User


class AgenziaRouter:
    """
    Router per indirizzare le query al database corretto in base all'agenzia dell'utente
    """
    
    # Modelli che appartengono al database principale (comuni a tutte le agenzie)
    SHARED_MODELS = [
        'agenzia',
        'profiloutente', 
        'group',
        'permission',
        'contenttype',
        'session',
        'logentry'
    ]
    
    # Modelli che devono essere presenti in TUTTI i database (per foreign key)
    REPLICATED_MODELS = [
        'user'
    ]
    
    def db_for_read(self, model, **hints):
        """Decide quale database utilizzare per le letture"""
        model_name = model._meta.model_name.lower()
        
        # Modelli replicati: User va sempre nel database dell'agenzia corrente per permettere foreign key
        if model_name in self.REPLICATED_MODELS:
            return self._get_user_database()
        
        # Forza sempre gli altri modelli Django built-in al database 'default'
        if model._meta.app_label in ['contenttypes', 'sessions', 'admin']:
            return 'default'
        
        # Modelli condivisi vanno sempre sul database 'default'  
        if model_name in self.SHARED_MODELS:
            return 'default'
        
        # Per altri modelli dell'app 'app', usa il database dell'agenzia
        return self._get_user_database()
    
    def db_for_write(self, model, **hints):
        """Decide quale database utilizzare per le scritture"""
        return self.db_for_read(model, **hints)
    
    def allow_relation(self, obj1, obj2, **hints):
        """Permette relazioni tra oggetti, incluso tra modelli condivisi e specifici dell'agenzia"""
        # Sempre permetti relazioni che coinvolgono modelli built-in di Django
        if obj1 and obj2:
            # Sempre permetti se uno dei due modelli è di Django
            if (obj1._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin'] or
                obj2._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin']):
                return True
                
            # Permetti relazioni tra modelli della stessa agenzia
            if hasattr(obj1, '_state') and hasattr(obj2, '_state'):
                return obj1._state.db == obj2._state.db
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Controlla quali migrazioni possono essere applicate a quale database"""
        model_name = model_name.lower() if model_name else ''
        
        # Per PostgreSQL multi-tenant, permettiamo tutte le migrazioni su tutti i database
        # Questo è necessario perché ogni database deve avere tutte le tabelle
        return True
    
    def _get_user_database(self):
        """Ottieni il database dell'agenzia dell'utente corrente"""
        try:
            # Questo sarà impostato dal middleware
            from threading import current_thread
            if hasattr(current_thread(), 'user_database'):
                return current_thread().user_database
        except:
            pass
        return 'default'