# Guacamole — Engineering Standards, GD&T, and Compliance Integration

**Final architecture and implementation brief**  
**Date:** 15 October 2026  
**Status:** Proposed architecture and implementation plan; standards applicability and safety-critical checks require qualified review.  
**Revised:** 15 October 2026 — SysML v2 is the only requirements authority; StrictDoc moved from P0 to an optional downstream documentation adapter (§2 "Requirements authority", §3).

## 1. Executive decision

Build a **Standards & Compliance Engine** as a deterministic, versioned service in Guacamole, integrated with the authoritative SysML v2 project model and the existing agent/solver orchestration. Separately, build a **semantic PMI / model-based definition (MBD)** representation that generates ISO/ASME-family drawings and STEP AP242 deliverables from engineering design intent.

Agents may propose a standards profile, applicable clauses, datum schemes, tolerances and compliance evidence. They must **not** be the authority that declares safety-critical code compliance. Deterministic checks and formally recorded human decisions determine release eligibility.

**First two demonstrators:**

- **ISO GPS mechanical drawing:** Professional, editable manufacturing drawings with semantic datum systems, GD&T, clear revision/title-block practices and STEP AP242 round-trip tests.
- **Australian pressure vessel:** Given equipment and jurisdiction context, identify candidate AS/NZS 1200 / AS 1210 / AS 4343 obligations, missing inputs, relevant fabrication/inspection requirements and the NSW regulatory workflow; generate a clause-linked compliance matrix but do not claim approved design without the required engineering checks and approvals.

## 2. Architecture

```text
Human-defined project context and authoritative SysML v2 baseline
                          │
                          ▼
           Standards Applicability Resolver
       ┌──────────────────┼──────────────────┐
       │                  │                  │
 Jurisdiction and    Versioned Standards   Client/company
 regulatory rules    Registry + licence    project rules
       └──────────────────┼──────────────────┘
                          ▼
                 Standards Profile
            (edition, amendments, status)
                          ▼
                 Requirement Compiler
        (human-approved typed compliance rules)
                          ▼
       Engineering agents and solver adapters
             ├── CAD / semantic PMI
             ├── structural / thermal / fluid analyses
             └── manufacturing / inspection documentation
                          ▼
                   Compliance Engine
       (rule evaluation + evidence + human review)
                          ▼
                    Release Gate
       ├── release permitted for supported scope
       ├── blocked by failure or missing critical evidence
       └── engineering approval required
```

### Explicit authority boundaries

1. **SysML v2 project baseline:** authoritative project requirements, interfaces, component identities, functional relationships, approved design decisions.
2. **Standards registry:** authoritative metadata about selected codes, editions and source provenance; the licensed normative documents remain the authority for their actual content.
3. **Compliance rules:** typed and reviewed interpretations of specific normative provisions, with bounded capability and validation tests.
4. **CAD/PMI canonical model:** authoritative dimensions, tolerances, datums and their feature attachments; drawing PDFs/DXF/SVG are views/exports, not the source of engineering meaning.
5. **Evidence:** immutable results tied to specific geometry revisions, project baseline, standard editions and rule-implementation versions.
6. **Humans:** explicitly approve code selection, open interpretation questions, safety-critical decisions, design reviews and release where appropriate.

### Requirements authority (revised 15 October 2026)

SysML v2 and StrictDoc overlap on requirement definition, hierarchy and traceability. SysML v2 also carries formal constraints, satisfy relationships and verification cases as native model semantics; StrictDoc's strengths are textual requirements, documentation, traceability matrices and exports. Two editable requirement stores would split the truth: if an agent changes a maximum allowable pressure in SysML while StrictDoc still holds the old value, the compliance engine has no single authority to trust. So there is no bidirectional editing, and data flows one way:

- **SysML v2 owns** engineering requirements, formal constraints, design intent and system relationships.
- **Guacamole owns** standards applicability decisions, compliance rules, validation execution and evidence records, linked directly to SysML requirements rather than copied into another requirements system.
- **StrictDoc (optional)** produces human-readable specification packages, traceability tables and review reports exported from the model. The SysML→StrictDoc adapter would be custom Guacamole code.
- **ReqIF** (`reqif` library) handles requirement exchange with external tools such as DOORS and Polarion.

