import hashlib
import json
from getpass import getpass

from websockets.sync.client import connect

token = getpass("Current EHopper authorization token: ").strip()
# Accept the whole "Authorization: Bearer <token>" line EHopper prints at startup.
token = token.removeprefix("Authorization:").strip().removeprefix("Bearer").strip()
# True: a priority note for the Chief; the plan and running workers continue.
# False: a correction; the Chief replans from scratch and every worker is stopped.
keep_workers = True
text = """
Priority: move to candidate CAD now. Model the braced CFRP tripod and quadpod landing legs
directly in the FreeCAD candidates (intermediate stance with 279.4 mm propellers and wide
stance with 330.2 mm propellers, as in your structural_trade_review_checkpoint_01 handoff)
instead of completing a separate analytic braced-leg study first. Use the CAD mass, CG and
clearance results for the structural down-selection.

This is a priority note, not a requirement change: keep the current plan, decisions and the
plant worker running.
"""

command = {
    # The ID follows the text: rerunning the same message returns the stored result
    # instead of interjecting twice, and an edited message is always sent.
    "id": "interject-" + hashlib.sha256(text.encode()).hexdigest()[:12],
    "command": {
        "kind": "interject",
        "run_id": "0d3952dea3fd4803a63b63a01d64464c",
        "author": "Khoi",
        "text": text,
        "keep_workers": keep_workers,
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
    ws.send(json.dumps(command))
    print("Interjection sent; waiting up to 120 seconds for acknowledgement...", flush=True)
    try:
        print(ws.recv(timeout=120), flush=True)
    except TimeoutError:
        raise SystemExit(
            "No acknowledgement received. Check the EHopper event log; rerunning "
            "this script is safe because the same text reuses the same command ID."
        ) from None
