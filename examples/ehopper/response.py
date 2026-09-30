import json
import uuid
from getpass import getpass
from websockets.sync.client import connect

token = "HDZT1b6Qu8bTfpGPAMMPz-Bb_n4scYzgygb-hixzuh4"
reply = """
Try that again thnx and add ':)' if it works
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

message = {
    "id": uuid.uuid4().hex,
    "command": {
        "kind": "reply_human",
        "request_id": "342ff76978da453497afb32a5a6261ff",
        "author": "Khoi",
        "text": reply,
    },
}

with connect(
    "ws://127.0.0.1:8766",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
) as ws:
    ws.send(json.dumps(message))
    print(ws.recv())