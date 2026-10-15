"""Stop hook shared by Claude Code (.claude/settings.json) and Codex (.codex/hooks.json).

Runs CI's fast checks and sends the agent back once if any fail. The unit tests
take over a minute, so they stay in CI.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".venv" / "bin"
CHECKS = (
    ("ruff", "check", "--output-format", "concise", "src", "tests"),
    ("ruff", "format", "--check", "src", "tests"),
    ("ty", "check", "--output-format", "concise"),
)

event = json.load(sys.stdin)
failures = []
# stop_hook_active: this turn was already sent back once, so let it end.
if not event.get("stop_hook_active"):
    for tool, *args in CHECKS:
        if not (BIN / tool).exists():
            continue
        run = subprocess.run(
            [BIN / tool, *args], cwd=ROOT, capture_output=True, text=True, check=False
        )
        if run.returncode:
            output = (run.stdout + run.stderr).strip()[:3000]
            failures.append(f"$ .venv/bin/{tool} {' '.join(args)}\n{output}")
# Codex expects JSON on stdout when a Stop hook exits 0.
print(
    json.dumps(
        {
            "decision": "block",
            "reason": "CI checks fail; fix them before finishing "
            "(`.venv/bin/ruff format src tests` fixes formatting). If you did not "
            "cause a failure, report it instead of fixing it.\n\n"
            + "\n\n".join(failures),
        }
        if failures
        else {}
    )
)