Changes imported back (StrictDoc edits, customer ReqIF) become controlled proposals against SysML, reviewed by the Systems Engineer like any other requirement change; they never silently overwrite the model.

Guacamole already has the SysML side: the OpenMBEE SysML Toolkit (`sysml` SDK) parses and checks every model revision, and the Systems Engineer's compliance gate (`review_issues()`) lists every constrained requirement the model does not yet satisfy. That leaves little for StrictDoc's requirements management to add. Priority for the requirements/standards track: (1) SysML parsing and validation, in place; (2) the Standards & Compliance Engine; (3) `reqif`; (4) Docling + NISO STS ingestion; (5) StrictDoc, only if its traceability UI, browser editor or reporting is wanted later.

## 3. Reusable open-source Python projects

| Priority | Project | URL | Role | Limit / adoption decision |
|---|---|---|---|---|
| In place | **SysML Toolkit** (OpenMBEE `sysml` SDK) | https://github.com/Open-MBEE/sysml-sdk | SysML v2 parsing and validation; already Guacamole's model layer (`integrations/sysml/`). | OpenSysML was suggested for this role; not needed alongside it. |
| P0 prototype | **FreeCAD MBD Workbench** | https://github.com/ChipsWoodShop/FreeCAD-MBDWorkbench | Python-based FreeCAD addon for semantic datum features, datum systems, feature-control frames, validation and supported STEP AP242 PMI interchange. | Early public preview, LGPL-2.1; supported subset only. Use as experimental backend; do not make this Guacamole's canonical PMI schema. |
| P0 foundation | **pythonocc-core** | https://github.com/tpaviot/pythonocc-core | Python access to OCCT geometry and XDE/STEPCAFControl mechanisms underpinning semantic PMI exchange. | Need an end-to-end capability spike for the exact GD&T classes and installed OCCT version. |
| Alternative backend | **CadQuery/OCP** | https://github.com/CadQuery/OCP | Modern Python OCCT bindings used in the CadQuery ecosystem. | Prefer one primary OCCT binding per process; test available class coverage before deciding between OCP and pythonocc. |
| P0 renderer | **ezdxf** | https://github.com/mozman/ezdxf | Read, write and audit editable DXF documents; custom blocks and drafting geometry for views, datum tags and FCFs. | DXF primitives **do not** establish ISO/ASME conformance; the rules and annotation compiler are custom. |
| Optional | **StrictDoc** | https://github.com/strictdoc-project/strictdoc | Text/Git-based requirements, traceability, documentation and reports. | Downstream documentation adapter, not a core dependency: renders reports from the SysML model, never a second editable requirements store (§2). Apache-2.0. |
| P0 interchange | **reqif** | https://github.com/strictdoc-project/reqif | Python ReqIF/ReqIFz parsing, writing and validation. | ReqIF exchanges *requirements*, not complete standards documents. Apache-2.0. |
| P0 ingestion | **Docling** | https://github.com/docling-project/docling | Extract layout, tables, equations and text from licensed PDFs and other supported documents. | Extraction is fallible; require source anchors, licence checks and human approval before any extracted content becomes an executable rule. MIT core licence; check model licences. |
| P0 ingestion | **xmlschema** | https://github.com/sissaschool/xmlschema | Validate XML against available XSDs; parse XML-based interchange such as NISO STS and QIF. | Conformance to XML structure is not equivalent to correct normative interpretation. |
| P0 rules | **rule-engine** | https://github.com/zeroSteiner/rule-engine | Typed/sandboxed selectors for applicability and conditional activation. | Not a mechanical design-code solver; mathematical checks are separate reviewed Python functions. BSD-3-Clause. |
| P0 numerical | **Pint** | https://github.com/hgrecco/pint | Unit-aware quantities, conversions and dimension checks. | Does not supply engineering code equations or approved material tables. |
| P1/P2 tracing | **pySHACL** | https://github.com/RDFLib/pySHACL | RDF/SHACL consistency constraints over a semantic evidence graph. | Optional; simple project scale can initially use relational tables and/or NetworkX. |
| P2 templates | **StrictDoc templates** | https://github.com/strictdoc-project/strictdoc-templates | Existing structured templates covering, among other subjects, ECSS and DO-178C. | Useful acceleration, not certification or a substitute for licensed/current standards. |
| P3 inspection | **QIF community** | https://github.com/QualityInformationFramework/qif-community | QIF 3.0 samples and Python bindings for downstream dimensional inspection exchange. | Later integration; not necessary for drawing MVP. |
| Research only | **pv-calc** | https://github.com/ccluett/pv-calc | Examples of transparent external-pressure calculation and validity reporting. | NOT an AS 1210 implementation or a basis for claiming code compliance; evaluate only as design/research reference. |

