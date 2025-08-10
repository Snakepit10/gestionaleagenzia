"""
Comando per verificare se i dati sono presenti nei database
"""
from django.core.management.base import BaseCommand
from app.models import Cliente, Movimento, Agenzia
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Verifica se i dati sono presenti nei database'

    def handle(self, *args, **options):
        databases = ['default', 'goldbet_db', 'better_db']
        
        for db_name in databases:
            self.stdout.write(f"\n📊 Database: {db_name}")
            self.stdout.write("=" * 40)
            
            try:
                # Conta utenti
                user_count = User.objects.using(db_name).count()
                self.stdout.write(f"👥 Utenti: {user_count}")
                
                # Conta agenzie (solo nel default)
                if db_name == 'default':
                    agenzia_count = Agenzia.objects.using(db_name).count()
                    self.stdout.write(f"🏢 Agenzie: {agenzia_count}")
                
                # Conta clienti
                cliente_count = Cliente.objects.using(db_name).count()
                self.stdout.write(f"👤 Clienti: {cliente_count}")
                
                # Conta movimenti
                movimento_count = Movimento.objects.using(db_name).count()
                self.stdout.write(f"💰 Movimenti: {movimento_count}")
                
                # Mostra alcuni clienti
                if cliente_count > 0:
                    clienti = Cliente.objects.using(db_name)[:3]
                    self.stdout.write("📋 Primi clienti:")
                    for cliente in clienti:
                        self.stdout.write(f"  - {cliente.cognome} {cliente.nome}")
                        
            except Exception as e:
                self.stdout.write(f"❌ Errore per {db_name}: {e}")
        
        self.stdout.write(f"\n🎉 Verifica completata!")