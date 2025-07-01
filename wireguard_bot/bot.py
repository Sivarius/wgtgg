import os
from datetime import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from utils.json_db import JsonDB
from utils.wg_utils import generate_client_config, apply_peer, remove_peer

TOKEN = os.getenv("TG_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Не задана переменная окружения TG_BOT_TOKEN")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
peers_db = JsonDB(os.path.join(CONFIG_DIR, "peers.json"))
archive_db = JsonDB(os.path.join(CONFIG_DIR, "archive.json"))
admins_db = JsonDB(os.path.join(CONFIG_DIR, "admins.json"))

WG_CLIENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wg", "clients")

def is_admin(user_id: int) -> bool:
    admins = admins_db.get("admins") or []
    return user_id in admins

class AddClientState(StatesGroup):
    waiting_for_name_date = State()

class EditClientState(StatesGroup):
    waiting_for_new_date = State()

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я WireGuard бот. Используйте команды:\n"
                         "/add - добавить пользователя\n"
                         "/list - список пользователей\n"
                         "/remove idN - удалить пользователя\n"
                         "/edit idN - изменить дату отключения\n"
                         "/info idN - информация о пользователе\n"
                         "/reload - синхронизировать конфигурации с сервером")

@dp.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return
    await message.answer("Введите имя и дату отключения в формате: Имя, ДД.MM.ГГГГ\n"
                         "Пример: Иван, 08.07.2025")
    await AddClientState.waiting_for_name_date.set()

@dp.message_handler(state=AddClientState.waiting_for_name_date)
async def process_add_name_date(message: types.Message, state: FSMContext):
    try:
        name, date_str = map(str.strip, message.text.split(",", 1))
        deactivate_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    except Exception:
        await message.answer("Неверный формат. Введите в формате: Имя, ДД.MM.ГГГГ")
        return

    client_id, conf_path = generate_client_config(name, deactivate_date)
    await message.answer(f"Пользователь добавлен с ID {client_id}. Конфиг сгенерирован.")

    with open(conf_path, "rb") as conf_file:
        await bot.send_document(message.from_user.id, conf_file, caption=f"Конфиг для {name} (ID {client_id})")

    await state.finish()

@dp.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return

    peers = peers_db.get_all()
    if not peers:
        await message.answer("Список пользователей пуст.")
        return

    lines = []
    for user_id, data in peers.items():
        line = (f"id{user_id}: {data['name']} - IP: {data['ip']} - "
                f"отключение: {data['deactivate_date']}\n"
                f"/remove id{user_id} | /edit id{user_id} | /info id{user_id}")
        lines.append(line)

    await message.answer("\n\n".join(lines))

@dp.message_handler(commands=["remove"])
async def cmd_remove(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return

    args = message.get_args()
    if not args.startswith("id"):
        await message.answer("Укажите ID пользователя для удаления: /remove idN")
        return
    user_id = args

    user_data = peers_db.get(user_id)
    if not user_data:
        await message.answer(f"Пользователь `{user_id}` не найден.", parse_mode="Markdown")
        return

    # Переносим в архив
    archive_db.data[user_id] = user_data
    archive_db._save()
    peers_db.delete(user_id)

    # Удаляем файл конфига
    conf_path = os.path.join(WG_CLIENTS_DIR, f"{user_id}.conf")
    if os.path.exists(conf_path):
        os.remove(conf_path)

    # Убираем из WireGuard
    remove_peer(user_id)

    await message.answer(f"Пользователь `{user_id}` удалён и архивирован.", parse_mode="Markdown")

@dp.message_handler(commands=["info"])
async def cmd_info(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return

    args = message.get_args()
    if not args.startswith("id"):
        await message.answer("Укажите ID пользователя для информации: /info idN")
        return
    user_id = args

    user_data = peers_db.get(user_id)
    if not user_data:
        await message.answer(f"Пользователь `{user_id}` не найден.", parse_mode="Markdown")
        return

    info_text = (f"ID: {user_id}\n"
                 f"Имя: {user_data['name']}\n"
                 f"IP: {user_data['ip']}\n"
                 f"Дата отключения: {user_data['deactivate_date']}\n"
                 f"Публичный ключ: {user_data['public_key']}")
    await message.answer(info_text)

@dp.message_handler(commands=["edit"])
async def cmd_edit(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return

    args = message.get_args()
    if not args.startswith("id"):
        await message.answer("Укажите ID пользователя: /edit idN")
        return

    user_id = args
    user_data = peers_db.get(user_id)
    if not user_data:
        await message.answer(f"Пользователь `{user_id}` не найден.", parse_mode="Markdown")
        return

    await state.update_data(edit_user_id=user_id)
    await EditClientState.waiting_for_new_date.set()
    await message.answer(f"Введите новую дату отключения для пользователя `{user_id}` в формате ДД.MM.ГГГГ", parse_mode="Markdown")

@dp.message_handler(state=EditClientState.waiting_for_new_date)
async def process_new_date(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = user_data.get("edit_user_id")
    try:
        new_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте снова в формате ДД.MM.ГГГГ")
        return

    user_record = peers_db.get(user_id)
    user_record["deactivate_date"] = new_date.strftime("%d.%m.%Y")
    peers_db.data[user_id] = user_record
    peers_db._save()

    await message.answer(f"Дата отключения пользователя `{user_id}` обновлена на {new_date.strftime('%d.%m.%Y')}", parse_mode="Markdown")
    await state.finish()

@dp.message_handler(commands=["reload"])
async def cmd_reload(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав для использования этой команды.")
        return

    peers = peers_db.get_all()
    archive = archive_db.get_all()

    # Получаем список файлов конфигов в папке wg/clients
    conf_files = set(f for f in os.listdir(WG_CLIENTS_DIR) if f.endswith(".conf"))

    applied = []
    removed = []
    errors = []

    # Подключаем пользователей из peers.json
    for user_id, data in peers.items():
        conf_filename = f"{user_id}.conf"
        if conf_filename not in conf_files:
            errors.append(f"{user_id} - отсутствует конфиг {conf_filename}")
            continue
        try:
            apply_peer(user_id, data)
            applied.append(user_id)
        except Exception as e:
            errors.append(f"Ошибка подключения {user_id}: {str(e)}")

    # Отключаем пользователей из archive.json
    for user_id, data in archive.items():
        conf_filename = f"{user_id}.conf"
        if conf_filename in conf_files:
            try:
                remove_peer(user_id)
                removed.append(user_id)
            except Exception as e:
                errors.append(f"Ошибка отключения {user_id}: {str(e)}")

    msg_lines = []
    if applied:
        msg_lines.append("Подключены пользователи: " + ", ".join(applied))
    if removed:
        msg_lines.append("Отключены пользователи: " + ", ".join(removed))
    if errors:
        msg_lines.append("Ошибки:\n" + "\n".join(errors))

    if not msg_lines:
        msg_lines.append("Сервер и база в актуальном состоянии.")

    await message.answer("\n".join(msg_lines))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)