The existing CAD engine may remain FreeCAD. **Don't replace the geometry backend just to improve drawings**: isolate a `CADFeatureResolver`, `PMIBackend`, and `DrawingRenderer` interface and evolve them independently.

## 4. Supported standards and format profiles

### Initial: ISO GPS mechanical engineering

A candidate `ISO_GPS_MECHANICAL_2026` profile should identify exact selected publications (and relevant amendments):

- **ISO 8015:2011** — GPS fundamental concepts.
- **ISO 1101:2017** — geometrical tolerancing indications and interpretation.
- **ISO 5459:2024** — datums and datum systems.
- **ISO 14405-1:2025** — linear-size tolerancing.
- **ISO 129-1:2018** — dimensional/tolerance presentation.
- **ISO 5457:1999 + Amd 1:2010** — technical drawing sheet sizes/layout.
- **ISO 7200:2004** — title block fields.
- **ISO 21920-1:2021** — indication of surface texture.
- **ISO 22081:2021** — general geometrical and size specifications.
- **ISO 10303-242:2025** — target STEP AP242 exchange profile (managed model-based 3D engineering).

Add relevant reference standards (e.g., ISO 5458 on pattern/position tolerancing) only after a reviewed applicability analysis. Select a precise amendment/revision baseline rather than claiming that an unversioned `ISO` tag guarantees compliance.

### Other profile families

- `ASME_Y14` (including ASME Y14.5-2018 (R2024) for GD&T).
- `AU_TECHNICAL_DRAWING` (including relevant parts of AS 1100 as confirmed for the use case).
- `ECSS_SPACE`, `DO178C_AVIONICS`, and approved company-specific overlays.
- `AU_PRESSURE_VESSEL` described below.

**Profile switching is NOT symbol substitution.** ISO GPS and ASME Y14.5 differ semantically. The system must translate only verified equivalent concepts and report non-equivalent or ambiguous constructs for engineering review.

### Canonical interchange map

| Source or artifact | External interchange |
|---|---|
| Full publisher-tagged standard | **NISO STS 1.2 XML**, if legally available |
| Requirements and traceability exchange | **ReqIF 1.2 / ReqIFz** |
| Geometry with semantic PMI/GD&T | **STEP AP242** (test capability/edition subset) |
| Editable 2D drawing | **DXF**; **SVG** for visual review |
| Human-readable, released drawing/report | PDF |
| Inspection plans/results | **QIF** (later) |
| System/project model | **SysML v2** |
| Native machine-checking | Guacamole-typed schemas and Python rule modules |

NISO STS is a **content/interchange format for publishers' standards documents**, not a guarantee that purchased ISO/AS PDFs are available in STS. ReqIF is a **requirements interchange** format; it does not transfer full normative standard semantics automatically.

## 5. Data model and contracts

Use Pydantic or a comparable typed-schema mechanism; serialize project baselines and rule-pack manifests in versioned YAML/JSON.

```yaml
standards_profile:
  id: ISO_GPS_MECHANICAL_2026
  profile_revision: '1.0.0'
  standards:
    - id: ISO-1101
      edition: '2017'
      verification_status: reviewed
      source_id: licensed-source-or-catalogue-id
      source_sha256: '<hash-of-authoritative-source>'
      rules_pack: iso1101_2017_v1
      implementation_coverage: partial
  release_policy:
    unverified_mandatory_requirements: block
    unapproved_code_selection: block
    broken_geometry_references: block
```

Each compiled compliance rule records:

