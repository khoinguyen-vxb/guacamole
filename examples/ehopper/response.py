import json
from getpass import getpass

from websockets.sync.client import connect

# The token changes on every EHopper start; paste the one it printed.
token = getpass("Current EHopper authorization token: ").strip()
token = token.removeprefix("Authorization:").strip().removeprefix("Bearer").strip()
request_id = "789f30845252467798618636530c4a4d"
reply = f"""
Referring to: {request_id}

Diagnostics for verify_command request b7d6f20b863f491c9545257a292c241a: execution
completed (exit 0). Validation failed while validating the checker's stdout as a
VerificationResult, in the model's consistency validator, not in parsing or the envelope:
"Value error, Passed verification requires observed passing checks".

Contract: outcome "passed" requires a non-empty checks map in which every value is true.
A null check counts as not passed. Your result had 83 true checks and 4 explicitly
unperformed null checks with outcome "passed", so it was rejected. This rule was not stated
in the tool description; that was a runtime gap, not a checker defect.

Remedy: rerun the state/frame/mass checker through verify_command reporting outcome
"inconclusive" while it keeps the four null checks (as your propulsion/interface checker
already does), or omit checks the program does not perform and report "passed". After the
next runtime restart, verify_command returns schema mismatches as an inconclusive result
with the validation message, and its description states this rule.

Separately, when recording evidence, copy the verification result's outcome and explanation
exactly; put any commentary in the rationale. Pass this to the plant worker; no other change
to its plan is needed.
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
