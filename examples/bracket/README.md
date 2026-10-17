# Wall-bracket benchmark

Milestone B's end-to-end check, on one constrained product family: a natural-language
brief in, a ready PDR review package out. The package holds native FreeCAD CAD, STEP,
the part's PMI, an ISO part drawing and a CAD-derived BOM, each checked and traced to
requirements. Nobody edits CAD or assembles documents by hand.

The family is an L-shaped plate with a row of holes in each leg, fixed to the wall
through the upright with hex screws and washers. Agents choose the design; two tools
do the deterministic work:

- `bracket_generate(design, name)` builds a parametric FreeCAD model in
  [freecad_bracket.py](freecad_bracket.py). Every dimension is an expression on a
  `Parameters` sheet. The tool exports a BOM derived from the assembly tree and the
  bracket's PMI (`-pmi.json`). From the PMI it compiles an A3 part drawing, an
  editable DXF with an SVG for review, and a STEP AP242 file carrying the PMI on the
  bracket's faces. A layout the model cannot hold, or a drawing or STEP that cannot
  be made, comes back as `problems`, not files.
- `bracket_check(native_artifact, step_artifact, bom_artifact, pmi_artifact,
  drawing_artifact, load_n)` reopens the published files. It checks recompute, solid
  validity, recompute after a +1 mm thickness change, STEP solid count and volumes,
  interference, and the BOM against the model. It checks the PMI and the drawing
  (below). It then evaluates every requirement constraint it can measure (`mass`,
  `width`, `depth`, `height`, `deflection`, `max_stress`, `safety_factor`,
  `screw_tension`). Structural values are a PDR hand calculation from the model's
  own parameters. Constraints it cannot measure stay "not performed", so they can
  never pass silently.

## Drawing and PMI

The drawing follows the ISO GPS subset in [drafting.py](../../src/guacamole/integrations/drafting.py): third-angle
views of the bracket part, datums A (wall face), B (underside) and C (side face), and
ISO 129-1 dimensions taken from the model's geometry. It has an ISO 5457 A3 sheet, an
ISO 7200 title block and an ISO 5455 scale; it is also written as a vector PDF. The
family's drafting rules in [bracket.py](bracket.py) supply every tolerance, and the
drawing invents none:

- Holes are ISO 273 medium clearance holes, class H13.
- Hole positions are ⌀(H − F) at maximum material (Ⓜ): the floating-fastener rule.
- Everything else falls under ISO 22081: ±0.5 on sizes, a 1 mm surface profile to A B C.

A designer agent may propose other GD&T through `bracket_generate`'s `tolerancing`
argument. It can choose another H class, a tighter position, a mounting-face flatness
or other general values. The proposal is checked rather than trusted:

- a position above H − F would let the screws jam, so `bracket_generate` returns that
  as a problem;
- `bracket_check` verifies the rule again from the published PMI and BOM.

The PMI is the source of meaning. The DXF is compiled from it and the SVG is rendered
from the DXF. [ap242.py](../../src/guacamole/integrations/ap242.py) writes the STEP from it through OCCT: datums,
hole sizes and frames, each attached to the faces the PMI names. Each carries graphical
PMI too, so STEP viewers show the annotations upright beside their features. The ISO 22081
general surface profile goes on every face no other surface profile covers, as the
CAx-IF PMI practice 4.1 (section 6.3) gives it. The general ±0.5 size tolerance has
no AP242 semantic entity; it stays in the PMI and on the drawing. `bracket_check`
reports these as separate checks:

- whether the PMI is well formed (no malformed datum reference or unsupported
  tolerance);
- whether each of its named features still maps to exactly one, unchanged, face or
  hole set of the reopened model;
- whether an independent read of the published STEP returns exactly the PMI: every
  datum, hole size, value, zone, modifier and datum order, and the general surface
  profile, on the same faces;
- what reading the DXF back finds: audit, units and scale, title block, every frame,
  datum and hole size of the PMI, everything inside the frame, and lettering height.

The STEP reader in `ap242.py` puts every dimension and tolerance a file holds in
exactly one place: mapped to the typed PMI, listed as unmapped with the reason, or
counted as a presentation-only annotation. The typed PMI covers:

- planes, holes, shafts, widths and sets of surfaces;
- datums on them, and datum targets: points, lines, circles and rectangles;
- diameters, widths and radii;
- linear locations;
- all fifteen ISO 1101 characteristics, with their modifiers, projected zones and
  datum material requirements.