- Stable rule ID; standard ID, edition, amendment and **precise clause reference**.
- Source URI/hash, ingestion method, reviewer, interpretation revision.
- Normative strength, rule type, dependency inputs and applicability predicate.
- Verification method: `schema`, `geometric`, `analytical`, `simulation`, `documentary`, `inspection`, or `human_review`.
- Executable validator name/version where implemented; coverage limitations.
- Measured result, assumptions, tolerances, evidence artifact/hash, timestamp and model revision.

Use distinct outcomes `PASS`, `FAIL`, `NOT_APPLICABLE`, `UNKNOWN`, `REQUIRES_REVIEW` and `NOT_IMPLEMENTED`. **Only `PASS` establishes that a specific implemented check passed.** Unknown, missing or unsupported mandatory items block an unrestricted release.

Suggested API:

```python
resolve_applicability(project_context) -> ApplicabilityReport
compile_standards_profile(selection, approvals) -> StandardsProfile
validate_artifact(artifact, profile, rule_set) -> ComplianceReport
collect_evidence(compliance_report, artifact_hashes) -> EvidenceBundle
request_release(evidence_bundle, approval_policy) -> ReleaseDecision
```

The resolver must be capable of returning `candidate` rather than falsely definitive selections when an equipment classification, facility context, contract or local regulation is uncertain.

## 6. Semantic GD&T and drawing pipeline

```text
SysML functional interfaces and manufacturing intent
  -> CAD geometry + stable named engineering features
  -> datum and functional tolerance proposals (AI-assisted)
  -> human-approved canonical PMI specification
  -> deterministic ISO/ASME-profile semantic checks
  -> feature mapping validation after every geometry revision
  -> OCCT/FreeCAD PMI adapters
  -> STEP AP242 with semantic PMI
  -> drawing compiler -> DXF/SVG/PDF
  -> round-trip/conformance test -> release gate
```

Canonical PMI should represent **datum features and reference systems, dimensional size specifications, geometrical tolerance type, tolerance zone geometry, material modifiers, actual feature references, associated basic dimensions and applied standard semantics**. Do not store PMI merely as glyphs or concatenated strings.

Drawing deliverables should support project profiles for projection convention, title/revision blocks, units, scale, line/dimension style, sheet borders and sizes, general notes, manufacturing finish, tolerance note, BOM, orthographic and section/detail views, and QA/inspection references. The renderer must not invent tolerances simply to populate a drawing.

**Topology hazard:** FreeCAD/OCCT face indices may change after geometric edits. Feature-to-PMI references must carry stable logical feature IDs plus geometry fingerprints/validation; ambiguous remapping must invalidate affected PMI until resolved.

**Initial OCCT spike:** Confirm actual Python bindings expose the required `XCAFDoc_*` and `STEPCAFControl_*` operations on your installed versions. Create a minimal part with face-bound datum A, size specification, position tolerance and datum reference frame; write AP242; reload independently; compare typed PMI and feature attachment. OCCT supports multiple PMI types with documented restrictions; do not assume perfect coverage.

Use freely available **NIST PMI test cases** and **CAx-IF AP242 PMI recommended practices** for regression and interoperability testing. Passing an AP242 round trip means the tested subset survives exchange, **not** that every GD&T choice is functionally appropriate or ISO-compliant.

## 7. Australian pressure-vessel demonstrator

**Sample prompt:** “Design a welded 200 L vessel with a specified design pressure for installation in NSW.”

Before starting design, ask for or explicitly flag missing inputs: vessel configuration, fluid/phase and hazard classification inputs, design pressure including vacuum/external pressure, full temperature range, material and allowed design stresses, corrosion allowance, weld/joint assumptions, fabrication location, intended duty, inspection/service regime, and contractual/regulatory pathway.

Candidate applicable family:

- **AS/NZS 1200:2015** — overarching pressure equipment framework.
- **AS 1210:2010**, with relevant amendments and current reconfirmation metadata (reported R2025) — pressure-vessel design/manufacture/documentation, subject to actual code selection and scope.
- **AS 4343:2014** — equipment/fluid hazard classification.
- **AS 4458** — pressure equipment manufacture, if required by the selected code path.
- **AS 4037** — examination/testing, if applicable.
- **AS 3992**, **AS 3920.1** and other referenced standards where genuinely required, not as indiscriminate blanket obligations.
- Applicable **NSW Work Health and Safety legislation/regulations and SafeWork NSW registration rules** as a distinct regulatory source.

