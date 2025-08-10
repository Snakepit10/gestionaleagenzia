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
                # Gestione corretta dell'encoding con JSON
                self.stdout.write(f"🔧 Correggendo encoding del file JSON...")
                
                import json
                import codecs
                
                # Prova diversi encoding per leggere il file
                data = None
                successful_encoding = None
                
                for encoding in ['utf-8', 'latin-1', 'cp1252']:
                    try:
                        with codecs.open(filepath, 'r', encoding=encoding) as f:
                            data = json.load(f)
                        successful_encoding = encoding
                        self.stdout.write(f"✅ File letto correttamente con encoding {encoding}")
                        break
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        self.stdout.write(f"⚠️ Encoding {encoding} fallito: {e}")
                        continue
                
                if data is None:
                    raise Exception("Impossibile leggere il file con nessun encoding")
                
                # Salva il file con UTF-8 corretto
                temp_filepath = filepath.replace('.json', '_clean.json')
                with open(temp_filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                self.stdout.write(f"✅ File risalvato con UTF-8: {temp_filepath}")
                
                # Carica i dati nel database specifico con formato esplicito
                management.call_command(
                    'loaddata',
                    temp_filepath,
                    format='json',  # Specifica esplicitamente il formato
                    database=db_name,
                    verbosity=2
                )
                
                # Pulisci il file temporaneo
                import os
                os.remove(temp_filepath)
                
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