The reader confirms each tolerance value against the file's own text, because OCCT
reads some third-party encodings as 0. It also confirms each nominal against the
geometry, because OCCT returns values in NIST's inch files unscaled. On NIST's
AP242 PMI test models it maps 138 sizes and locations and 172 frames. It lists 269
constructs outside the typed subset with reasons, counts 240 presentation-only
annotations, and loses none. Set `GUACAMOLE_NIST_PMI` to the unzipped
[NIST PMI STEP files](https://www.nist.gov/document/nist-pmi-step-files) to run that
check in `tests/test_ap242.py`. The test also compares CTC 4 against NIST's drawing
of it.

OCCT 7.9 has defects that `ap242.py` works around, and its round-trip check would
catch them if they change:

- Its writer stores an ISO 286 grade two above the one given, so H13 would read back
  as H15.
- Its writer drops projected zones, all around and all over. Its reader maps them,
  and `write()` lists what it could not carry.
- Its reader drops the sign of a lower deviation above nominal.

[mbd.py](../../src/guacamole/integrations/mbd.py) is a second, experimental AP242 writer. It uses the
[FreeCAD MBD Workbench](https://github.com/ChipsWoodShop/FreeCAD-MBDWorkbench), an
LGPL-2.1 preview that follows ASME Y14.5. It puts the PMI on the model's faces as the
Workbench's own datum, datum system, dimension and frame objects, saves that FreeCAD
model, and exports with the Workbench. `ap242.read` then checks the file. The
Workbench cannot hold the following, and the result lists each one:

- ISO 286 classes such as H13;
- coaxiality, concentricity and symmetry;
- datum material requirements;
- widths, surface sets and locations;
- the ISO 22081 general specification.

It also puts each frame on one face, so a pattern becomes one frame per hole. On this
bracket, the datums and the four position frames come through. One problem remains:
FreeCAD 1.1's OCCT 7.8.0 attaches no face to a datum on a plane bounded by one loop,
here datum C on the side face, and the read-back flags it. OCCT 7.9 attaches all
twelve faces.

The Workbench's exporter needs pythonocc-core inside FreeCAD. With the snap FreeCAD,
a conda environment with `pythonocc-core=7.8.1` works. Point `MBD_PYTHONOCC` at its
site-packages and `MBD_WORKBENCH` at the Workbench if they are not where
`guacamole.integrations.mbd` looks by default. `tests/test_mbd.py` runs only when both
are there.

The review's `review.md` is the package document. It includes the requirement
traceability table with measured values, decisions, deliverables with the drawing
and BOM inline, every check and measurement, and open items.

## Running

Needs FreeCAD (`freecadcmd`, or the snap's `freecad.cmd`) and the Claude Code CLI,
logged in:

```bash
uv sync --extra langchain --extra graphiti --extra mem0
.venv/bin/python -m examples.bracket.bracket
```

Each brief in [briefs/](briefs) runs as a fresh project under `runs/<timestamp>/`.
Every question, blocking or not, gets one scripted reply as it is asked, telling the
agents to proceed on recorded assumptions. The final review is left to a human: each
brief holds at its ready PDR review until it is accepted or changes are requested.
Edit and run `examples/bracket/review.py` with the token the brief printed. Control is
on `ws://127.0.0.1:8767`. A brief passes when its run reaches a ready PDR review. A provider failure such as a
usage limit pauses the brief and stops the benchmark there, so later briefs are not
burned in seconds. Once the cause is fixed, resume with
`.venv/bin/python -m examples.bracket.bracket runs/<timestamp>`: briefs that finished
are kept, and the paused one continues its saved run. `runs/<timestamp>/benchmark.json` records status,
estimated input tokens and time for each brief. `BUDGET.max_run_input_tokens` caps
each run (17M by default). Snap and Flatpak FreeCAD builds can read `$HOME` but not
`/tmp`, so keep `RUNS` under your home directory.

`tests/test_bracket.py` exercises the tools, the checks and the report with real
FreeCAD where FreeCAD and the `bracket` extra are installed, and the pass/fail logic
and the benchmark loop everywhere. `tests/test_drafting.py` covers the PMI checks
without FreeCAD, and drawing and read-back where ezdxf is installed.
`tests/test_ap242.py` round-trips a declared matrix through AP242 with OCP. The
matrix holds every carried characteristic, both zones and both material modifiers,
a zero tolerance at maximum material, a class and a deviation size, and datum
systems of one to three datums.
