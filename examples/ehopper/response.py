import json
from getpass import getpass
from websockets.sync.client import connect

token = getpass("Current EHopper authorization token: ")
reply = """
Please only do the exposed central structure. Add minimum required structural parts, there is no requirement to 
make it actually look like a rocket. The fins and nosecone will add negliglbe aerodynamic benefits at our low speed
and will just contribute a lot of costs and weight so do not include it.
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

message = {
    "id": "reply-8592018ac9fa4a6998a15bd34ad8399b",
    "command": {
        "kind": "reply_human",
        "request_id": "8592018ac9fa4a6998a15bd34ad8399b",
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
