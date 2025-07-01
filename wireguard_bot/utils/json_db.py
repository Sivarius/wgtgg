import json
import os
import logging
from datetime import datetime

PEERS_FILE = "wireguard_bot/config/peers.json"
ARCHIVE_FILE = "wireguard_bot/config/archive.json"

logger = logging.getLogger("JsonDB")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

class JsonDB:
    def __init__(self, filepath):
        self.filepath = filepath
        self.data = {}
        logger.debug(f"Инициализация JsonDB с файлом: {filepath}")
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            logger.info(f"Файл {self.filepath} не найден, создаётся новый пустой")
            self.data = {}
            self._save()
        else:
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                logger.info(f"Данные загружены из {self.filepath}, записей: {len(self.data)}")
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON в {self.filepath}, данные сброшены")
                self.data = {}

    def _save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logger.info(f"Данные сохранены в {self.filepath}, записей: {len(self.data)}")

    def get_all(self):
        logger.debug("Получение всех данных")
        return self.data

    def get(self, user_id):
        logger.debug(f"Получение данных по ID: {user_id}")
        return self.data.get(user_id)

    def exists(self, user_id):
        exists = user_id in self.data
        logger.debug(f"Проверка существования ID {user_id}: {exists}")
        return exists

    def add(self, user_dict):
        new_id = self.get_next_id()
        self.data[new_id] = user_dict
        self._save()
        logger.info(f"Добавлен новый пользователь с ID {new_id}")
        return new_id

    def update(self, user_id, updates: dict):
        if user_id in self.data:
            self.data[user_id].update(updates)
            self._save()
            logger.info(f"Обновлены данные пользователя {user_id}")
            return True
        logger.warning(f"Попытка обновления несуществующего ID {user_id}")
        return False

    def delete(self, user_id):
        if user_id in self.data:
            del self.data[user_id]
            self._save()
            logger.info(f"Удалён пользователь с ID {user_id}")
            return True
        logger.warning(f"Попытка удаления несуществующего ID {user_id}")
        return False

    def _generate_new_id(self):
        existing_ids = [int(k[2:]) for k in self.data.keys() if k.startswith("id") and k[2:].isdigit()]
        new_num = 1
        if existing_ids:
            new_num = max(existing_ids) + 1
        logger.debug(f"Сгенерирован новый ID: id{new_num}")
        return f"id{new_num}"

    def get_next_id(self):
        peers = []
        archive = []
        if os.path.exists(PEERS_FILE):
            try:
                with open(PEERS_FILE, 'r', encoding='utf-8') as f:
                    peers = json.load(f).get("peers", [])
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON в {PEERS_FILE}")
        if os.path.exists(ARCHIVE_FILE):
            try:
                with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                    archive = json.load(f).get("archive", [])
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON в {ARCHIVE_FILE}")

        all_ids = peers + archive
        if not all_ids:
            logger.debug("Список ID пуст, возвращается id1")
            return "id1"
        last_id = max(int(peer["id"][2:]) for peer in all_ids if "id" in peer and peer["id"].startswith("id"))
        next_id = f"id{last_id + 1}"
        logger.debug(f"Следующий ID сгенерирован: {next_id}")
        return next_id

    def find_by_ip(self, ip):
        for uid, user in self.data.items():
            if user.get("ip") == ip:
                logger.debug(f"Найден пользователь по IP {ip}: {uid}")
                return uid
        logger.debug(f"Пользователь с IP {ip} не найден")
        return None

    def get_last_ip(self):
        last_ip = self.data.get("last_ip")
        logger.debug(f"Получен последний IP: {last_ip}")
        return last_ip

    def set_last_ip(self, ip):
        self.data["last_ip"] = ip
        self._save()
        logger.info(f"Установлен последний IP: {ip}")

    def get_admins(self):
        admins = self.data.get("admins", []) if isinstance(self.data, dict) else []
        logger.debug(f"Получен список админов: {admins}")
        return admins
