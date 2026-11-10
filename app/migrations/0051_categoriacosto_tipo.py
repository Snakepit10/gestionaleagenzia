from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0050_nations_solo_uefa'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriacosto',
            name='tipo',
            field=models.CharField(
                max_length=10, default='indiretto',
                choices=[('diretto', 'Diretto (variabile)'), ('indiretto', 'Indiretto (struttura)')],
                help_text="Diretto = costo variabile legato ai ricavi (entra nel margine di "
                          "contribuzione). Indiretto = costo fisso/di struttura."),
        ),
    ]
