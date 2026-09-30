# Electronic Hopper

Guacamole project for a coaxial electric hopper: approximately 5 m hover for
300 seconds followed by controlled landing, with hardware cost below 500
(provisionally AUD). The scope is propulsion selection, FreeCAD design and PID
integration into the supplied 6DOF simulation. See [the brief](context/brief.md)
for requirements, open questions and the initial simulator findings.

Run from the repository root:

```bash
uv run examples/ehopper/ehopper.py
```

This installs the host/document readers and the supplied local FreeCAD MCP.
An alternative using the existing repository environment is:

```bash
uv sync --extra sounding-rocket
uv sync --project examples/ehopper/freecad-mcp --locked --no-dev
.venv/bin/python -m examples.ehopper.ehopper
```

The shared `sounding-rocket` extra supplies document readers; the hopper brief
defines the engineering scope. Codex CLI must already be installed and logged in.
The hopper provider enables live web search for current component prices,
dimensions and specifications. It researches manufacturer/supplier pages and
records source URLs, access dates, currencies and units in its sourcing notes.
Restart the launcher to apply this setting to an already-running saved project.
Backend dependencies stay separate. The provided 6DOF source is incomplete;
installing its dependencies does not repair or validate its dynamics.

The numerical environment and pinned PyThrust submodule are set up separately:

```bash
git -C examples/ehopper/tooling/6dof_hopper submodule update --init PyThrust
uv venv examples/ehopper/tooling/6dof_hopper/.venv --python 3.13
uv sync --project examples/ehopper/tooling/6dof_hopper --locked
uv pip install --python examples/ehopper/tooling/6dof_hopper/.venv/bin/python -e examples/ehopper/tooling/6dof_hopper/PyThrust
PYTHONDONTWRITEBYTECODE=1 examples/ehopper/tooling/6dof_hopper/.venv/bin/python examples/ehopper/tooling/6dof_hopper/test/test_pythrust.py
```

These commands install the dependencies used by the current code. The supplied
propulsion demo exercises an isolated rotor; it does not validate a coaxial pair
or meet the hopper's endurance/budget requirements. The source simulator still
needs the repairs recorded in the brief.

FreeCAD must be installed. `freecad_run` calls the supplied MCP over stdio and
defaults to its `execute_code_headless` tool, which detects `freecadcmd`,
`FreeCADCmd`, Snap's `freecad.cmd`, or the FreeCAD Flatpak. It runs saved Python
scripts from the output directory and returns declared exports and a response
log. GUI mode also requires the
[FreeCAD MCP addon](freecad-mcp/docs/installation.md) running on localhost:9875;
`freecad_status` checks that addon. Set `FREECAD_MCP_TOKEN` in the environment
when the addon requires authentication. No token belongs in the brief or files.

Edit configuration in `ehopper.py`; there are no command-line arguments.
The project inventories `context/`, both `tooling/` repositories and
`freecad-mcp/` including its setup/execution documentation. Outputs go to
`results/`, history to `.guacamole/`. Rerunning resumes a single saved run.
Human control uses `ws://127.0.0.1:8766`, with the authorization token printed
at startup; root README documents inbox, reply, correction and review commands.
Port 8766 keeps this project separate from Kookaburra's default port.

Run the setup regression checks without model calls:

```bash
.venv/bin/python -m unittest discover -s tests -p test_ehopper.py -v
```

To also exercise the real supplied FreeCAD MCP and validate/export a test solid:

```bash
EHOPPER_FREECAD_SMOKE=1 .venv/bin/python -m unittest discover -s tests -p test_ehopper.py -v
```

The test solid validates the CAD connection and export path; it is not a vehicle
design. Selecting hardware, designing the hopper and demonstrating mission
performance remain engineering work for the configured project.
