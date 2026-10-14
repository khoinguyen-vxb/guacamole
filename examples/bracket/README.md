# Wall-bracket benchmark

Milestone B's end-to-end check, on one constrained product family: a natural-language
brief in, a ready PDR review package out. The package holds native FreeCAD CAD, STEP,
a drawing and a CAD-derived BOM, each checked and traced to requirements. Nobody
edits CAD or assembles documents by hand.

The family is an L-shaped plate with a row of holes in each leg, fixed to the wall
through the upright with hex screws and washers. Agents choose the design; two tools
do the deterministic work:

- `bracket_generate(design, name)` builds a parametric FreeCAD model in
  [freecad_bracket.py](freecad_bracket.py). Every dimension is an expression on a
  `Parameters` sheet. The tool exports STEP, an A3 third-angle drawing and a BOM
  derived from the assembly tree. A layout the model cannot hold comes back as
  `problems`, not files.
- `bracket_check(native_artifact, step_artifact, bom_artifact, load_n)` reopens the
  published files. It checks recompute, solid validity, recompute after a +1 mm
  thickness change, STEP solid count and volumes, interference, and the BOM against
  the model. It then evaluates every requirement constraint it can measure (`mass`,
  `width`, `depth`, `height`, `deflection`, `max_stress`, `safety_factor`,
  `screw_tension`). Structural values are a PDR hand calculation from the model's
  own parameters. Constraints it cannot measure stay "not performed", so they can
  never pass silently.

The review's `review.md` is the package document. It includes the requirement
traceability table with measured values, decisions, deliverables with the drawing
and BOM inline, every check and measurement, and open items.

## Running

Needs FreeCAD (`freecadcmd`, or the snap's `freecad.cmd`) and the Codex CLI, logged in:

```bash
uv sync
.venv/bin/python -m examples.bracket.bracket
```

Each brief in [briefs/](briefs) runs as a fresh project under `runs/<timestamp>/`.
A blocking question gets one scripted reply asking the agents to proceed on recorded
assumptions; the final review is left to a human. A brief passes when its run
reaches a ready PDR review. `runs/<timestamp>/benchmark.json` records status,
estimated input tokens and time for each brief. `BUDGET.max_run_input_tokens` caps
each run (6M by default). Snap and Flatpak FreeCAD builds can read `$HOME` but not
`/tmp`, so keep `RUNS` under your home directory.

`tests/test_bracket.py` exercises the tools, the checks and the report with real
FreeCAD where it is installed, and the pass/fail logic and the benchmark loop
everywhere.
