"""Send a human correction to the running enclosure host.

Run with: .venv/bin/python -m examples.enclosure.interject
It asks for the token the host printed. Edit text (and keep_workers) first.
"""

import hashlib

from guacamole.websocket import control

from .enclosure import CONTROL_PORT

# True: a priority note; the plan and running workers continue.
# False: a correction; the Chief replans from scratch and every worker is stopped.
keep_workers = True
text = """
To the pcb_fan_power worker (and any agent doing KiCad work):

KiCad 10 and its standard libraries exist only inside the Konnect container that
the kicad_* tools run in. A read-only copy of the libraries is now a project
input at examples/enclosure/kicad-libs: symbols/, footprints/, sym-lib-table and
fp-lib-table. Read definitions from there with list_files and read_text.

- Write the .kicad_pro, .kicad_sch and .kicad_pcb files with write_text or a
  script through execute, referencing parts by standard library names (Device:R,
  Connector_BarrelJack:BarrelJack_Horizontal) and embedding the symbol and
  footprint definitions you copied, so the container's KiCad resolves them.
- Check only with kicad_erc and kicad_drc; export only with
  kicad_export_schematic_pdf and kicad_export_manufacturing.
- Do not run podman, docker or KiCad through execute, and do not search the
  filesystem outside the project, its outputs and its inputs (no container
  storage, no Trash, no home-directory scans). Anything you found that way is
  not an acceptable source; use the kicad-libs copy instead.
"""

with control(CONTROL_PORT, "Enclosure") as send:
    send(
        {
            "kind": "interject",
            "author": "Jack",
            "text": text,
            "keep_workers": keep_workers,
        },
        # The ID follows the text: rerunning the same message returns the stored
        # result instead of interjecting twice, and an edited message is sent.
        id="interject-" + hashlib.sha256(text.encode()).hexdigest()[:12],
    )
