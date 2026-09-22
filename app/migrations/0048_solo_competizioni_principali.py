from django.db import migrations


def solo_principali(apps, schema_editor):
    # Solo sul DB condiviso 'default'. Elimina tutte le competizioni non principali e
    # installa/aggiorna (attive) quelle dell'elenco curato PRINCIPALI.
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import catalogo
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    catalogo.sync_principali(CompetizioneLedwall, using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0047_attiva_set_iniziale_competizioni'),
    ]

    operations = [
        migrations.RunPython(solo_principali, noop),
    ]
