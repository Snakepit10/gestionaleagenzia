"""
Sistema di gestione multi-database pulito e semplice
"""
from django.contrib.auth.models import User
from django.db import models


# Mapping agenzia -> database
AGENZIA_DATABASE_MAP = {
    'goldbet': 'goldbet_db',
    'better': 'better_db',
}

# Database di default per dati condivisi
DEFAULT_DB = 'default'


def get_user_database(user):
    """
    Restituisce il database corretto per l'utente basato sulla sua agenzia
    """
    if not user or not user.is_authenticated:
        return DEFAULT_DB
    
    try:
        profilo = user.profiloutente
        if profilo and profilo.agenzia:
            agenzia_nome = profilo.agenzia.nome.lower()
            return AGENZIA_DATABASE_MAP.get(agenzia_nome, DEFAULT_DB)
    except:
        pass
    
    return DEFAULT_DB


class DatabaseManager:
    """
    Manager per gestire operazioni multi-database in modo consistente
    """
    
    def __init__(self, user):
        self.user = user
        self.user_db = get_user_database(user)
    
    def get_queryset(self, model_class, select_related=None, prefetch_related=None):
        """
        Restituisce un queryset sul database corretto con ottimizzazioni
        """
        queryset = model_class.objects.using(self.user_db)
        
        if select_related:
            queryset = queryset.select_related(*select_related)
        
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        
        return queryset
    
    def get_object_or_404(self, model_class, select_related=None, **filters):
        """
        Get object or 404 sul database corretto
        """
        from django.shortcuts import get_object_or_404
        queryset = self.get_queryset(model_class, select_related=select_related)
        return get_object_or_404(queryset, **filters)
    
    def save_object(self, obj, **kwargs):
        """
        Salva un oggetto sul database corretto
        """
        kwargs['using'] = self.user_db
        return obj.save(**kwargs)
    
    def delete_object(self, obj, **kwargs):
        """
        Elimina un oggetto dal database corretto
        """
        kwargs['using'] = self.user_db
        return obj.delete(**kwargs)


class MultiDatabaseMixin:
    """
    Mixin per i modelli che devono funzionare in multi-database
    """
    
    def save(self, *args, **kwargs):
        # Se non è specificato using, usa il database dell'oggetto corrente
        if 'using' not in kwargs and hasattr(self, '_state') and self._state.db:
            kwargs['using'] = self._state.db
        return super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Se non è specificato using, usa il database dell'oggetto corrente
        if 'using' not in kwargs and hasattr(self, '_state') and self._state.db:
            kwargs['using'] = self._state.db
        return super().delete(*args, **kwargs)


def sync_user_to_agency_db(user):
    """
    Sincronizza un utente nel database della sua agenzia
    """
    if not user:
        return
    
    user_db = get_user_database(user)
    if user_db == DEFAULT_DB:
        return  # Utente già nel database principale
    
    try:
        # Crea o aggiorna l'utente nel database dell'agenzia
        existing_user = User.objects.using(user_db).filter(id=user.id).first()
        
        if existing_user:
            # Aggiorna utente esistente
            existing_user.username = user.username
            existing_user.first_name = user.first_name
            existing_user.last_name = user.last_name
            existing_user.email = user.email
            existing_user.password = user.password
            existing_user.is_staff = user.is_staff
            existing_user.is_active = user.is_active
            existing_user.is_superuser = user.is_superuser
            existing_user.date_joined = user.date_joined
            existing_user.last_login = user.last_login
            existing_user.save(using=user_db)
        else:
            # Crea nuovo utente
            User.objects.using(user_db).create(
                id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                password=user.password,
                is_staff=user.is_staff,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                date_joined=user.date_joined,
                last_login=user.last_login,
            )
    except Exception as e:
        print(f"Errore sincronizzazione utente {user.username}: {e}")


def get_all_databases():
    """
    Restituisce tutti i database delle agenzie
    """
    return list(AGENZIA_DATABASE_MAP.values()) + [DEFAULT_DB]


def migrate_all_databases():
    """
    Utility per fare migrate su tutti i database
    """
    from django.core.management import call_command
    
    for db in get_all_databases():
        print(f"Migrating database: {db}")
        call_command('migrate', database=db, verbosity=1)