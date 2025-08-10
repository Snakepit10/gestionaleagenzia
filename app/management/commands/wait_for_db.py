"""
Comando Django per aspettare che i database siano pronti
"""
import time
import sys
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Comando per aspettare che tutti i database siano disponibili"""
    
    help = 'Aspetta che tutti i database siano disponibili'
    
    def handle(self, *args, **options):
        """Logica principale del comando"""
        self.stdout.write('🔍 Aspettando che i database siano pronti...')
        
        databases = ['default', 'goldbet_db', 'better_db']
        max_attempts = 30
        
        for db_name in databases:
            attempts = 0
            db_ready = False
            
            while not db_ready and attempts < max_attempts:
                try:
                    # Prova a ottenere una connessione al database
                    connection = connections[db_name]
                    connection.cursor()
                    db_ready = True
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Database {db_name} pronto!')
                    )
                except OperationalError:
                    attempts += 1
                    self.stdout.write(
                        f'⏳ Database {db_name} non pronto. Tentativo {attempts}/{max_attempts}...'
                    )
                    time.sleep(2)
            
            if not db_ready:
                self.stdout.write(
                    self.style.ERROR(f'❌ Database {db_name} non disponibile dopo {max_attempts} tentativi')
                )
                sys.exit(1)
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Tutti i database sono pronti!')
        )