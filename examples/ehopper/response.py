import json
from getpass import getpass
from websockets.sync.client import connect

token =  "CxChOMcZhVxmyCTSXrNRTop6A9ZXr_-lupaFsHPjy9E"
reply = """
Referring to: 81d9c978978c45fb9e9d5717dfe72506
yeah sounds good to me bossman
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

message = {
    "id": "reply-81d9c978978c45fb9e9d5717dfe72506",
    "command": {
        "kind": "reply_human",
        "request_id": "81d9c978978c45fb9e9d5717dfe72506",
        "author": "Khoi",
        "text": reply,
    },
}

print("Connecting to EHopper on 127.0.0.1:8766...", flush=True)
with connect(
    "ws://127.0.0.1:8766",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
    # EHopper serves this socket on its busy run loop; allow a slow handshake.
    open_timeout=120,
) as ws:
    print("Connected; sending reply...", flush=True)
    ws.send(json.dumps(message))
    print("Reply sent; waiting up to 120 seconds for acknowledgement...", flush=True)
    try:
        print(ws.recv(timeout=120), flush=True)
    except TimeoutError:
        raise SystemExit(
            "No acknowledgement received. Check the EHopper event log; rerunning "
            "this script is safe because it reuses the same command ID."
        ) from None
