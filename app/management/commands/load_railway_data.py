"""
Comando per caricare i dati esportati su Railway
"""
from django.core.management.base import BaseCommand
from django.core import management
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Carica i dati esportati nei database Railway'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-dir',
            type=str,
            default='.',
            help='Directory contenente i file JSON esportati'
        )

    def handle(self, *args, **options):
        data_dir = options['data_dir']
        
        # Mappa dei file dati per ciascun database
        data_files = {
            'default': 'railway_data_default.json',
            'goldbet_db': 'railway_data_goldbet_db.json', 
            'better_db': 'railway_data_better_db.json'
        }
        
        for db_name, filename in data_files.items():
            filepath = os.path.join(data_dir, filename)
            
            if not os.path.exists(filepath):
                self.stdout.write(f"⚠️ File {filename} non trovato, saltato")
                continue
                
            self.stdout.write(f"🔄 Caricando dati in {db_name} da {filename}...")
            
            try:
                # Carica i dati nel database specifico
                management.call_command(
                    'loaddata',
                    filepath,
                    '--database', db_name,
                    verbosity=1
                )
                self.stdout.write(f"✅ Dati caricati con successo in {db_name}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Errore caricando dati in {db_name}: {str(e)}")
                )
                
        self.stdout.write(
            self.style.SUCCESS('🎉 Caricamento dati Railway completato!')
        )