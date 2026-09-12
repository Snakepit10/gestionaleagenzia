from django.db import migrations


# Crea il gruppo "Conto Economico": assegnandovi un utente (da Django admin) gli si abilita
# l'accesso alla sezione Conto Economico anche senza renderlo super-user.
def crea_gruppo(apps, schema_editor):
    if schema_editor.connection.alias != 'default':
        return
    Group = apps.get_model('auth', 'Group')
    Group.objects.using('default').get_or_create(name='Conto Economico')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0030_cliente_nascosto'),
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crea_gruppo, noop),
    ]