For NSW, SafeWork NSW currently identifies pressure-vessel *design registration* for hazard levels **A–D** and individual *item registration* for **A–C**, subject to stated exceptions. The engine must distinguish these two obligations, check exceptions and record independent verification evidence where legally required. **AS 1210 is not automatically mandatory for every Australian vessel merely because its location is Australia**: determine adoption, project contract, jurisdiction, equipment scope and permitted alternatives.

The first demonstration must resolve standards and produce a compliance/verification plan; it is **not** an autonomous vessel certification application. Do not implement formulae from memory or substitute generic thin-wall equations for AS 1210 clause requirements. Source all code equations and material tables from lawful authoritative editions, implement them as reviewed numerical routines with valid-domain checks, and independently verify benchmark cases.

**Pressure-vessel outputs:** `applicability.json`, `standards.lock.yaml`, `hazard_classification.json` (or unresolved), `required_inputs.json`, `pressure_vessel_compliance_matrix.json`, evidence register, signed review status, and eventually design/analysis/drawing documents.

## 8. Suggested package layout (proposed, not based on a code audit)

```text
guacamole/
  standards/
    models.py                  # typed standard, profile and rule schemas
    registry.py                # editions, amendments, references, metadata
    applicability.py           # project/jurisdiction/discipline resolution
    profile.py                 # baseline and resolution/precedence
    ingest/
      niso_sts.py              # publisher-structured standards XML
      reqif_adapter.py         # requirement interchange
      licensed_pdf.py          # Docling/PDF extraction with provenance
    rules/
      expressions.py           # applicability selectors
      evaluators.py            # deterministic validation interfaces
      units.py                 # Pint quantities
    packs/
      iso_gps/
      au_pressure_equipment/
      asme_y14/
    compliance/
      traceability.py
      evidence.py
      report.py
      release_gate.py
  pmi/
    models.py                  # Guacamole-owned semantic PMI IR
    feature_mapping.py        # durable feature identities
    validators/
    adapters/
      freecad_mbd.py
      occt_ap242.py
    drawing/
      layout.py
      iso_gps.py
      asme_y14.py
      dxf_renderer.py
  tests/
    compliance/
    pmi_nist/
    standard_profiles/
```

Maintain engine schemas and user-approved rule packs within Guacamole; isolate third-party packages behind adapters. The schema must support company overlays without allowing less-strict project defaults to silently override mandatory regulations or contractual requirements. Resolve conflicts explicitly and record the engineering authority for the choice.

## 9. Implementation roadmap and definition of done

### M0 — Standards foundation

Implement registry, immutable project `standards.lock`, licensing/provenance metadata, applicability resolution, reviewed rule schemas, unknown/fail/review statuses and release-gate integration. Unit-test amendment/version comparisons and missing-context behavior.

**Acceptance:** Changing jurisdiction, chosen code edition or key equipment properties triggers a fresh applicability/verification assessment. An unresolved mandatory item cannot receive an unqualified `PASS`.

**Status (15 October 2026): built on the existing records, not as a separate `standards/` package.** Requirement records gained a `Standard` pin (designation, edition, amendments, licensed text, applicability basis) and a `Clause` link. The edition must be stated in a human source, each standard is selected once, and changing the basis, edition or text makes everything resting on them stale. A selection without licensed text blocks review readiness. Review packages carry a Standards table and `standards.lock.json`, and requirements no keyed check covers read "not checked". Covered by `tests/test_standards.py`. **Added 15 October 2026 (`src/guacamole/standards.py`, tests in `tests/test_standards.py`):**
- **Catalogue and facts.** A standards catalogue is recorded from a reviewed source (`project.record_catalogue`). Requirements state facts (`Fact`) whose value and unit their quote must say.
- **Applicability rules.** They are evaluated in a safe expression subset with three-valued logic, using the stdlib `ast` module, so no `rule-engine` dependency. A missing fact gives unknown, never false.
- **Review gate.** A mandatory standard that applies and is unselected, or whose applicability is unknown, blocks a review (the "unresolved mandatory item" acceptance). Packages carry an Applicability table.
- **Edition ordering.** `edition_key` sorts by year, then amendment, and the table flags superseded editions.
- **Withdrawal.** It is a human-sourced `Withdrawal` on a requirement revision. The requirement leaves the model, plans and checks and stays in the record, and its dependants go stale.

