from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0043_competizioneledwall_modalita'),
    ]

    operations = [
        migrations.AddField(
            model_name='impostazioniledwall',
            name='loghi_riepilogo',
            field=models.BooleanField(
                default=False,
                help_text='Mostra i loghi delle squadre ai lati nelle schede riepilogo'),
        ),
        migrations.AddField(
            model_name='impostazioniledwall',
            name='max_partite_riepilogo',
            field=models.IntegerField(
                default=6,
                help_text='Massimo di partite per scheda riepilogo: se sono di più, il riepilogo si '
                          'divide su più schede (righe più grandi e leggibili). Default 6.'),
        ),
    ]
