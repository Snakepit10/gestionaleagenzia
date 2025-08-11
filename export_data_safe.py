#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script per esportare dati locali per Railway con encoding UTF-8 corretto
ATTENZIONE: Questo è un export una-tantum. Lo script verrà eliminato dopo l'uso.
"""
import os
import sys
import django
import json
from io import StringIO
from django.core.management import call_command

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agenzia.settings')
django.setup()

def export_database_safe(db_name, output_file):
    """Esporta un database con encoding UTF-8 sicuro"""
    print(f"🔄 Esportando database '{db_name}'...")
    
    # Usa StringIO per catturare l'output in memoria
    output = StringIO()
    
    try:
        # Esporta i dati dal database specificato
        call_command(
            'dumpdata',
            '--database', db_name,
            '--format', 'json',
            '--indent', 2,
            '--natural-foreign',
            '--natural-primary',
            stdout=output,
            exclude=[
                'contenttypes',
                'admin.logentry',
                'sessions.session',
                'auth.permission',
            ]
        )
        
        # Ottieni i dati come stringa
        data_str = output.getvalue()
        
        # Salva il file con encoding UTF-8 esplicito
        with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(data_str)
        
        print(f"✅ Database '{db_name}' esportato in '{output_file}' con encoding UTF-8")
        
        # Verifica che il file sia valido JSON
        with open(output_file, 'r', encoding='utf-8') as f:
            json.load(f)
        print(f"✅ File JSON validato correttamente")
        
        return True
        
    except Exception as e:
        print(f"❌ Errore esportando '{db_name}': {str(e)}")
        return False
    
    finally:
        output.close()

def main():
    """Esporta tutti i database locali"""
    print("🚀 Avvio export dati locali per Railway...")
    print("📋 Encoding: UTF-8")
    print("📋 Formato: JSON con indentazione")
    
    databases = {
        'default': 'railway_data_default.json',
        'goldbet_db': 'railway_data_goldbet_db.json', 
        'better_db': 'railway_data_better_db.json'
    }
    
    success_count = 0
    
    for db_name, filename in databases.items():
        if export_database_safe(db_name, filename):
            success_count += 1
            
            # Mostra statistiche del file
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"📊 {filename}: {len(data)} records")
            except:
                pass
    
    print(f"\n🎉 Export completato: {success_count}/{len(databases)} database esportati")
    
    if success_count == len(databases):
        print("\n✅ Tutti i database sono stati esportati correttamente!")
        print("📤 File pronti per il caricamento su Railway:")
        for filename in databases.values():
            if os.path.exists(filename):
                size_mb = os.path.getsize(filename) / 1024 / 1024
                print(f"   - {filename} ({size_mb:.2f} MB)")
    else:
        print(f"\n⚠️ Alcuni database non sono stati esportati correttamente")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())