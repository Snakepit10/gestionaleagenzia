"""
Registra (o rimuove) il webhook Telegram per ricevere i messaggi nel bot.

Uso:
    python manage.py set_telegram_webhook --base-url https://miodominio.up.railway.app
    python manage.py set_telegram_webhook            # usa env WEBHOOK_BASE_URL
    python manage.py set_telegram_webhook --delete   # rimuove il webhook

Prerequisiti (env): TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET.

Nota: con il webhook attivo, getUpdates (comando get_telegram_chats) non funziona
più finché il webhook non viene rimosso (--delete).
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Registra il webhook Telegram (o lo rimuove con --delete)"

    def add_arguments(self, parser):
        parser.add_argument('--base-url', type=str, default=None,
                            help="URL pubblico base dell'app (default: env WEBHOOK_BASE_URL)")
        parser.add_argument('--delete', action='store_true',
                            help="Rimuove il webhook invece di impostarlo")

    def handle(self, *args, **options):
        import requests

        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')

        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN mancante."))
            return

        if options['delete']:
            resp = requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=10)
            self.stdout.write(self.style.SUCCESS(f"deleteWebhook: {resp.status_code} {resp.text}"))
            return

        if not secret:
            self.stderr.write(self.style.ERROR("TELEGRAM_WEBHOOK_SECRET mancante."))
            return

        base_url = options['base_url'] or os.environ.get('WEBHOOK_BASE_URL', '')
        if not base_url:
            self.stderr.write(self.style.ERROR(
                "Base URL mancante: passa --base-url oppure imposta WEBHOOK_BASE_URL."
            ))
            return

        url = f"{base_url.rstrip('/')}/telegram/webhook/{secret}/"
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={'url': url, 'secret_token': secret},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get('ok'):
            self.stdout.write(self.style.SUCCESS(f"Webhook impostato su: {url}"))
        else:
            self.stderr.write(self.style.ERROR(f"Errore setWebhook: {resp.status_code} {resp.text}"))
