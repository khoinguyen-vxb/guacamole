import json
import uuid
from getpass import getpass
from websockets.sync.client import connect

token = "JOPYBuekVoAQVi3il3XVW9IA8tLyVK-b3q3u8TUp9OQ"
reply = """
I'm the approver, but also go onto the internet and read the all the technical documentation. There should be extensive examples within the provided documentation for you to design around. The drawings and report figures are also all in the report.
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

message = {
    "id": uuid.uuid4().hex,
    "command": {
        "kind": "reply_human",
        "request_id": "eadd606fff0a4ae79b7bc0e7274ef4c8",
        "author": "Khoi",
        "text": reply,
    },
}

with connect(
    "ws://127.0.0.1:8765",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
) as ws:
    ws.send(json.dumps(message))
    print(ws.recv())