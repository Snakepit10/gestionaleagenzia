"""
Comando di utilità per recuperare i chat_id delle chat/gruppi Telegram.

Uso:
    python manage.py get_telegram_chats
    python manage.py get_telegram_chats --token 123456:ABC...

Prerequisiti:
    1. Aver creato il bot con @BotFather e avere il token.
    2. Aver aggiunto il bot al gruppo (o avergli scritto in privato).
    3. Aver inviato almeno UN messaggio nella chat dopo aver aggiunto il bot
       (per i gruppi, conviene menzionare il bot o disattivarne la privacy
       da @BotFather -> /setprivacy -> Disable).

Il comando interroga l'endpoint getUpdates e stampa, per ogni chat trovata,
il chat_id da incollare in admin -> Agenzie -> "Telegram chat id".
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Elenca i chat_id delle chat/gruppi Telegram raggiungibili dal bot"

    def add_arguments(self, parser):
        parser.add_argument(
            '--token',
            type=str,
            default=None,
            help="Token del bot (default: settings.TELEGRAM_BOT_TOKEN / env TELEGRAM_BOT_TOKEN)",
        )

    def handle(self, *args, **options):
        import requests

        token = options['token'] or getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            self.stderr.write(self.style.ERROR(
                "Token mancante. Passa --token oppure imposta TELEGRAM_BOT_TOKEN."
            ))
            return

        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                timeout=10,
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Errore di rete: {e}"))
            return

        if resp.status_code != 200:
            self.stderr.write(self.style.ERROR(
                f"Telegram ha risposto {resp.status_code}: {resp.text}"
            ))
            return

        data = resp.json()
        if not data.get('ok'):
            self.stderr.write(self.style.ERROR(f"Risposta non valida: {data}"))
            return

        # Raccoglie le chat uniche da tutti i tipi di update
        chats = {}
        for update in data.get('result', []):
            for key in ('message', 'edited_message', 'channel_post', 'my_chat_member'):
                obj = update.get(key)
                if obj and 'chat' in obj:
                    chat = obj['chat']
                    chats[chat['id']] = chat

        if not chats:
            self.stdout.write(self.style.WARNING(
                "Nessuna chat trovata. Invia un messaggio nella chat/gruppo "
                "(menzionando il bot nei gruppi) e riprova.\n"
                "Nota: getUpdates non funziona se è attivo un webhook sul bot."
            ))
            return

        self.stdout.write(self.style.SUCCESS(f"Trovate {len(chats)} chat:\n"))
        for chat_id, chat in chats.items():
            titolo = chat.get('title') or " ".join(
                filter(None, [chat.get('first_name'), chat.get('last_name')])
            ) or chat.get('username') or '(senza nome)'
            tipo = chat.get('type', '?')
            self.stdout.write(f"  chat_id = {chat_id}")
            self.stdout.write(f"           tipo: {tipo} | nome: {titolo}\n")
