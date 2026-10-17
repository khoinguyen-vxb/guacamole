"""Headless FreeCAD job scripts: deterministic, no MCP server involved.

run_job runs a FreeCAD-side script on one JSON job in headless FreeCAD (FREECAD).
"""

import asyncio
import json
import os
import shutil
import signal
from contextlib import suppress
from pathlib import Path

# Headless FreeCAD; the snap names it freecad.cmd.
FREECAD = next(
    (p for n in ("freecadcmd", "FreeCADCmd", "freecad.cmd") if (p := shutil.which(n))),
    None,
)


async def run_job(
    job: dict[str, object], directory: Path, script: Path, timeout_s: float = 300
) -> dict:
    """Run a FreeCAD-side script on one job in its own headless process group.

    The script reads the job file named in GUACAMOLE_JOB and writes the job's result
    file. A timeout or a cancelled call kills that group, not just the wait for it.
    Snap and Flatpak FreeCAD builds see $HOME but not /tmp: keep directory there.
    """
    if FREECAD is None:
        raise RuntimeError("FreeCAD is not installed: no freecadcmd on PATH")
    path, result = directory / "job.json", directory / "result.json"
    result.unlink(missing_ok=True)
    path.write_text(json.dumps({**job, "result": str(result)}), encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        FREECAD,
        "-c",
        f"exec(open({str(script)!r}, encoding='utf-8').read())",
        # Offscreen Qt lets scripts import GUI-backed addons without a display.
        env={**os.environ, "GUACAMOLE_JOB": str(path), "QT_QPA_PLATFORM": "offscreen"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout_s)
    except (TimeoutError, asyncio.CancelledError) as exc:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        # Not TimeoutError: the runtime would read that as its own turn timing out.
        raise RuntimeError(f"FreeCAD took over {timeout_s:g} s") from None
    if process.returncode or not result.exists():
        tail = "\n".join(output.decode(errors="replace").splitlines()[-15:])
        raise RuntimeError(f"FreeCAD exited {process.returncode}:\n{tail}")
    return json.loads(result.read_text(encoding="utf-8"))
