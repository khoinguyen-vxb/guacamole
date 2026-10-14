import json
from getpass import getpass

from websockets.sync.client import connect

# The token changes on every EHopper start; paste the one it printed.
token = getpass("Current EHopper authorization token: ").strip()
token = token.removeprefix("Authorization:").strip().removeprefix("Bearer").strip()
request_id = "bf616ffea8fc4979a73c5ee1cbabf8d5"
reply = f"""
Referring to: {request_id}

Choice: expose the supported reconciliation action. Both records are preserved.

Cause: a runtime gap. Retry must repeat the original arguments, so a corrected call is a
new request, and nothing could settle the failed original; finish stayed rejected.
Fixed and restarted: a new "supersede" action takes request_id (the failed request), by
(a later completed request with the same requester, tool and parent) and reason. It
cancels the failed request with reason "Superseded by <by>: <reason>" and records
request.superseded. The failed revision and its result stay in history; neither outcome
becomes a pass, and the four unperformed checks stay unperformed.

Only the requester can supersede. The plant worker should send:
supersede request_id b7d6f20b863f491c9545257a292c241a, by 21ca2850ef224d3bbb276822db3dd2ff,
then finish. Do not retry b7d6f20b or rerun 21ca2850. Pass this on to the worker.
"""

message = {
    "id": f"reply-{request_id}",
    "command": {
        "kind": "reply_human",
        "request_id": request_id,
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
