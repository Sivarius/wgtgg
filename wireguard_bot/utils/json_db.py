import json
import os
from datetime import datetime

PEERS_FILE = "wireguard_bot/config/peers.json"
ARCHIVE_FILE = "wireguard_bot/config/archive.json"

class JsonDB:
    def __init__(self, filepath):
        self.filepath = filepath
        self.data = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            self.data = {}
            self._save()
        else:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                try:
                    self.data = json.load(f)
                except json.JSONDecodeError:
                    self.data = {}

    def _save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_all(self):
        return self.data

    def get(self, user_id):
        return self.data.get(user_id)

    def exists(self, user_id):
        return user_id in self.data

    def add(self, user_dict):
        """
        Добавляет нового пользователя.
        Автоматически генерирует уникальный ID в формате idN.
        Возвращает сгенерированный ID.
        """
        new_id = self.get_next_id()
        self.data[new_id] = user_dict
        self._save()
        return new_id

    def update(self, user_id, updates: dict):
        if user_id in self.data:
            self.data[user_id].update(updates)
            self._save()
            return True
        return False

    def delete(self, user_id):
        if user_id in self.data:
            del self.data[user_id]
            self._save()
            return True
        return False

    def _generate_new_id(self):
        """
        Старый метод, больше не используется.
        """
        existing_ids = [int(k[2:]) for k in self.data.keys() if k.startswith("id") and k[2:].isdigit()]
        new_num = 1
        if existing_ids:
            new_num = max(existing_ids) + 1
        return f"id{new_num}"

    def get_next_id(self):
        """
        Генерация следующего ID на основе peers.json и archive.json
        """
        peers = []
        archive = []
        if os.path.exists(PEERS_FILE):
            with open(PEERS_FILE, 'r', encoding='utf-8') as f:
                try:
                    peers = json.load(f).get("peers", [])
                except json.JSONDecodeError:
                    pass

        if os.path.exists(ARCHIVE_FILE):
            with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                try:
                    archive = json.load(f).get("archive", [])
                except json.JSONDecodeError:
                    pass

        all_ids = peers + archive
        if not all_ids:
            return "id1"
        last_id = max(int(peer["id"][2:]) for peer in all_ids if "id" in peer and peer["id"].startswith("id"))
        return f"id{last_id + 1}"

    def find_by_ip(self, ip):
        """
        Возвращает user_id, если ip найден, иначе None
        """
        for uid, user in self.data.items():
            if user.get("ip") == ip:
                return uid
        return None

    def get_last_ip(self):
        """
        Для last_ip.json, где структура: {"last_ip": "10.8.0.22"}
        """
        return self.data.get("last_ip")

    def set_last_ip(self, ip):
        self.data["last_ip"] = ip
        self._save()

    def get_admins(self):
        """
        Для admins.json, где структура: {"admins": [123456, 789012]}
        Возвращает список админов
        """
        if isinstance(self.data, dict) and "admins" in self.data:
            return self.data["admins"]
        return []
