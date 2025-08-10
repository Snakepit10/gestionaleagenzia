"""
Script per esportare i dati locali per il caricamento su Railway
"""
import os
import sys
import django
from django.core import management
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agenzia.settings')
django.setup()

def export_database_data():
    """Esporta i dati di tutti i database in formato JSON"""
    
    databases = ['default', 'goldbet_db', 'better_db']
    
    for db_name in databases:
        print(f"🔄 Esportando dati da {db_name}...")
        
        # Nome file di output
        output_file = f"railway_data_{db_name}.json"
        
        try:
            # Esporta tutti i dati del database con encoding UTF-8 esplicito
            with open(output_file, 'w', encoding='utf-8') as f:
                management.call_command(
                    'dumpdata',
                    '--database', db_name,
                    '--natural-foreign', 
                    '--natural-primary',
                    '--indent', '2',
                    stdout=f
                )
            print(f"✅ Dati esportati in {output_file} con encoding UTF-8")
            
        except Exception as e:
            print(f"❌ Errore esportando {db_name}: {e}")

if __name__ == '__main__':
    export_database_data()