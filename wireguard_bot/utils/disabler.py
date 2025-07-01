# wireguard_bot/utils/disabler.py
from datetime import datetime
from wireguard_bot.utils.json_db import load_peers, load_archive, save_peers, save_archive
from wireguard_bot.utils.wg_utils import remove_peer

def disable_expired_peers():
    peers = load_peers()
    archive = load_archive()
    now = datetime.now()
    updated_peers = {}

    for peer_id, peer in peers.items():
        expires = datetime.strptime(peer["expires"], "%d.%m.%y")
        if expires < now:
            remove_peer(peer_id)
            archive[peer_id] = peer
        else:
            updated_peers[peer_id] = peer

    save_peers(updated_peers)
    save_archive(archive)
