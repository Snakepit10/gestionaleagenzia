from django.db import migrations


def seed(apps, schema_editor):
    # Solo sul DB condiviso 'default' (le competizioni ledwall vivono li').
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import config
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    for c in config.COMPETITIONS:
        aliases = '\n'.join(c.get('aliases', []) or [])
        CompetizioneLedwall.objects.using('default').get_or_create(
            codice=c['id'],
            defaults={
                'nome': c['name'],
                'short_name': c['shortName'],
                'ordine': c['priority'],
                'attivo': True,
                'aliases': aliases,
                'contiene': (c.get('contains') or ''),
            },
        )


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0037_competizioneledwall_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
