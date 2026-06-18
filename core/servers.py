"""Add the server to a game directory's servers.dat (in-game server list).

servers.dat is uncompressed NBT:
  root compound -> "servers": TAG_List of TAG_Compound,
  each with "name" (string) and "ip" (string).

We merge into any existing file so we never wipe a player's other servers, and
dedupe by ip so re-running doesn't add duplicates.
"""

import os

from . import nbt


def ensure_server(game_dir, name, ip, log=None):
    """Ensure a server entry (name, ip) exists in <game_dir>/servers.dat."""
    log = log or (lambda *_: None)
    path = os.path.join(game_dir, "servers.dat")

    servers_list = []  # list of compound dicts (each: {field: (type, value)})

    if os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                _root_name, (root_type, root_val) = nbt.parse(f.read())
            if root_type == nbt.TAG_COMPOUND and "servers" in root_val:
                _elem_type, items = root_val["servers"][1]
                servers_list = list(items)
        except (OSError, ValueError) as e:
            log(f"  could not read existing servers.dat ({e}); recreating")
            servers_list = []

    # Dedup by ip.
    for entry in servers_list:
        existing_ip = entry.get("ip", (nbt.TAG_STRING, ""))[1]
        if existing_ip == ip:
            log(f"  server '{ip}' already in list")
            return False

    servers_list.append({
        "name": (nbt.TAG_STRING, name),
        "ip": (nbt.TAG_STRING, ip),
    })

    root_value = {
        "servers": (nbt.TAG_LIST, (nbt.TAG_COMPOUND, servers_list)),
    }
    data = nbt.write("", nbt.TAG_COMPOUND, root_value)

    os.makedirs(game_dir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    log(f"  added server '{name}' ({ip}) to the in-game server list")
    return True
