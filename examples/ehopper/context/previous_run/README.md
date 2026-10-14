# Prior work from an earlier run (2026-09-30 to 2026-10-14)

An earlier run of this project produced these notes before it was archived. Treat
them as unverified starting points, not evidence. None of this work passed a
verification, and parts of it predate requirement changes now recorded in
`context/brief.md`, which governs where they differ. Decision, plan and requirement
IDs in these files belong to the archived run and do not exist in this project. Use
them to avoid repeating research, and re-check prices and claims before relying on
them.

## Propulsion and structure sourcing

- `propulsion_source_register_2026-10-11_part01.md`: dated supplier research for
  motors, propellers, ESCs and batteries.
- `propulsion_source_register_2026-10-11_part02_actuators.md`: servo, actuator and
  supply alternatives.
- `propulsion_module_topology_source_register_2026-10-12_01.md`: integrated coaxial
  module options and precedents.
- `structural_tube_supplier_register_2026-10-11_01.md`: CFRP and aluminium tube
  sources.

Prices and stock are catalogue observations from 2026-10-11 and 2026-10-12, not
quotations.

## Structure

- `structural_trade_review_checkpoint_01.md`: comparison of spine counts, spine
  materials, and tripod versus quadpod legs. The CAD candidates built from it later
  failed interference checks (overlapping tube solids and gimbal yoke clearance),
  so they are not carried over.

## Simulator and control

- `pre_edit_root_cause_checkpoint_20261011_01.md`: root causes of the defects in
  the supplied `tooling/6dof_hopper` simulator.
- `pre_edit_caller_reconciliation_r12_20261011_02.md`: the callers each repair
  affects.
- `README_pdr_r12_plant_01.md`: the preliminary plant repair and how to run it.
- `pid_architecture_and_vehicle_interfaces_r12_01.md`: the proposed PID
  architecture and vehicle interfaces.

The repaired simulator copy those notes describe is in the output directory at
`previous_run/repaired_hopper_r12/`. Read or copy it from there; it is not
ingested as a document.
