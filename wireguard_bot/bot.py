import logging
from aiogram import Bot, Dispatcher, executor, types
from utils import wg_utils, json_db, notifier, disabler
import os
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
LOG_FILE = BASE_DIR / "logs" / "bot.txt"

API_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# базы данных
admins_db = json_db.JsonDB(str(CONFIG_DIR / "admins.json"))
peers_db = json_db.JsonDB(str(CONFIG_DIR / "peers.json"))
archive_db = json_db.JsonDB(str(CONFIG_DIR / "archive.json"))
last_ip_db = json_db.JsonDB(str(CONFIG_DIR / "last_ip.json"))

def log(msg: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

def is_admin(user_id: int) -> bool:
    return user_id in (admins_db.get("admins", []) or [])

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    log(f"User {message.from_user.id} called start/help")
    if not is_admin(message.from_user.id):
        log(f"Access denied on start/help: {message.from_user.id}")
        return
    await message.answer(
        " Добро пожаловать в WireGuard Bot!\n"
        "Доступные команды:\n"
        "/add name, dd.mm.yyyy — добавить пользователя\n"
        "/list — список активных\n"
        "/remove idN — отключить пользователя\n"
        "/edit idN dd.mm.yyyy — изменить срок\n"
        "/info idN — информация о пользователе\n"
        "/reload — применить и проверить состояние"
    )
    log(f"Sent help to {message.from_user.id}")

@dp.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    log(f"/add called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on add: {message.from_user.id}")
        return
    args = message.get_args()
    if not args or "," not in args:
        await message.reply("❌ Используй формат: /add имя, дата (например: /add ivan, 01.07.2025)")
        log(f"Bad args for /add by {message.from_user.id}")
        return
    try:
        name, date_str = args.split(",", 1)
        name = name.strip()
        expires = datetime.strptime(date_str.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
    except Exception as e:
        await message.reply("❌ Неверный формат даты.\nИспользуй: dd.mm.yyyy")
        log(f"Date parse error in /add by {message.from_user.id}: {e}")
        return
    client_id, config_text, client_data = wg_utils.generate_client_config(name, expires, last_ip_db, peers_db)
    peers_db.set(client_id, client_data)
    config_path = BASE_DIR / "wg" / "clients" / f"{client_id}.conf"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_text)
    await message.reply_document(types.InputFile(str(config_path)), caption=f"✅ Пользователь `{client_id}` добавлен.")
    log(f"Added client {client_id} by {message.from_user.id}")

@dp.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    log(f"/list called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on list: {message.from_user.id}")
        return
    users = peers_db.get_all()
    if not users:
        await message.reply("Нет активных пользователей.")
        log(f"No users for /list by {message.from_user.id}")
        return
    text = ""
    for uid, data in users.items():
        text += f"`{uid}`: {data['name']} — до {data['deactivate_date']} /edit {uid} /remove {uid} /info {uid}\n"
    await message.reply(text)
    log(f"Listed {len(users)} users to {message.from_user.id}")

@dp.message_handler(commands=["remove"])
async def cmd_remove(message: types.Message):
    log(f"/remove called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on remove: {message.from_user.id}")
        return
    uid = message.get_args().strip()
    user = peers_db.pop(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        log(f"Remove failed, not found {uid}")
        return
    archive_db.set(uid, user)
    wg_utils.remove_peer(uid)
    await message.reply(f" Пользователь `{uid}` отключён и перенесён в архив.")
    log(f"Removed {uid} by {message.from_user.id}")

@dp.message_handler(commands=["edit"])
async def cmd_edit(message: types.Message):
    log(f"/edit called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on edit: {message.from_user.id}")
        return
    args = message.get_args().strip().split()
    if len(args) != 2:
        await message.reply("❌ Используй формат: /edit idN dd.mm.yyyy")
        log(f"Bad args for /edit by {message.from_user.id}")
        return
    uid, new_date = args
    try:
        datetime.strptime(new_date, "%d.%m.%Y")
    except Exception as e:
        await message.reply("❌ Неверный формат даты.\nИспользуй: dd.mm.yyyy")
        log(f"Date error in /edit by {message.from_user.id}: {e}")
        return
    user = peers_db.get(uid) or archive_db.get(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        log(f"Edit failed, not found {uid}")
        return
    user["deactivate_date"] = new_date
    user["created_at"] = datetime.now().strftime("%d.%m.%Y")
    if uid in archive_db.get_all():
        archive_db.pop(uid)
        peers_db.set(uid, user)
        wg_utils.apply_peer(uid, user)
        await message.reply(f"♻️ Пользователь `{uid}` восстановлен и активен до {new_date}")
        log(f"Restored {uid} by {message.from_user.id}")
    else:
        peers_db.set(uid, user)
        await message.reply(f" Срок действия пользователя `{uid}` обновлён до {new_date}")
        log(f"Extended {uid} by {message.from_user.id}")

@dp.message_handler(commands=["info"])
async def cmd_info(message: types.Message):
    log(f"/info called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on info: {message.from_user.id}")
        return
    uid = message.get_args().strip()
    user = peers_db.get(uid) or archive_db.get(uid)
    if not user:
        await message.reply("❌ Пользователь не найден.")
        log(f"Info failed, not found {uid}")
        return
    info = (
        f" ID: `{uid}`\n"
        f"Имя: {user['name']}\n"
        f"IP: {user['ip']}\n"
        f"Создан: {user['created_at']}\n"
        f"Истекает: {user['deactivate_date']}\n"
    )
    await message.reply(info)
    log(f"Info shown for {uid} to {message.from_user.id}")

@dp.message_handler(commands=["reload"])
async def cmd_reload(message: types.Message):
    log(f"/reload called by {message.from_user.id}")
    if not is_admin(message.from_user.id):
        log(f"Access denied on reload: {message.from_user.id}")
        return
    users = peers_db.get_all()
    now = datetime.now()
    expired = [uid for uid, u in users.items()
               if datetime.strptime(u["deactivate_date"], "%d.%m.%Y") < now]
    for uid in expired:
        user = peers_db.pop(uid)
        archive_db.set(uid, user)
        wg_utils.remove_peer(uid)
    for uid, u in peers_db.get_all().items():
        wg_utils.apply_peer(uid, u)
    await message.reply(f" Завершено.\nПросроченных пользователей отключено: {len(expired)}")
    log(f"Reload: expired {len(expired)}, by {message.from_user.id}")

def schedule_daily_jobs():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(disabler.disable_expired_peers, "cron", hour=12, minute=0)
    scheduler.add_job(lambda: notifier.send_notifications(bot), "cron", hour=12, minute=0)
    scheduler.start()
    log("Scheduler started")

async def on_startup(dp):
    schedule_daily_jobs()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    schedule_daily_jobs()
    log("Bot started")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
