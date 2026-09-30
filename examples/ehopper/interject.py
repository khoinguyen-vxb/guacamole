import json
import uuid
from getpass import getpass
from websockets.sync.client import connect

token = getpass("Current EHopper control token: ")
text = (
    "Recovery: pytest 9.1.1 is installed in the 6dof_hopper interpreter, and "
    "the README setup now syncs its locked environment. Stop retrying stale "
    "Read refs: copy the exact current Ref object from the latest context and "
    "reissue the read without reconstructing or reusing older refs. Refresh the "
    "file listing once if needed; if still unavailable, report the missing path "
    "and continue the supplier research and preliminary CAD/audit with valid refs."
)
command = {
    "id": f"interject-{uuid.uuid4().hex}",
    "command": {"kind": "interject", "author": "Khoi", "text": text},
}
with connect(
    "ws://127.0.0.1:8766",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
) as ws:
    ws.send(json.dumps(command))
    print(ws.recv())
