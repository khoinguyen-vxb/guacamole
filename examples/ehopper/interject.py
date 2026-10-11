import json
from getpass import getpass
from websockets.sync.client import connect

token = getpass("Current EHopper authorization token: ").strip()
# Accept the whole "Authorization: Bearer <token>" line EHopper prints at startup.
token = token.removeprefix("Authorization:").strip().removeprefix("Bearer").strip()
text = """
Structural correction (hard constraint): replace the single central spine with a tripod or
quadpod structure built from CFRP (carbon-fibre) tube spines. Compare the tripod and quadpod
options and recommend one with justification.

This supersedes the single aluminium tube spine in structural decision
01797f347ac344f984e1912cc5247b28 and the aluminium/PETG-only structural study. Research and
price CFRP tubes within the existing AUD 500 vehicle budget.

Budget amendment: printed PETG parts no longer need to be costed. Exclude PETG filament from
the AUD 500 vehicle budget; all other purchased hardware and materials still count.

Keep the bottom-mounted propulsion (REQ-PROPULSION-PLACEMENT) and the common two-axis gimbal.
If the tripod/quadpod layout conflicts with the gimbal, ask me before changing the actuation
concept.
"""

command = {
    # Fixed ID: rerunning returns the stored result instead of interjecting twice.
    "id": "interject-cfrp-pod-01",
    "command": {
        "kind": "interject",
        "run_id": "0d3952dea3fd4803a63b63a01d64464c",
        "author": "Khoi",
        "text": text,
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
            "this script is safe because it reuses the same command ID."
        ) from None
