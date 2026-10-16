import hashlib
import json
from getpass import getpass

from websockets.sync.client import connect

token = getpass("Current EHopper authorization token: ").strip()
# Accept the whole "Authorization: Bearer <token>" line EHopper prints at startup.
token = token.removeprefix("Authorization:").strip().removeprefix("Bearer").strip()
# True: a priority note for the Chief; the plan and running workers continue.
# False: a correction; the Chief replans from scratch and every worker is stopped.
keep_workers = True
text = """
**HUMAN DESIGN INTERJECT — eHopper Integrated Coaxial Propulsion Architecture**

I am directing a revision to the eHopper PDR propulsion architecture.

**Design decision:** Adopt **Option A — an integrated counter-rotating coaxial motor module** as the preferred architecture, replacing the current separate-motor arrangement with extended bypass arms/elbow structures supporting the lower rotor.

The existing CAD implementation (`BypassArm*`, `BypassSocket*`, `UnresolvedMotorPlate*`) is unnecessarily complex for this application. I want a more compact, concentric, structurally efficient propulsion assembly with a short and preferably symmetric load path.

This is a human-authorized **architecture direction**, not an unconditional selection of the Himax CR28161100 or authorization to purchase hardware.

### Required actions

**1. Chief Agent / Systems Engineering**

- Register this human-directed architecture decision in the authoritative SysML model and update the relevant architecture, requirements traceability and PDR plan.
- Retain previous separate-motor designs as historical trade alternatives, not the preferred design.
- Preserve existing requirements: propulsion below the upper structure, common two-axis gimbal, independent counter-rotating propulsion channels, and the original mission, budget and safety constraints.
- Coordinate revisions between propulsion, structures/CAD and simulator agents.

**2. Propulsion Engineering**

- Prioritize integrated contra-rotating motor assemblies, starting with the Himax CR28161100 and investigating other suitable commercial alternatives.
- Determine whether a commercially available integrated unit can meet the combined thrust, controllability, thermal endurance, efficiency, mass and budget requirements.
- Maintain independent control of both rotors through separate ESC channels to preserve differential reaction-torque yaw authority.
- Obtain authoritative mounting geometry, propeller interfaces, shaft/retention details, actual inter-rotor spacing and manufacturer-supported operating limits.
- Maintain the existing evidence holds for missing paired thrust/torque/current/RPM data and mission-duration thermal qualification. Do not infer coaxial performance by doubling isolated-rotor data.

**3. CAD / Structural Engineering**

Develop a revised parametric FreeCAD assembly implementing the integrated motor architecture.

- Eliminate the separate lower-motor support structure and unnecessary bypass arms.
- Design a compact central motor mounting carrier or symmetric yoke attached to the moving portion of the common two-axis gimbal.
- Connect the carrier to the integrated unit through a physically realizable, documented stationary mounting interface.
- Keep stationary structures outside both propeller swept volumes and ensure rotor concentricity, retention and clearance.
- Preserve the bottom-mounted rotor configuration, upper battery/electronics arrangement, landing-leg clearance and gimbal functionality.
- Reassess gimbal travel, motor mounting loads, thrust-induced bending, reaction torque, bearing/interface loads, vibration susceptibility and manufacturability.
- Recompute structural mass, CG, inertia and material requirements.
- Produce revised FCStd, STEP, arrangement and mounting drawings using the project's applicable engineering drawing standards and GD&T framework.
- Quantitatively compare the new architecture against the existing M4-03 structural candidate, including mass, complexity, mechanical interfaces, clearances and estimated cost.

**4. Plant / Controls Engineering**

- Update the 6DOF plant to reflect the integrated motor configuration, particularly rotor axial offsets, installed mass properties, rotor inertias and propulsion force/moment application.
- Retain separate rotor-speed and reaction-torque dynamics, calibrated coaxial interference parameters, motor/ESC response, saturation and common gimbal control.
- Repeat relevant hover, attitude recovery and landing verification after the model change.

### Engineering constraints and acceptance

Maintain the existing project requirements: approximately 5 m hover height, 300-second uninterrupted hover, controlled landing, and purchased vehicle hardware/materials below AUD 500 excluding tax and shipping, with the established whole-pack accounting rules.

Do not treat missing manufacturer drawings, performance data or physical qualifications as satisfied. Provisional CAD may use explicitly marked assumptions but cannot constitute verified mounting compatibility.

**Expected outcome:** An updated architectural decision, revised integrated-module CAD candidate, refreshed propulsion trade and BOM, updated plant interface and an evidence-based report identifying remaining blockers.

Proceed autonomously with the architecture revision and preliminary engineering work. If no integrated motor module can satisfy the project constraints, explain the infeasibility and request human approval before reverting to the extended separate-motor architecture.

Do not declare a final motor selection, purchase authorization or PDR acceptance until the required supporting evidence exists.
"""

command = {
    # The ID follows the text: rerunning the same message returns the stored result
    # instead of interjecting twice, and an edited message is always sent.
    "id": "interject-" + hashlib.sha256(text.encode()).hexdigest()[:12],
    "command": {
        "kind": "interject",
        # Omit run_id so EHopper targets its active run after a fresh start.
        "author": "Khoi",
        "text": text,
        "keep_workers": keep_workers,
    },
}

print("Connecting to EHopper on 127.0.0.1:8766...", flush=True)
with connect(
    "ws://127.0.0.1:8766",
    additional_headers={"Authorization": f"Bearer {token}"},
    proxy=None,
    # EHopper serves this socket on its busy run loop; allow a slow handshake.
    open_timeout=120,
) as ws:
    ws.send(json.dumps(command))
    print("Interjection sent; waiting up to 120 seconds for acknowledgement...", flush=True)
    try:
        print(ws.recv(timeout=120), flush=True)
    except TimeoutError:
        raise SystemExit(
            "No acknowledgement received. Check the EHopper event log; rerunning "
            "this script is safe because the same text reuses the same command ID."
        ) from None
