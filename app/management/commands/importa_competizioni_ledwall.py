# -*- coding: utf-8 -*-
"""
Importa nel ledwall (CompetizioneLedwall, DB 'default') tutte le competizioni che compaiono nel
feed di diretta.it, su piu' giorni, raggruppate per nazione e **disattivate**.

    python manage.py importa_competizioni_ledwall            # scarica dal feed e importa
    python manage.py importa_competizioni_ledwall --giorni 14
    python manage.py importa_competizioni_ledwall --solo-json # aggiorna solo il file catalogo
    python manage.py importa_competizioni_ledwall --da-file   # importa dal file catalogo (no rete)

Non tocca le competizioni gia' presenti (dedup sugli alias): aggiunge solo quelle nuove, spente.
Dall'admin poi le accendi e imposti bandiera / modalita' / ordine.
"""
from django.core.management.base import BaseCommand

from app.ledwall import catalogo


class Command(BaseCommand):
    help = "Importa le competizioni dal feed diretta.it in CompetizioneLedwall (disattivate), per nazione."

    def add_arguments(self, parser):
        parser.add_argument('--tutte', action='store_true',
                            help="Scarica dal feed TUTTE le competizioni trovate (avanzato). "
                                 "Senza questo flag installa solo le PRINCIPALI (consigliato).")
        parser.add_argument('--giorni', type=int, default=8,
                            help="Con --tutte: quanti giorni in avanti scandire (default 8; parte da ieri).")
        parser.add_argument('--solo-json', action='store_true',
                            help="Con --tutte: scarica dal feed e aggiorna solo il file catalogo, senza DB.")
        parser.add_argument('--da-file', action='store_true',
                            help="Con --tutte: importa dal file catalogo versionato, senza chiamare il feed.")

    def handle(self, *args, **opts):
        if not opts['tutte']:
            from app.models import CompetizioneLedwall
            creati, aggiornati, eliminate = catalogo.sync_principali(CompetizioneLedwall, using='default')
            self.stdout.write(self.style.SUCCESS(
                "Competizioni principali: %d create, %d aggiornate, %d rimosse (non principali)."
                % (creati, aggiornati, eliminate)))
            return
        if opts['da_file']:
            cat = catalogo.load_json()
            self.stdout.write("Catalogo da file: %d competizioni." % len(cat))
        else:
            cat = catalogo.discover_from_feed(range(-1, opts['giorni']))
            catalogo.write_json(cat)
            nazioni = len({c['nazione'] for c in cat})
            self.stdout.write("Trovate %d competizioni in %d nazioni (catalogo aggiornato)." % (len(cat), nazioni))
            if opts['solo_json']:
                return

        from app.models import CompetizioneLedwall
        created = catalogo.upsert(CompetizioneLedwall, cat, using='default')
        self.stdout.write(self.style.SUCCESS(
            "Aggiunte %d nuove competizioni (disattivate). Attivale dall'admin: Ledwall - Competizioni." % created))
