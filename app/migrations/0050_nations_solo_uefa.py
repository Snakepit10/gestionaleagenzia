from django.db import migrations


def fix_nations(apps, schema_editor):
    # Ri-applica il set principale: la Nations League ora matcha solo la UEFA (non CONCACAF ecc.).
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import catalogo
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    catalogo.sync_principali(CompetizioneLedwall, using=schema_editor.connection.alias)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0049_principali_turchia_belgio_scozia'),
    ]

    operations = [
        migrations.RunPython(fix_nations, noop),
    ]
