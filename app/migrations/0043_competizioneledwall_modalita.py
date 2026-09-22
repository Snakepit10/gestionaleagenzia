from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0042_competizioneledwall_bandiera'),
    ]

    operations = [
        migrations.AddField(
            model_name='competizioneledwall',
            name='modalita',
            field=models.CharField(
                max_length=10, default='entrambe',
                choices=[('entrambe', 'Schede + Riepilogo'), ('schede', 'Solo schede'),
                         ('riepilogo', 'Solo riepilogo')],
                help_text="Come mostrare questa competizione: le singole schede partita e poi la "
                          "scheda riepilogo (default), solo le schede, oppure solo il riepilogo.",
            ),
        ),
    ]
