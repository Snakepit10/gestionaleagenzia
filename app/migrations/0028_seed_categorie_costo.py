from django.db import migrations


# Esempi (suggerimenti) di macro-categorie di costo, ispirati alle voci B del conto
# economico civilistico. Vengono create solo sul database 'default' (tassonomia globale)
# e solo se non già presenti (idempotente): l'utente può modificarle o eliminarle.
ESEMPI = [
    ('personale', 'Personale', 10),
    ('servizi', 'Servizi', 20),
    ('godimento-beni-terzi', 'Godimento beni di terzi (affitti, noleggi)', 30),
    ('materie-consumo', 'Materie prime, sussidiarie e di consumo', 40),
    ('oneri-finanziari', 'Commissioni e oneri finanziari', 50),
    ('oneri-diversi', 'Oneri diversi di gestione', 60),
    ('ammortamenti', 'Ammortamenti e svalutazioni', 70),
]


def seed(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    CategoriaCosto = apps.get_model('app', 'CategoriaCosto')
    for codice, nome, ordine in ESEMPI:
        CategoriaCosto.objects.using('default').get_or_create(
            codice=codice, defaults={'nome': nome, 'ordine': ordine, 'attivo': True})


def unseed(apps, schema_editor):
    # Non rimuoviamo nulla: sono suggerimenti che l'utente può aver personalizzato.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0027_categoriacosto_categoriaspesa_categoria_costo_codice'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
