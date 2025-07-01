# wireguard_bot/utils/disabler.py
from datetime import datetime
from wireguard_bot.utils.json_db import load_json, save_json
from wireguard_bot.utils.wg_utils import remove_peer

def disable_expired_peers():
    peers_data = load_json("config/peers.json")
    peers = peers_data.get("peers", [])

    archive_data = load_json("config/archive.json")
    archive = archive_data.get("archive", [])

    now = datetime.now()
    updated_peers = []
    moved_to_archive = []

    for peer in peers:
        expiry_str = peer.get("date")
        if not expiry_str:
            updated_peers.append(peer)
            continue

        try:
            expiry_date = datetime.strptime(expiry_str, "%d.%m.%y")
        except ValueError:
            updated_peers.append(peer)
            continue

        if expiry_date < now:
            remove_peer(peer["id"])
            moved_to_archive.append(peer)
        else:
            updated_peers.append(peer)

    if moved_to_archive:
        save_json("config/peers.json", {"peers": updated_peers})
        save_json("config/archive.json", {"archive": archive + moved_to_archive})
