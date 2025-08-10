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
        
        self.stdout.write('🚀 Iniziando caricamento dati Railway...')
        self.stdout.write(f'📁 Directory dati: {data_dir}')
        
        # Mappa dei file dati per ciascun database
        data_files = {
            'default': 'railway_data_default.json',
            'goldbet_db': 'railway_data_goldbet_db.json', 
            'better_db': 'railway_data_better_db.json'
        }
        
        self.stdout.write(f'📋 File da caricare: {list(data_files.values())}')
        
        for db_name, filename in data_files.items():
            filepath = os.path.join(data_dir, filename)
            
            self.stdout.write(f"🔍 Cercando file: {filepath}")
            
            if not os.path.exists(filepath):
                self.stdout.write(f"❌ File {filename} non trovato in {filepath}")
                # Prova nella root directory
                root_filepath = filename
                if os.path.exists(root_filepath):
                    filepath = root_filepath
                    self.stdout.write(f"✅ File trovato in root: {filepath}")
                else:
                    self.stdout.write(f"❌ File {filename} non trovato neanche in root, saltato")
                    continue
            else:
                self.stdout.write(f"✅ File trovato: {filepath}")
                
            self.stdout.write(f"🔄 Caricando dati in {db_name} da {filename}...")
            
            try:
                # Prova a correggere l'encoding del file
                self.stdout.write(f"🔧 Correggendo encoding del file...")
                with open(filepath, 'rb') as f:
                    content = f.read()
                
                # Prova diversi encoding
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        decoded_content = content.decode(encoding)
                        # Risalva con UTF-8
                        temp_filepath = f"{filepath}.utf8"
                        with open(temp_filepath, 'w', encoding='utf-8') as f:
                            f.write(decoded_content)
                        
                        self.stdout.write(f"✅ File corretto con encoding {encoding}")
                        filepath = temp_filepath
                        break
                    except UnicodeDecodeError:
                        continue
                
                # Carica i dati nel database specifico
                management.call_command(
                    'loaddata',
                    filepath,
                    '--database', db_name,
                    verbosity=2
                )
                self.stdout.write(f"✅ Dati caricati con successo in {db_name}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Errore caricando dati in {db_name}: {str(e)}")
                )
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
                
        self.stdout.write(
            self.style.SUCCESS('🎉 Caricamento dati Railway completato!')
        )