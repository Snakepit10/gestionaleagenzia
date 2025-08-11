from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'
    
    def ready(self):
        """Setup quando l'app è pronta"""
        # Importa i segnali
        import app.signals