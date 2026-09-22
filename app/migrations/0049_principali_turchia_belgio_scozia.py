from django.db import migrations


def solo_principali(apps, schema_editor):
    # Ri-applica il set principale (ora include Turchia, Belgio, Scozia).
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import catalogo
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    catalogo.sync_principali(CompetizioneLedwall, using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0048_solo_competizioni_principali'),
    ]

    operations = [
        migrations.RunPython(solo_principali, noop),
    ]
