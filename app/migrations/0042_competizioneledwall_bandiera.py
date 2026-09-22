from django.db import migrations, models


def seed_flags(apps, schema_editor):
    # Solo sul DB condiviso 'default' (le competizioni ledwall vivono li').
    if schema_editor.connection.alias != 'default':
        return
    from app.ledwall import config
    CompetizioneLedwall = apps.get_model('app', 'CompetizioneLedwall')
    flag_by_code = {c['id']: (c.get('flag') or '') for c in config.COMPETITIONS}
    for row in CompetizioneLedwall.objects.using('default').all():
        if not (row.bandiera or '').strip():
            f = flag_by_code.get(row.codice, '')
            if f:
                row.bandiera = f
                row.save(using='default', update_fields=['bandiera'])


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0041_impostazioniledwall_loghi_hd'),
    ]

    operations = [
        migrations.AddField(
            model_name='competizioneledwall',
            name='bandiera',
            field=models.CharField(
                blank=True, default='', max_length=12,
                help_text="Codice bandiera mostrata accanto al nome (ISO): es. 'it', 'es', 'de', "
                          "'fr', 'gb-eng' (Inghilterra), 'eu' (competizioni europee). Vuoto = nessuna.",
            ),
        ),
        migrations.RunPython(seed_flags, unseed),
    ]
