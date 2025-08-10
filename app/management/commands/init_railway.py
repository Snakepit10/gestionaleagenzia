"""
Comando per inizializzare completamente Railway con utenti e conti
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from app.models import Agenzia, ProfiloUtente, ContoFinanziario


class Command(BaseCommand):
    help = 'Inizializza completamente Railway con utenti, agenzie e conti'

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                # 1. Crea le agenzie
                self.stdout.write('🏢 Creando agenzie...')
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
                    }
                ]

                agenzie = {}
                for agenzia_data in agenzie_data:
                    agenzia, created = Agenzia.objects.get_or_create(
                        codice=agenzia_data['codice'],
                        defaults=agenzia_data
                    )
                    agenzie[agenzia_data['nome']] = agenzia
                    if created:
                        self.stdout.write(f'✅ Creata agenzia: {agenzia.nome}')
                    else:
                        self.stdout.write(f'⚠️ Agenzia già esistente: {agenzia.nome}')

                # 2. Crea gli utenti
                self.stdout.write('👥 Creando utenti...')
                utenti_data = [
                    {
                        'username': 'daniele',
                        'email': 'danielelombardo12@gmail.com',
                        'first_name': 'Daniele',
                        'last_name': 'Lombardo',
                        'agenzia': agenzie['Goldbet'],
                        'is_staff': True,
                        'is_superuser': True
                    },
                    {
                        'username': 'salvo',
                        'email': 'salvo@better.com',
                        'first_name': 'Salvo',
                        'last_name': 'Better',
                        'agenzia': agenzie['Better'],
                        'is_staff': True,
                        'is_superuser': False
                    }
                ]

                admin_user = None
                for user_data in utenti_data:
                    agenzia = user_data.pop('agenzia')
                    
                    user, created = User.objects.get_or_create(
                        username=user_data['username'],
                        defaults=user_data
                    )
                    
                    if created:
                        user.set_password('password123')
                        user.save()
                        self.stdout.write(f'✅ Creato utente: {user.username}')
                        
                        # Salva il primo admin per creare i conti
                        if user.is_superuser and not admin_user:
                            admin_user = user
                    else:
                        self.stdout.write(f'⚠️ Utente già esistente: {user.username}')
                        if user.is_superuser and not admin_user:
                            admin_user = user

                    # Crea il profilo utente
                    profilo, created = ProfiloUtente.objects.get_or_create(
                        user=user,
                        defaults={'agenzia': agenzia}
                    )
                    
                    if created:
                        self.stdout.write(f'✅ Creato profilo per {user.username} -> {agenzia.nome}')

                # 3. Crea i conti finanziari predefiniti (solo nel database default)
                if admin_user and ContoFinanziario.objects.using('default').count() == 0:
                    self.stdout.write('💰 Creando conti finanziari predefiniti nel database default...')
                    try:
                        # Crea i conti base nel database default
                        conti_base = [
                            {'nome': 'Cassa', 'tipo': 'attivo', 'descrizione': 'Denaro contante'},
                            {'nome': 'Banca', 'tipo': 'attivo', 'descrizione': 'Conto corrente bancario'},
                            {'nome': 'Clienti', 'tipo': 'attivo', 'descrizione': 'Crediti vs clienti'},
                            {'nome': 'Fornitori', 'tipo': 'passivo', 'descrizione': 'Debiti vs fornitori'},
                        ]
                        
                        for conto_data in conti_base:
                            ContoFinanziario.objects.using('default').create(
                                nome=conto_data['nome'],
                                tipo=conto_data['tipo'],
                                descrizione=conto_data['descrizione'],
                                creato_da=admin_user,
                                modificato_da=admin_user,
                                saldo=0
                            )
                        
                        self.stdout.write('✅ Conti finanziari creati nel database default')
                    except Exception as e:
                        self.stdout.write(f'⚠️ Errore creando conti finanziari: {e}')
                
                self.stdout.write(
                    self.style.SUCCESS('🎉 Inizializzazione Railway completata!')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Errore durante l\'inizializzazione: {str(e)}')
            )
            raise