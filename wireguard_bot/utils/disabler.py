# utils/disabler.py
from datetime import datetime
from pathlib import Path
from utils.json_db import JsonDB
from utils.wg_utils import remove_peer

CONFIG_DIR = Path(__file__).parent.parent / "config"

def disable_expired_peers():
    peers_db = JsonDB(str(CONFIG_DIR / "peers.json"))
    archive_db = JsonDB(str(CONFIG_DIR / "archive.json"))

    now = datetime.now()
    to_archive = []

    for uid, peer in list(peers_db.get_all().items()):
        expiry_str = peer.get("deactivate_date") or peer.get("date")
        if not expiry_str:
            continue
        try:
            expiry_date = datetime.strptime(expiry_str, "%d.%m.%Y")
        except ValueError:
            try:
                expiry_date = datetime.strptime(expiry_str, "%d.%m.%y")
            except ValueError:
                continue
        if expiry_date < now:
            remove_peer(uid)
            # move to archive
            peers_db.pop(uid)
            archive_db.set(uid, peer)
            to_archive.append(uid)
