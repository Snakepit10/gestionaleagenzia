from django.db import migrations

from app.database_utils import AGENZIA_DATABASE_MAP


# Categorie di task di default, create in OGNI database agenzia (non su 'default').
# Idempotente: l'utente può poi modificarle/eliminarle/aggiungerne.
DEFAULT = [
    ('Manutenzione', 10),
    ('Acquisti', 20),
    ('Segnalazione assistenza', 30),
    ('Altro', 90),
]


def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    if alias not in AGENZIA_DATABASE_MAP.values():
        return
    CategoriaTask = apps.get_model('app', 'CategoriaTask')
    for nome, ordine in DEFAULT:
        CategoriaTask.objects.using(alias).get_or_create(
            nome=nome, defaults={'ordine': ordine, 'attivo': True})


def unseed(apps, schema_editor):
    # Non rimuoviamo nulla: possono essere state personalizzate.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0033_categoriatask_taskagenzia'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
