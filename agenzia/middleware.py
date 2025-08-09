"""
Middleware per impostare il database corretto in base all'agenzia dell'utente
"""
from threading import current_thread
from django.contrib.auth.models import AnonymousUser


class AgenziaMiddleware:
    """
    Middleware che imposta il database corretto per ogni richiesta
    in base all'agenzia dell'utente autenticato
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Imposta il database predefinito
        database = 'default'
        
        # Se l'utente è autenticato, ottieni il suo database
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # Prova a ottenere il profilo utente
                profilo = request.user.profiloutente
                if profilo and profilo.agenzia:
                    database = profilo.agenzia.database_name
            except:
                # Se non c'è profilo, usa il database predefinito
                pass
        
        # Imposta il database per il thread corrente
        current_thread().user_database = database
        
        # Continua con la richiesta
        response = self.get_response(request)
        
        # Pulisci il database dal thread
        if hasattr(current_thread(), 'user_database'):
            delattr(current_thread(), 'user_database')
        
        return response