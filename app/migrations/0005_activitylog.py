# Generated by Django 5.2.1 on 2025-05-25 11:17

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_alter_contofinanziario_tipo_movimentoconti'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Creazione'), ('update', 'Modifica'), ('delete', 'Eliminazione'), ('status_change', 'Cambio di stato'), ('payment', 'Pagamento'), ('reopen', 'Riapertura')], max_length=20)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('description', models.TextField()),
                ('data_before', models.JSONField(blank=True, null=True)),
                ('data_after', models.JSONField(blank=True, null=True)),
                ('object_id', models.PositiveIntegerField()),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activity_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Log Attività',
                'verbose_name_plural': 'Log Attività',
                'ordering': ['-timestamp'],
            },
        ),
    ]
