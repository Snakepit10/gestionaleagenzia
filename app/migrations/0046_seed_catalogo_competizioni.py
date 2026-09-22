from django.db import migrations


def seed(apps, schema_editor):
    # Solo sul DB condiviso 'default' (le competizioni ledwall vivono li').
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import catalogo
    cat = catalogo.load_json()
    if not cat:
        return
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    catalogo.upsert(CompetizioneLedwall, cat, using=schema_editor.connection.alias)


def unseed(apps, schema_editor):
    # Rimuove solo le competizioni importate ancora disattivate (non tocca quelle accese/curate).
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import catalogo
    cat = catalogo.load_json()
    codici = [c['codice'] for c in cat]
    if not codici:
        return
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    (CompetizioneLedwall.objects.using(schema_editor.connection.alias)
     .filter(codice__in=codici, attivo=False, ordine__gte=1000).delete())


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0045_competizioneledwall_nazione'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
