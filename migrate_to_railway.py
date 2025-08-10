"""
Script per migrare direttamente i dati SQLite locali su PostgreSQL Railway
"""
import os
import django
from django.core.management import execute_from_command_line
from django.db import connections
from django.contrib.auth.models import User

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agenzia.settings')
django.setup()

from app.models import Cliente, Movimento, DistintaCassa, Agenzia, ProfiloUtente

def migrate_data_to_railway():
    """Migra i dati da SQLite locale a PostgreSQL Railway"""
    
    print("🚀 Iniziando migrazione dati su Railway...")
    
    # Prima assicurati che le migrazioni siano applicate
    print("📋 Applicando migrazioni...")
    execute_from_command_line(['manage.py', 'migrate', '--database=default'])
    execute_from_command_line(['manage.py', 'migrate', '--database=goldbet_db']) 
    execute_from_command_line(['manage.py', 'migrate', '--database=better_db'])
    
    # Controlla se siamo su Railway (presenza variabili PostgreSQL)
    is_railway = bool(os.environ.get('DATABASE_URL', '').startswith('postgres'))
    
    if not is_railway:
        print("❌ Questo script deve essere eseguito su Railway con database PostgreSQL")
        return
        
    try:
        # Migra database default (utenti e agenzie)
        print("👥 Migrando utenti e agenzie...")
        execute_from_command_line(['manage.py', 'init_railway'])
        
        # Se hai dati da migrare dai database locali, usa i file JSON esportati
        print("📊 Per migrare i dati operativi, usa:")
        print("1. Esporta i dati localmente con: python export_data_for_railway.py")
        print("2. Carica su Railway con: python manage.py load_railway_data")
        
        print("✅ Setup Railway completato!")
        
    except Exception as e:
        print(f"❌ Errore durante la migrazione: {e}")

if __name__ == '__main__':
    migrate_data_to_railway()