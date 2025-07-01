import os
import subprocess
from datetime import datetime
from pathlib import Path
from utils.json_db import JsonDB

CONFIG_DIR = Path(__file__).parent.parent / "config"
PEERS_PATH = CONFIG_DIR / "peers.json"
ARCHIVE_PATH = CONFIG_DIR / "archive.json"
TEMPLATE_PATH = CONFIG_DIR / "template.conf"
WG_CLIENTS_DIR = Path(__file__).parent.parent / "wg" / "clients"

WG_INTERFACE = "wg0"


def _run_command(command):
    result = subprocess.run(command, shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"Ошибка при выполнении команды: {command}\n"
                           f"{result.stderr.decode()}")
    return result.stdout.decode().strip()


def _increment_ip(last_ip: str) -> str:
    parts = last_ip.split(".")
    last_octet = int(parts[-1]) + 1
    if last_octet > 254:
        raise ValueError("Достигнут максимум IP-адресов в подсети")
    parts[-1] = str(last_octet)
    return ".".join(parts)


def _generate_keys():
    private_key = _run_command("wg genkey")
    public_key = _run_command(f"echo {private_key} | wg pubkey")
    preshared_key = _run_command("wg genpsk")
    return private_key, public_key, preshared_key


def _load_template():
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Не найден шаблон конфига {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def generate_client_config(client_name: str, deactivate_date: datetime.date):
    peers_db = JsonDB(str(PEERS_PATH))
    last_ip_db = JsonDB(str(CONFIG_DIR / "last_ip.json"))

    last_ip = last_ip_db.get_last_ip() or "10.8.0.1"
    new_ip = _increment_ip(last_ip)
    last_ip_db.set_last_ip(new_ip)

    priv_key, pub_key, psk_key = _generate_keys()
    template = _load_template()
    config_text = (template
                   .replace("%AD%", new_ip)
                   .replace("%PrK%", priv_key)
                   .replace("%PhK%", psk_key))

    user_data = {
        "name": client_name,
        "ip": new_ip,
        "private_key": priv_key,
        "public_key": pub_key,
        "preshared_key": psk_key,
        "deactivate_date": deactivate_date.strftime("%Y-%m-%d"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    client_id = peers_db.add(user_data)

    WG_CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    conf_path = WG_CLIENTS_DIR / f"{client_id}.conf"
    conf_path.write_text(config_text, encoding="utf-8")

    return client_id, str(conf_path)


def apply_peer(client_id: str):
    peers_db = JsonDB(str(PEERS_PATH))
    peer = peers_db.get(client_id)
    if not peer:
        raise ValueError(f"Пользователь с ID {client_id} не найден")

    command = (
        f"wg set {WG_INTERFACE} "
        f"peer {peer['public_key']} "
        f"preshared-key <(echo {peer['preshared_key']}) "
        f"allowed-ips {peer['ip']}/32"
    )
    _run_command(f"bash -c '{command}'")


def remove_peer(client_id: str):
    peers_db = JsonDB(str(PEERS_PATH))
    peer = peers_db.get(client_id)
    if not peer:
        raise ValueError(f"Пользователь с ID {client_id} не найден")

    command = f"wg set {WG_INTERFACE} peer {peer['public_key']} remove"
    _run_command(command)


def apply_peers():
    """Добавляет актуальных пиров, переносит истекших в архив."""
    peers_db = JsonDB(str(PEERS_PATH))
    archive_db = JsonDB(str(ARCHIVE_PATH))
    updated = []

    today = datetime.today()

    for peer in peers_db.get_all():
        expires = peer.get("deactivate_date") or peer.get("expires")  # совместимость
        try:
            expires_date = datetime.strptime(expires, "%Y-%m-%d")
        except Exception:
            archive_db.add(peer)
            continue

        if expires_date < today:
            archive_db.add(peer)
        else:
            # добавляем в интерфейс
            _run_command(
                f"wg set {WG_INTERFACE} peer {peer['public_key']} "
                f"preshared-key <(echo {peer['preshared_key']}) "
                f"allowed-ips {peer['ip']}/32"
            )
            updated.append(peer)

    # перезапись файлов
    peers_db.replace_all(updated)
    archive_db.save()

    _run_command(f"systemctl restart wg-quick@{WG_INTERFACE}")  # добавлен перезапуск


def remove_peers():
    """Удаляет из интерфейса всех пиров из архива."""
    archive_db = JsonDB(str(ARCHIVE_PATH))
    for peer in archive_db.get_all():
        pub = peer.get("public_key")
        if pub:
            _run_command(f"wg set {WG_INTERFACE} peer {pub} remove")

    _run_command(f"systemctl restart wg-quick@{WG_INTERFACE}")  # добавлен перезапуск