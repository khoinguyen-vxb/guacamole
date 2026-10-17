import uuid

from guacamole.websocket import control

reply = """
I'm the approver, but also go onto the internet and read the all the technical documentation. There should be extensive examples within the provided documentation for you to design around. The drawings and report figures are also all in the report.
"""

if "[" in reply:
    raise SystemExit("Fill in or remove the bracketed placeholders before sending.")

with control(8765, "Kookaburra") as send:
    send(
        {
            "kind": "reply_human",
            "request_id": "eadd606fff0a4ae79b7bc0e7274ef4c8",
            "author": "Khoi",
            "text": reply,
        },
        id=uuid.uuid4().hex,
    )
