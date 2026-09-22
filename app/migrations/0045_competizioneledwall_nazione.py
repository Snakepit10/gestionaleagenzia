from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0044_impostazioni_riepilogo'),
    ]

    operations = [
        migrations.AddField(
            model_name='competizioneledwall',
            name='nazione',
            field=models.CharField(
                max_length=40, blank=True, default='',
                help_text="Nazione/area della competizione (per raggrupparle in elenco), es. 'Italia'"),
        ),
    ]
