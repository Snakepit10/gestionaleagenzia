"""
Comando per ricalcolare i saldi progressivi di tutti i movimenti esistenti
"""
from django.core.management.base import BaseCommand
from app.models import Movimento
from decimal import Decimal


class Command(BaseCommand):
    help = 'Ricalcola i saldi progressivi per tutti i movimenti esistenti in tutti i database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            type=str,
            help='Database specifico da processare (es: default, goldbet_db, better_db, planet_db)',
        )

    def handle(self, *args, **options):
        # Determina quali database processare
        if options['database']:
            databases = [options['database']]
        else:
            databases = ['default', 'goldbet_db', 'better_db', 'planet_db']

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('RICALCOLO SALDI PROGRESSIVI')
        self.stdout.write('=' * 60 + '\n')

        for db_name in databases:
            self.stdout.write(f"\nElaborazione database: {db_name}")
            self.stdout.write('-' * 60)

            try:
                # Ottieni tutti i movimenti ordinati per data (dal più vecchio al più recente)
                movimenti = Movimento.objects.using(db_name).order_by('data', 'id')
                totale_movimenti = movimenti.count()

                if totale_movimenti == 0:
                    self.stdout.write(self.style.WARNING(f"Nessun movimento trovato in {db_name}"))
                    continue

                self.stdout.write(f"Trovati {totale_movimenti} movimenti da elaborare")

                # Calcola il saldo progressivo
                saldo_corrente = Decimal('0.00')
                movimenti_aggiornati = 0
                movimenti_con_errori = 0

                for idx, movimento in enumerate(movimenti, 1):
                    try:
                        # Aggiungi l'importo al saldo corrente
                        saldo_corrente += movimento.importo

                        # Aggiorna il movimento solo se il saldo è diverso
                        if movimento.saldo_progressivo != saldo_corrente:
                            movimento.saldo_progressivo = saldo_corrente
                            movimento.save(using=db_name, update_fields=['saldo_progressivo'])
                            movimenti_aggiornati += 1

                        # Mostra progresso ogni 100 movimenti
                        if idx % 100 == 0:
                            percentuale = (idx / totale_movimenti) * 100
                            self.stdout.write(
                                f"  Progresso: {idx}/{totale_movimenti} ({percentuale:.1f}%) "
                                f"- Saldo corrente: {saldo_corrente:.2f} EUR"
                            )

                    except Exception as e:
                        movimenti_con_errori += 1
                        self.stdout.write(
                            self.style.ERROR(f"  Errore nel movimento #{movimento.id}: {str(e)}")
                        )

                # Riepilogo per questo database
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nCompletato {db_name}:"
                    )
                )
                self.stdout.write(f"   - Movimenti totali: {totale_movimenti}")
                self.stdout.write(f"   - Movimenti aggiornati: {movimenti_aggiornati}")
                self.stdout.write(f"   - Saldo finale: {saldo_corrente:.2f} EUR")

                if movimenti_con_errori > 0:
                    self.stdout.write(
                        self.style.WARNING(f"   - Errori: {movimenti_con_errori}")
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Errore generale per {db_name}: {str(e)}")
                )

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('RICALCOLO COMPLETATO!'))
        self.stdout.write('=' * 60 + '\n')
