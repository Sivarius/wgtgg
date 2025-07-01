# wireguard_bot/utils/notifier.py
import json
from datetime import datetime, timedelta
from wireguard_bot.config import paths
from wireguard_bot.utils.json_db import load_admins, load_peers
from aiogram import Bot

async def send_notifications(bot: Bot):
    peers = load_peers()
    admins = load_admins()
    now = datetime.now()

    for peer_id, peer in peers.items():
        expires = datetime.strptime(peer["expires"], "%d.%m.%y")
        if 0 <= (expires - now).days < 3:
            for admin in admins:
                message = (
                    f"⚠️ Срок действия конфига *{peer['name']}* (`{peer_id}`) "
                    f"истекает *{peer['expires']}*\n\n"
                    f"Дата создания: {peer['created_at']}"
                )
                await bot.send_message(admin, message, parse_mode="Markdown")
