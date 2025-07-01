import logging
from aiogram import Bot, Dispatcher, executor, types
from utils import wg_utils, json_db
import os
from datetime import datetime
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from wireguard_bot.utils.notifier import send_notifications
from wireguard_bot.utils.disabler import disable_expired_peers

API_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

admins_db = json_db.JsonDB("wireguard_bot/config/admins.json")
peers_db = json_db.JsonDB("wireguard_bot/config/peers.json")
archive_db = json_db.JsonDB("wireguard_bot/config/archive.json")
last_ip_db = json_db.JsonDB("wireguard_bot/config/last_ip.json")

def is_admin(user_id: int) -> bool:
    return user_id in admins_db.get("admins", [])

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👋 Добро пожаловать в WireGuard Bot!\n"
        "Доступные команды:\n"
        "/add name, dd.mm.yyyy — добавить пользователя\n"
        "/list — список активных\n"
        "/remove idN — отключить пользователя\n"
        "/edit idN dd.mm.yyyy — изменить срок\n"
        "/info idN — информация о пользователе\n"
        "/reload — применить и проверить состояние"
    )

@dp.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.get_args()
    if not args or "," not in args:
        await message.reply("❌ Используй формат: /add имя, дата (например: /add ivan, 01.07.2025)")
        return

    try:
        name, date_str = args.split(",", 1)
        name = name.strip()
        expires = datetime.strptime(date_str.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
    except ValueError:
        await message.reply("❌ Неверный формат даты. Используй: dd.mm.yyyy")
        return

    client_id, config_text, client_data = wg_utils.generate_client_config(name, expires, last_ip_db, peers_db)
    peers_db.set(client_id, client_data)

    config_path = f"wireguard_bot/wg/clients/{client_id}.conf"
    with open(config_path, "w") as f:
        f.write(config_text)

    await message.reply_document(types.InputFile(config_path), caption=f"✅ Пользователь `{client_id}` добавлен.")

@dp.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    users = peers_db.get_all()
    if not users:
        await message.reply("Нет активных пользователей.")
        return

    text = ""
    for uid, data in users.items():
        name = data["name"]
        expires = data["deactivate_date"]
        text += f"`{uid}`: {name} — до {expires} /edit {uid} /remove {uid} /info {uid}\n"
    await message.reply(text)

@dp.message_handler(commands=["remove"])
async def cmd_remove(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    uid = message.get_args().strip()
    user = peers_db.pop(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return

    archive_db.set(uid, user)
    wg_utils.remove_peer(uid)
    await message.reply(f"🚫 Пользователь `{uid}` отключён и перенесён в архив.")

@dp.message_handler(commands=["edit"])
async def cmd_edit(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.get_args().strip().split()
    if len(args) != 2:
        await message.reply("❌ Используй формат: /edit idN dd.mm.yyyy")
        return

    uid, new_date = args
    try:
        datetime.strptime(new_date, "%d.%m.%Y")
    except ValueError:
        await message.reply("❌ Неверный формат даты. Используй: dd.mm.yyyy")
        return

    user = peers_db.get(uid) or archive_db.get(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return

    user["deactivate_date"] = new_date
    user["created_at"] = datetime.now().strftime("%d.%m.%Y")

    # Возвращаем из архива если нужно
    if uid in archive_db.get_all():
        archive_db.pop(uid)
        peers_db.set(uid, user)
        wg_utils.apply_peer(uid, user)
        await message.reply(f"♻️ Пользователь `{uid}` восстановлен и активен до {new_date}")
    else:
        peers_db.set(uid, user)
        await message.reply(f"📝 Срок действия пользователя `{uid}` обновлён до {new_date}")

@dp.message_handler(commands=["info"])
async def cmd_info(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    uid = message.get_args().strip()
    user = peers_db.get(uid) or archive_db.get(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        return

    info = (
        f"👤 ID: `{uid}`\n"
        f"Имя: {user['name']}\n"
        f"IP: {user['ip']}\n"
        f"Создан: {user['created_at']}\n"
        f"Истекает: {user['deactivate_date']}\n"
    )
    await message.reply(info)

@dp.message_handler(commands=["reload"])
async def cmd_reload(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    users = peers_db.get_all()
    now = datetime.now()
    expired = []

    for uid, user in users.items():
        expire_date = datetime.strptime(user["deactivate_date"], "%d.%m.%Y")
        if expire_date < now:
            expired.append(uid)

    for uid in expired:
        user = peers_db.pop(uid)
        archive_db.set(uid, user)
        wg_utils.remove_peer(uid)

    for uid, user in peers_db.get_all().items():
        wg_utils.apply_peer(uid, user)

    await message.reply(f"🔄 Завершено. Просроченных пользователей отключено: {len(expired)}")
    
    # 🔁 Планировщик
async def schedule_daily_jobs():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(disable_expired_peers, "cron", hour=12, minute=0)
    scheduler.add_job(lambda: send_notifications(bot), "cron", hour=12, minute=0)
    scheduler.start()

async def on_startup(dp):
    await schedule_daily_jobs()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
