import json
import uuid
from getpass import getpass
from websockets.sync.client import connect

token = getpass("Current EHopper authorization token: ")
text = input("Reply to the pending EHopper question: ").strip()
if not text:
    raise SystemExit("No reply entered.")
command = {
    "id": f"interject-{uuid.uuid4().hex}",
    "command": {
        "kind": "interject",
        "run_id": "0d3952dea3fd4803a63b63a01d64464c",
        "author": "Khoi",
        "text": text,
    },
}
with connect(
    "ws://127.0.0.1:8766",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
    # EHopper serves this socket on its busy run loop; allow a slow handshake.
    open_timeout=120,
) as ws:
    ws.send(json.dumps(command))
    print(ws.recv())
