import json
import datetime
import os
import sys
import telegram

# Токен Telegram-бота вписан прямо сюда:
TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

# Пути к конфигам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEERS_PATH = os.path.join(BASE_DIR, "config", "peers.json")
ADMINS_PATH = os.path.join(BASE_DIR, "config", "admins.json")

# Кол-во дней до отключения, при котором отправляется уведомление
WARNING_DAYS = 3


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def parse_date(date_str):
    try:
        return datetime.datetime.strptime(date_str, "%d.%m.%y").date()
    except ValueError:
        return None


def should_warn(expiration_date):
    today = datetime.date.today()
    return 0 <= (expiration_date - today).days <= WARNING_DAYS


def build_message(peer):
    return (
        f"⚠️ *Напоминание об окончании срока подключения:*\n\n"
        f"*ID:* `{peer['id']}`\n"
        f"*Имя:* {peer['name']}\n"
        f"*Создан:* {peer['created_at']}\n"
        f"*Истекает:* {peer['expires']}\n"
    )


def notify_admins(peers, admins, bot):
    for peer in peers:
        exp_date = parse_date(peer.get("expires", ""))
        if not exp_date or not should_warn(exp_date):
            continue

        message = build_message(peer)
        for admin_id in admins:
            try:
                bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
            except Exception as e:
                print(f"❌ Не удалось отправить сообщение администратору {admin_id}: {e}")


def main():
    bot = telegram.Bot(token=TOKEN)

    peers = load_json(PEERS_PATH)
    admins = load_json(ADMINS_PATH).get("admins", [])

    if not peers or not admins:
        print("⚠️ Нет активных пиров или список админов пуст.")
        return

    notify_admins(peers, admins, bot)


if __name__ == "__main__":
    main()
