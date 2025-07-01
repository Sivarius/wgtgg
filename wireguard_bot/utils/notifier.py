# wireguard_bot/utils/notifier.py
from datetime import datetime
from wireguard_bot.utils.json_db import load_json

async def send_notifications(bot):
    peers_data = load_json("config/peers.json")
    peers = peers_data.get("peers", [])

    admins_data = load_json("config/admins.json")
    admins = admins_data.get("admins", [])

    now = datetime.now()

    for peer in peers:
        expiry_str = peer.get("date")
        if not expiry_str:
            continue

        try:
            expiry_date = datetime.strptime(expiry_str, "%d.%m.%y")
        except ValueError:
            continue

        if 0 <= (expiry_date - now).days < 3:
            for admin in admins:
                message = (
                    f"\u26a0\ufe0f Срок действия конфига *{peer['name']}* (`{peer['id']}`) "
                    f"истекает *{peer['date']}*\n\n"
                    f"Дата создания: {peer.get('created_at', 'N/A')}"
                )
                await bot.send_message(admin, message, parse_mode="Markdown")
