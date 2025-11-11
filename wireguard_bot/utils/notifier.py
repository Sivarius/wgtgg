# utils/notifier.py
from datetime import datetime
from utils.json_db import JsonDB
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"

async def send_notifications(bot):
    peers_db = JsonDB(str(CONFIG_DIR / "peers.json"))
    admins_db = JsonDB(str(CONFIG_DIR / "admins.json"))

    peers = peers_db.get_all()
    admins = admins_db.get_admins()
    now = datetime.now()

    for peer_id, peer in peers.items():
        expiry_str = peer.get("deactivate_date") or peer.get("date")
        if not expiry_str:
            continue
        dt = None
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                dt = datetime.strptime(expiry_str, fmt)
                break
            except ValueError:
                continue
        if not dt:
            continue
        days = (dt - now).days
        if 0 <= days < 3:
            for admin in admins:
                message = (
                    f"⚠️ Срок действия конфига {peer.get('name', '?')} (`{peer_id}`) "
                    f"истекает {expiry_str}\n\n"
                    f"Дата создания: {peer.get('created_at', 'N/A')}"
                )
                await bot.send_message(admin, message)
