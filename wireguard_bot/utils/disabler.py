import logging
from datetime import datetime
from pathlib import Path

from utils.json_db import JsonDB
from utils.wg_utils import remove_peer

BASE_DIR = Path(__file__).parent.parent  # wireguard_bot/
PEERS_PATH = BASE_DIR / "config" / "peers.json"
ARCHIVE_PATH = BASE_DIR / "config" / "archive.json"

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    peers_db = JsonDB(str(PEERS_PATH))
    archive_db = JsonDB(str(ARCHIVE_PATH))

    peers = peers_db.get_all()
    if not peers:
        logging.info("peers.json пустой, отключать нечего.")
        return

    today = datetime.now().date()
    expired_users = []

    # Ищем просроченных
    for user_id, user_data in list(peers.items()):
        expires_str = user_data.get("expires")
        if not expires_str:
            continue

        try:
            expires_date = datetime.strptime(expires_str, "%d.%m.%Y").date()
        except ValueError:
            logging.warning(f"Неверный формат даты expires для {user_id}: {expires_str}")
            continue

        if expires_date < today:
            logging.info(f"Пользователь {user_id} ({user_data.get('name')}) просрочен, отключаем и архивируем.")
            expired_users.append(user_id)

    if not expired_users:
        logging.info("Просроченных пользователей не найдено.")
        return

    # Отключаем и архивируем
    for uid in expired_users:
        user = peers_db.get(uid)
        if user is None:
            continue

        try:
            remove_peer(user["ip"])  # отключаем в wireguard
            logging.info(f"Пользователь {uid} отключён от WireGuard.")
        except Exception as e:
            logging.error(f"Ошибка при отключении {uid}: {e}")

        # Переносим в архив (новый ID с генерацией внутри JsonDB)
        archive_db.add(user)
        peers_db.delete(uid)

    logging.info("Завершено отключение и архивирование просроченных пользователей.")

if __name__ == "__main__":
    main()
