"""
Comando per configurare agenzie e utenti per il multi-tenancy
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from app.models import Agenzia, ProfiloUtente


class Command(BaseCommand):
    help = 'Configura agenzie e utenti per il sistema multi-tenant'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-agenzie',
            action='store_true',
            help='Crea le agenzie di esempio',
        )
        parser.add_argument(
            '--create-users',
            action='store_true',
            help='Crea gli utenti di esempio',
        )

    def handle(self, *args, **options):
        if options['create_agenzie']:
            self.create_agenzie()
        
        if options['create_users']:
            self.create_users()

    def create_agenzie(self):
        """Crea le agenzie di esempio"""
        agenzie_data = [
            {
                'nome': 'Goldbet',
                'codice': '2015103',
                'database_name': 'goldbet_db'
            },
            {
                'nome': 'Better',
                'codice': '2014678', 
                'database_name': 'better_db'
            },
            {
                'nome': 'Planet',
                'codice': '2016789',
                'database_name': 'planet_db'
            }
        ]

        for agenzia_data in agenzie_data:
            agenzia, created = Agenzia.objects.get_or_create(
                codice=agenzia_data['codice'],
                defaults=agenzia_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Creata agenzia: {agenzia.nome}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Agenzia già esistente: {agenzia.nome}')
                )

    def create_users(self):
        """Crea gli utenti di esempio"""
        try:
            # Agenzia Goldbet
            goldbet = Agenzia.objects.get(codice='2015103')
            better = Agenzia.objects.get(codice='2014678')
            planet = Agenzia.objects.get(codice='2016789')
        except Agenzia.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('Agenzie non trovate! Esegui prima --create-agenzie')
            )
            return

        utenti_data = [
            {
                'username': 'daniele',
                'email': 'danielelombardo12@gmail.com',
                'first_name': 'Daniele',
                'last_name': 'Lombardo',
                'agenzia': goldbet,
                'is_staff': True,
                'is_superuser': True
            },
            {
                'username': 'salvo',
                'email': 'salvo@better.com',
                'first_name': 'Salvo',
                'last_name': 'Better',
                'agenzia': better,
                'is_staff': True,
                'is_superuser': False
            },
            {
                'username': 'admin_planet',
                'email': 'admin@planet.com',
                'first_name': 'Admin',
                'last_name': 'Planet',
                'agenzia': planet,
                'is_staff': True,
                'is_superuser': False
            }
        ]

        for user_data in utenti_data:
            agenzia = user_data.pop('agenzia')
            
            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    username=user_data['username'],
                    defaults=user_data
                )
                
                if created:
                    user.set_password('password123')  # Password temporanea
                    user.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Creato utente: {user.username}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Utente già esistente: {user.username}')
                    )

                # Crea o aggiorna il profilo
                profilo, created = ProfiloUtente.objects.get_or_create(
                    user=user,
                    defaults={'agenzia': agenzia}
                )
                
                if not created and profilo.agenzia != agenzia:
                    profilo.agenzia = agenzia
                    profilo.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Aggiornato profilo per {user.username} -> {agenzia.nome}')
                    )
                elif created:
                    self.stdout.write(
                        self.style.SUCCESS(f'Creato profilo per {user.username} -> {agenzia.nome}')
                    )