**Units: Pint deliberately not added.** Every comparison in the runtime is in the unit its bound names, and tests enforce that (a gram value against a kilogram bound is rejected, not converted). Facts follow the same rule: a fact in another unit counts as missing until restated.

### M1 — Professional engineering drawings

Implement `ISO_GPS_MECHANICAL` profile and a DXF/PDF renderer with sheet/title/revision control, complete dimensions and a typed feature/datum/FCF intermediate representation. Test FreeCAD MBD Workbench as a pluggable adapter.

**Acceptance:** An independently reviewed, editable manufacturing drawing is generated from an existing Guacamole CAD example; malformed datum references and unsupported tolerances are flagged. Output appearance meets the selected validated drawing subset.

**Status (15 October 2026): built as example tooling, not in the runtime.** `examples/drafting.py` holds:
- a typed PMI: named features with geometry fingerprints, ISO 5459 datums, ISO 14405-1 sizes, ISO 1101 frames and the ISO 22081 general specification;
- a validator that flags malformed datum references and unsupported tolerances;
- a compiler to an editable DXF (ezdxf), with an SVG rendered from that DXF;
- a read-back conformance check of the DXF against the PMI.

The supported subset covers flatness, parallelism, perpendicularity, position and surface profile; ISO 129-1 dimensions; ISO 5457 A3; ISO 7200; ISO 5455; and third-angle projection.

The bracket example now publishes its PMI and drawing. `bracket_check` re-maps every PMI feature onto the reopened model, which is the topology guard, and checks the DXF.

**Not built:**
- **PDF output: built 2026-10-15.** `drafting.pdf()` is a minimal vector PDF writer behind ezdxf's drawing frontend: ISO line weights, even-odd glyph fills, no new dependency. The bracket now produces seven files.
- **Other profiles: built 2026-10-15.**
  - **First angle:** `Sheet.projection = "first"` (ISO 5456-2 method E) moves the plan view below and the view from the right to the left, and mirrors the symbol.
  - **ASME Y14.5-2018:** `PMI.profile` checks the ASME subset. The drawings carry ASME notes, read vertical dimensions from the bottom, and add Ⓘ or Ⓔ after sizes.
  - **Translation:** `drafting.translate()` restates a PMI in the other profile and gives a sentence for each change:
    - coaxiality, concentricity and symmetry become position;
    - ISO independency is stated as Ⓘ, and Rule #1 as Ⓔ;
    - position and profile frames sharing their datums get SEP REQT;
    - CZ, ACS and Ⓡ frames are left out.
  - **Still not drawn:** ASME's SEP REQT and EACH ELEMENT notes under frames, which `undrawn()` refuses.
- **Other sheet sizes: built 2026-10-15.** `Sheet.size` selects an ISO 5457 sheet from A4 (upright) to A0. On an upright sheet the revisions table stacks above the notes, clear of the centring marks.
- **Agent-proposed tolerancing: built 2026-10-15.** `bracket_generate` takes an optional `Tolerancing` proposal covering:
  - the hole class, H7 to H14;
  - the position at MMC;
  - the mounting-face flatness;
  - the ISO 22081 general values.

  Deterministic rules gate it: the floating fastener (T ≤ H − F) and a flatness tighter than the general profile. `bracket_check` re-verifies the fastener rule from the published PMI and BOM. Without a proposal, the family rule applies.
- **The FreeCAD MBD Workbench adapter:** moved to M2, where AP242 needs 3D semantic PMI.

The renders have been reviewed visually here; acceptance still needs a qualified drafter's independent review.

### M2 — Semantic PMI and AP242

