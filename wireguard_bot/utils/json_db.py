import json
import os
import logging
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PEERS_FILE = CONFIG_DIR / "peers.json"
ARCHIVE_FILE = CONFIG_DIR / "archive.json"

logger = logging.getLogger("JsonDB")
logger.setLevel(logging.INFO)

class JsonDB:
    def __init__(self, filepath: str):
        self.filepath = str(filepath)
        self.path = Path(self.filepath)
        self.data = {}
        logger.debug(f"Инициализация JsonDB с файлом: {self.filepath}")
        self._load()

    def _load(self):
        if not self.path.exists():
            logger.info(f"Файл {self.filepath} не найден, создаётся новый пустой")
            self.data = {}
            self._save()
            return
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw = f.read().strip()
                self.data = json.loads(raw) if raw else {}
            if not isinstance(self.data, dict):
                logger.warning(f"Ожидался объект JSON в {self.filepath}, получено {type(self.data)}; сброс в {}")
                self.data = {}
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {self.filepath}, данные сброшены")
            self.data = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Данные сохранены в {self.filepath}, записей: {len(self.data)}")

    # Public API
    def save(self):
        self._save()

    def get_all(self) -> dict:
        return self.data

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self._save()

    def pop(self, key):
        value = self.data.pop(key, None)
        self._save()
        return value

    def add(self, obj: dict) -> str:
        new_id = self.get_next_id()
        self.data[new_id] = obj
        self._save()
        return new_id

    def replace_all(self, new_dict: dict):
        self.data = dict(new_dict)
        self._save()

    def get_next_id(self) -> str:
        def extract_ids(mapping: dict):
            return [int(k[2:]) for k in mapping.keys() if isinstance(k, str) and k.startswith("id") and k[2:].isdigit()]

        current_ids = extract_ids(self.data)
        other_ids = []
        # try reading peers and archive as dicts
        for p in (PEERS_FILE, ARCHIVE_FILE):
            if p.exists():
                try:
                    txt = p.read_text(encoding='utf-8').strip()
                    obj = json.loads(txt) if txt else {}
                    if isinstance(obj, dict):
                        other_ids.extend(extract_ids(obj))
                except json.JSONDecodeError:
                    logger.warning(f"Невалидный JSON в {p}, пропуск при расчёте ID")
        all_ids = current_ids + other_ids
        next_num = (max(all_ids) + 1) if all_ids else 1
        return f"id{next_num}"

    # Convenience helpers for specific files
    def get_last_ip(self):
        return self.data.get("last_ip")

    def set_last_ip(self, ip: str):
        self.data["last_ip"] = ip
        self._save()

    def get_admins(self):
        return self.data.get("admins", []) if isinstance(self.data, dict) else []
