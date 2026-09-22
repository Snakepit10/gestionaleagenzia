from django.db import migrations

# Set iniziale ACCESO da noi (oltre alle 13 curate gia' attive): competizioni presenti nel
# catalogo e di interesse. codice -> (bandiera, short_name). L'utente poi ne aggiunge/toglie
# dall'admin. Idempotente: accende solo se la riga esiste, non tocca le altre.
SET_INIZIALE = {
    'italia-serie-c-girone-a': ('it', 'SERIE C-A'),
    'italia-serie-c-girone-b': ('it', 'SERIE C-B'),
    'italia-serie-c-girone-c': ('it', 'SERIE C-C'),
    'spagna-copa-del-rey': ('es', 'COPA DEL REY'),
    'usa-mls': ('us', 'MLS'),
    'messico-liga-mx-apertura': ('mx', 'LIGA MX'),
    'argentina-liga-profesional-clausura': ('ar', 'LIGA ARG'),
}

# Nazione per le curate che non hanno alias (quindi il backfill non la ricava dal prefisso).
NAZIONE_CURATE = {
    'mondiali': 'Mondo',
    'europei': 'Europa',
}


def attiva(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    for codice, (flag, short) in SET_INIZIALE.items():
        row = CompetizioneLedwall.objects.using('default').filter(codice=codice).first()
        if not row:
            continue
        row.attivo = True
        row.bandiera = flag
        row.short_name = short
        row.save(using='default', update_fields=['attivo', 'bandiera', 'short_name'])
    # Categorizza per nazione le curate senza alias.
    for codice, nazione in NAZIONE_CURATE.items():
        (CompetizioneLedwall.objects.using('default')
         .filter(codice=codice, nazione='').update(nazione=nazione))


def disattiva(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    (CompetizioneLedwall.objects.using('default')
     .filter(codice__in=list(SET_INIZIALE)).update(attivo=False))


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0046_seed_catalogo_competizioni'),
    ]

    operations = [
        migrations.RunPython(attiva, disattiva),
    ]
