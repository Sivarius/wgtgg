import os
import subprocess
import platform
import tempfile
import base64
from datetime import datetime
from pathlib import Path
from utils.json_db import JsonDB

CONFIG_DIR = Path(__file__).parent.parent / "config"
PEERS_PATH = CONFIG_DIR / "peers.json"
ARCHIVE_PATH = CONFIG_DIR / "archive.json"
TEMPLATE_PATH = CONFIG_DIR / "template.conf"

WG_INTERFACE = os.getenv("WG_INTERFACE", "wg0")
LOG_FILE = Path(__file__).parent.parent / "logs" / "wg_utils.log"

def log(message: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def _is_linux():
    return platform.system().lower() == "linux"


def _run_command(command):
    log(f"Выполнение команды: {command}")
    result = subprocess.run(command, shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    if result.returncode != 0:
        error_msg = result.stderr.decode(errors="ignore")
        log(f"Ошибка при выполнении команды: {command}\nОшибка: {error_msg}")
        raise RuntimeError(f"Ошибка при выполнении команды: {command}\n{error_msg}")
    output = result.stdout.decode(errors="ignore").strip()
    log(f"Результат команды: {output}")
    return output


def _increment_ip(last_ip: str) -> str:
    log(f"Инкремент IP: {last_ip}")
    parts = last_ip.split(".")
    last_octet = int(parts[-1]) + 1
    if last_octet > 254:
        log("Достигнут максимум IP-адресов в подсети")
        raise ValueError("Достигнут максимум IP-адресов в подсети")
    parts[-1] = str(last_octet)
    new_ip = ".".join(parts)
    log(f"Новый IP: {new_ip}")
    return new_ip


def _generate_keys():
    log("Генерация ключей WireGuard")
    if _is_linux():
        try:
            private_key = _run_command("wg genkey")
            public_key = _run_command(f"echo {private_key} | wg pubkey")
            preshared_key = _run_command("wg genpsk")
            log("Ключи сгенерированы через wg")
            return private_key, public_key, preshared_key
        except Exception:
            log("wg недоступен, переход к генерации фиктивных ключей для разработки")
    # Fallback: generate pseudo-keys for non-Linux/dev
    def b64(n):
        return base64.b64encode(os.urandom(n)).decode().rstrip("=")
    return (
        f"FAKE_PRIV_{b64(32)}",
        f"FAKE_PUB_{b64(32)}",
        f"FAKE_PSK_{b64(32)}",
    )


def _load_template():
    log(f"Загрузка шаблона конфига из {TEMPLATE_PATH}")
    if not TEMPLATE_PATH.exists():
        log(f"Шаблон конфига не найден: {TEMPLATE_PATH}")
        raise FileNotFoundError(f"Не найден шаблон конфига {TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    log("Шаблон конфига загружен")
    return template


def generate_client_config(client_name: str, deactivate_date_str: str, last_ip_db: JsonDB, peers_db: JsonDB):
    log(f"Генерация конфига: {client_name}, деактивация: {deactivate_date_str}")
    last_ip = last_ip_db.get_last_ip() or "10.8.0.1"
    new_ip = _increment_ip(last_ip)
    last_ip_db.set_last_ip(new_ip)

    priv_key, pub_key, psk_key = _generate_keys()
    template = _load_template()
    config_text = (template
                   .replace("%AD%", new_ip)
                   .replace("%PrK%", priv_key)
                   .replace("%PhK%", psk_key))

    client_id = peers_db.get_next_id()
    user_data = {
        "name": client_name,
        "ip": new_ip,
        "private_key": priv_key,
        "public_key": pub_key,
        "preshared_key": psk_key,
        "deactivate_date": deactivate_date_str,  # dd.mm.YYYY
        "created_at": datetime.now().strftime("%d.%m.%Y"),
    }

    return client_id, config_text, user_data


def apply_peer(client_id: str, user: dict):
    log(f"Применение пира ID: {client_id}")
    if not _is_linux():
        log("Пропуск применения пира: не Linux среда")
        return
    pub = user.get("public_key")
    psk = user.get("preshared_key")
    ip = user.get("ip")
    if not (pub and psk and ip):
        raise ValueError("Неполные данные пира для применения")
    # write PSK to temp file to avoid process substitution
    tmp = tempfile.NamedTemporaryFile("w", delete=False)
    try:
        tmp.write(psk + "\n")
        tmp.flush()
        tmp.close()
        command = f"wg set {WG_INTERFACE} peer {pub} preshared-key {tmp.name} allowed-ips {ip}/32"
        _run_command(command)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
    log(f"Пир {client_id} применён")


def remove_peer(client_id: str):
    log(f"Удаление пира ID: {client_id}")
    if not _is_linux():
        log("Пропуск удаления пира: не Linux среда")
        return
    peers_db = JsonDB(str(PEERS_PATH))
    archive_db = JsonDB(str(ARCHIVE_PATH))
    peer = peers_db.get(client_id) or archive_db.get(client_id)
    if not peer:
        log(f"Пир {client_id} не найден в базах")
        return
    pub = peer.get("public_key")
    if not pub:
        log(f"У пира {client_id} отсутствует public_key")
        return
    command = f"wg set {WG_INTERFACE} peer {pub} remove"
    _run_command(command)
    log(f"Пир {client_id} удалён")