Implement typed PMI → OCCT/FreeCAD mappings, robust face association, STEP AP242 import/export, round-trip discrepancy reporting and tests against NIST/CAx-IF cases. Differentiate semantic PMI coverage from drawing-only annotations.

**Acceptance:** A declared supported datum/dimension/GD&T test matrix round-trips with exact values, modifiers and geometry attachments; unsupported constructs are reported and never dropped silently.

**Status (15 October 2026): built as example tooling over OCCT 7.9.3 (CadQuery's OCP).** `examples/ap242.py` does three things:
- It writes the typed PMI into STEP AP242 on the faces each feature names.
- It reads AP242 back independently. Every construct ends up mapped, listed as unmapped with its reason, or counted as presentation only; none is dropped.
- It compares the result with the PMI field by field.

The bracket's STEP is now AP242 with its PMI, and `bracket_check` requires an exact round trip.

**The declared matrix round-trips exactly** (`tests/test_ap242.py`): values, modifiers and face attachments, over these constructs:
- datums on planes and on features of size, in systems of one to three, with Ⓜ or Ⓛ on a datum;
- datum targets: points, lines, circles and rectangles (CAx-IF PMI 4.1, section 6.6);
- sizes by ISO 286 class or by deviations: hole and shaft diameters, slot and tab widths, and radii;
- linear locations between planes, axes and median planes;
- all fifteen ISO 1101 characteristics, coaxiality included, with ⌀ zones, Ⓜ, Ⓛ, zero at MMC and the modifiers.

Projected zones, all around and all over are the exceptions: OCCT's writer drops them, and `write()` lists them as not carried.

**NIST's 17 AP242 test files** (CTC, FTC, STC): all 819 constructs are accounted for:
- 138 sizes and locations, and 172 frames, mapped;
- 269 listed, each with its reason;
- 240 presentation only.

CTC 4 matches NIST's drawing of it.

**OCCT defects found and handled:**
- Its writer stores ISO 286 grades two too high, so H13 would become H15.
- Its reader returns 0 for tolerance magnitudes in complex encodings, so every mapped value is confirmed against the file text.
- Its reader drops the sign of a lower deviation above nominal.
- Its reader returns GD&T values in NIST's inch files unscaled. Each nominal is checked against the geometry in mm, inches or metres.
- Its writer drops projected zones, all around and all over.

**Not built:**
- The ISO 22081 general size tolerance in AP242. AP242 has no semantic entity for it, and OCCT cannot write the CAx-IF practice's semantic text. The general surface profile is carried, on every face no other surface profile covers (CAx-IF PMI 4.1, section 6.3).
- Area and curve datum targets, movable targets, and the rest of AP242 outside the typed PMI. These are listed, not mapped.
- Drawing datums on surface sets, frames on surface sets without one radius, and locations of median planes; `drafting.undrawn()` refuses them. Everything else in the typed PMI is drawn: widths as dimensions with their frames and datums in line, radii at their arc, datums on holes under their callout, datum targets in the view facing them, and toleranced locations. Dimensions sit in the views' side stacks, so a step's extension lines can cross the part.
- **Graphical presentation PMI: built 2026-10-15.** Every semantic construct carries a tessellated presentation, linked as "PMI representation to presentation link" with its annotation plane (CAx-IF PMI 4.1, section 8):
  - It is drawn with the drawing compiler's own symbols, text as glyph outlines.
  - It stands upright in a principal view plane by its feature.
  - `read()` counts the presented constructs.
- ISO/ASME profile translation: built 2026-10-15 (see M1, other profiles). AP242 through OCCT declares no dimensioning standard and carries no Ⓔ or Ⓘ; `write()` lists both.

**The FreeCAD MBD Workbench (built as an adapter, 2026-10-15):** its 63 test STEP files read cleanly (150 constructs, all accounted for).

`examples/mbd.py` drives the Workbench in headless FreeCAD. It writes the PMI as the Workbench's own objects on the model's faces, saves that FreeCAD model, and exports with the Workbench's AP242 exporter. `ap242.read` then checks the file against the PMI as the Workbench was given it.

The Workbench can't hold everything, and the adapter lists each loss:
- ISO 286 classes;
- coaxiality, concentricity and symmetry (it follows ASME);
- datum material requirements;
- widths, surface sets and locations;
- the ISO 22081 general specification;
- one frame for a whole pattern (it writes one frame per face).

On the bracket, datums A and B and the four position frames come through. FreeCAD 1.1's OCCT 7.8.0 attaches no face to a datum on a plane bounded by one loop, so datum C is lost; OCCT 7.9.3 attaches all twelve faces.

The Workbench stays an experimental second writer. The canonical PMI is unchanged.

### M3 — Australian pressure-equipment compliance pack

Build applicability and classification pipeline for AS/NZS 1200, AS 1210, AS 4343 and NSW regulatory registration obligations. Add licensed clauses and reviewed deterministic analytical checks incrementally; generate traceability and human-review documentation.

**Acceptance:** Example prompts are correctly routed, critical inputs required, editions pinned, necessary external review identified, and safety-critical release blocked in absence of evidence.

### M4 — Standards interchange and expansion

Production-harden NISO STS ingestion, ReqIF exchange, changes/impact analysis, company-specific profile overlays, optional QIF inspection flow and ECSS/DO-178C profile templates.

**Acceptance:** A changed normative rule identifies affected SysML elements, CAD features, drawings, solver runs and evidence, and reopens the correct approvals without modifying unrelated artifacts.

## 10. Release state and safety rules

Avoid `DESIGN COMPLIANT` as a blanket machine-generated claim. Distinguish:

- **Draft:** requirements and artifacts still changing.
- **Checked — supported subset:** all executed validators for the supported rule coverage passed.
- **Review required:** outstanding ambiguities, legal/code selection, calculations or approvals.
- **Blocked:** mandatory failures, unknowns, missing licensed authority, broken PMI references or stale evidence.
- **Released with approved scope:** human-authorized and traceable design baseline with clearly stated coverage, limitations and applicable approvals.

Standards and project files may contain untrusted or misleading instructions; treat ingested document text as **data**, not commands to agents or the host. Enforce document licences, prevent unauthorized redistribution into public repositories/vector stores, and restrict external/cloud sharing of customer CAD and purchased standards.

## 11. Reference reading and validation sources

**Open-source projects**

- https://github.com/ChipsWoodShop/FreeCAD-MBDWorkbench
- https://github.com/tpaviot/pythonocc-core
- https://github.com/CadQuery/OCP
- https://github.com/mozman/ezdxf
- https://github.com/strictdoc-project/strictdoc
- https://github.com/strictdoc-project/reqif
- https://github.com/strictdoc-project/strictdoc-templates
- https://github.com/docling-project/docling
- https://github.com/sissaschool/xmlschema
- https://github.com/zeroSteiner/rule-engine
- https://github.com/hgrecco/pint
- https://github.com/RDFLib/pySHACL
- https://github.com/QualityInformationFramework/qif-community
- https://github.com/ccluett/pv-calc

**Relevant standards and official/interoperability sources**

- NISO STS 1.2: https://www.niso.org/publications/z39102-2022-sts
- ISO STEP AP242: https://www.iso.org/standard/84300.html
- ISO 1101: https://committee.iso.org/standard/66777.html
- ISO 5459: https://www.iso.org/standard/87855.html
- ISO 14405-1: https://www.iso.org/standard/14405-1
- OCCT STEP/PMI documentation: https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/step/step.md
- CAx-IF Recommended Practices (PMI/AP242): https://www.mbx-if.org/home/cax/recpractices/
- NIST model and STEP PMI test corpus: https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0
- AS 1210 catalogue entry: https://www.intertekinform.com/en-au/standards/as-1210-2010-127108_saig_as_as_268450
- AS 4343 catalogue entry: https://www.intertekinform.com/en-au/standards/as-4343-2014-111442_saig_as_as_233116/
- NSW design registration: https://www.safework.nsw.gov.au/licences-and-registrations/plant-registrations/plant-design-registration
- NSW item registration: https://www.safework.nsw.gov.au/licences-and-registrations/plant-registrations/plant-item-registration

**Caution:** This is an architectural brief, not a certification or legal determination. Standards and licensing statuses must be revalidated before production use and on each requested profile revision.
