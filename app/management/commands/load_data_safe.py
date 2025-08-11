# -*- coding: utf-8 -*-
"""
Comando per caricare i dati esportati su Railway con encoding UTF-8 sicuro
ATTENZIONE: Questo è un caricamento una-tantum. Il comando verrà eliminato dopo l'uso.
"""
from django.core.management.base import BaseCommand
from django.core import management
from django.db import transaction
import os
import json

class Command(BaseCommand):
    help = 'Carica i dati esportati nei database Railway con encoding UTF-8'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-dir',
            type=str,
            default='.',
            help='Directory contenente i file JSON esportati'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra solo quello che verrebbe caricato senza farlo realmente'
        )

    def handle(self, *args, **options):
        data_dir = options['data_dir']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 MODALITÀ DRY-RUN - Nessun dato verrà caricato')
        
        self.stdout.write('🚀 Avvio caricamento dati Railway...')
        self.stdout.write(f'📁 Directory dati: {data_dir}')
        self.stdout.write(f'📋 Encoding: UTF-8')
        
        # Mappa dei file dati per ciascun database
        data_files = {
            'default': 'railway_data_default.json',
            'goldbet_db': 'railway_data_goldbet_db.json', 
            'better_db': 'railway_data_better_db.json'
        }
        
        self.stdout.write(f'📋 File da caricare: {list(data_files.values())}')
        
        success_count = 0
        
        for db_name, filename in data_files.items():
            filepath = os.path.join(data_dir, filename)
            
            self.stdout.write(f"\n🔍 Cercando file: {filepath}")
            
            if not os.path.exists(filepath):
                self.stdout.write(f"❌ File {filename} non trovato, saltato")
                continue
            
            # Verifica che il file sia UTF-8 valido
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                record_count = len(data)
                file_size_mb = os.path.getsize(filepath) / 1024 / 1024
                
                self.stdout.write(f"✅ File trovato e validato:")
                self.stdout.write(f"   📊 Records: {record_count}")
                self.stdout.write(f"   💾 Dimensione: {file_size_mb:.2f} MB")
                
                if dry_run:
                    self.stdout.write(f"🔍 [DRY-RUN] Caricheremmo {record_count} records in {db_name}")
                    success_count += 1
                    continue
                
                # Carica i dati con transazione per sicurezza
                self.stdout.write(f"🔄 Caricando {record_count} records in {db_name}...")
                
                with transaction.atomic(using=db_name):
                    management.call_command(
                        'loaddata',
                        filepath,
                        format='json',
                        database=db_name,
                        verbosity=1
                    )
                
                self.stdout.write(f"✅ Database {db_name} caricato con successo")
                success_count += 1
                
            except json.JSONDecodeError as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ File {filename} non è JSON valido: {str(e)}")
                )
            except UnicodeDecodeError as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Errore encoding UTF-8 in {filename}: {str(e)}")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Errore caricando {filename} in {db_name}: {str(e)}")
                )
                # Non interrompiamo, continuiamo con gli altri database
                continue
                
        self.stdout.write(f"\n🎉 Caricamento completato: {success_count}/{len(data_files)} database")
        
        if success_count == len(data_files):
            self.stdout.write(
                self.style.SUCCESS('✅ Tutti i database sono stati caricati con successo!')
            )
            if not dry_run:
                self.stdout.write('⚠️  IMPORTANTE: Rimuovi i file JSON e questo comando dopo il caricamento')
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️ Solo {success_count} database caricati correttamente')
            )