from django.db import migrations


# Sposta tra le righe "escluse" i movimenti bancari già importati (ancora da classificare)
# che corrispondono a causali non rilevanti per il conto economico (incassi POS, versamenti,
# giroconti, rimesse di gioco al concessionario). Non tocca le righe già classificate.
TERMINI = [
    'incasso tramite p.o.s',
    'vers. cont. atm',
    'giroconto',
    'gbo italy',
]


def escludi_esistenti(apps, schema_editor):
    db = schema_editor.connection.alias
    MovimentoBancario = apps.get_model('app', 'MovimentoBancario')
    for term in TERMINI:
        MovimentoBancario.objects.using(db).filter(
            stato='da_classificare', descrizione__icontains=term).update(stato='ignorato')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0028_seed_categorie_costo'),
    ]

    operations = [
        migrations.RunPython(escludi_esistenti, noop),
    ]
