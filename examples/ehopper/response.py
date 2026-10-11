import json
from getpass import getpass
from websockets.sync.client import connect

token =  "mXGn4I9S97q2oExoiRv6s7wqwHe0akzo6NkKz9AI9t0"
reply = """
Referring to: 2984ecb56af841d08c95f59239783ff1
yeah sounds good to me bossman
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

message = {
    "id": "reply-2984ecb56af841d08c95f59239783ff1",
    "command": {
        "kind": "reply_human",
        "request_id": "2984ecb56af841d08c95f59239783ff1",
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
