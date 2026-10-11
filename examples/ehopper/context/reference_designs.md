# Reference designs: flown electric coaxial hoppers

Text descriptions of the 7 photos in `context/reference_images/`. Agents cannot
view the images, so this file is the usable source. A human wrote it from visual
inspection only: there is no scale, dimension, part number or performance data.
Anything marked "appears" is an interpretation; confirm it with the human before
using it as a requirement. The photos are social-media screenshots of other teams'
vehicles, not of this project.

## Common configuration (all three vehicles)

- **Rocket-style tail-sitter:** a tall, slender vertical spine with the avionics,
  computer and battery stacked along it. Most of the height and much of the
  mass sit well above the propulsion.
- **One coaxial contra-rotating motor pair at the very bottom**, with the props
  below the airframe and a metal spinner/nose cone at the lowest point. Each
  prop has two blades, and the two props are spaced closely. No vehicle has
  multiple rotors or arms.
- **Thrust vectoring by gimballing the whole motor unit.** A universal (cardan)
  joint sits above the motor mount. Two pushrods with blue anodised aluminium
  servo horns/ball links run from hobby servos on the frame, giving two-axis tilt.
  Roll/yaw appears to come from differential speed of the two motors, since no
  vanes are visible.
- **Splayed tripod (possibly quadpod) landing legs** made of long, thin, black
  (apparently carbon) tubes. They attach at a ring or plate just above the gimbal.
  The feet extend below the prop plane, so the props are clear of the ground, and
  the footprint is wider than the prop disc.
- **Prototype construction:** 3D-printed rings, brackets and avionics bays,
  carbon tubes or threaded rods, off-the-shelf dev boards, and visible loose wiring.

## Vehicle A: "Hopper" studio photos (3 images)

Files: `20f4952c-…jpg`, `60bf8903-…jpg`, `a8dca61e-…jpg`.

- **Avionics:** grey 3D-printed square bays with open/clamshell faces. The upper
  bay holds an ST Nucleo (STM32) dev board. The lower bay holds a custom green
  PCB with green screw terminals, with "HOPPER" printed on it. Its function
  (power distribution/IO) is not confirmed.
- **Battery:** a LiPo labelled "2200" (mAh), mounted above the avionics bays
  inside the spine frame. The cell count can't be read.
- **Base:** two printed rings joined by printed pillars form a cage. The gimbal
  universal joint hangs below it. One servo (white/grey case) is visible on the
  cage, with an orange servo lead.
- **Motor:** an integrated coaxial contra-rotating unit, with a red anodised
  cage on the upper motor and a silver lower motor. It has six phase leads with
  gold bullet connectors (3 per motor).
- **Legs:** 3 thin tubes, braced to the lower ring by printed struts and brackets.

## Vehicle B: "TAPETI" (2 images)

Files: `1f837ce5-…jpg`, `26f172cd-…jpg`.

- **Flight 03 frame (`1f837ce5`):** a "pre-flight" frame captioned "Autonomous
  flight test – coordinate transformation validation – onboard guidance,
  navigation & control". It shows a tall dense avionics mast with red parts and
  a red coaxial motor cage at the bottom. A black ring and a cable lead upward
  from the top, which appears to be an overhead **safety tether** for early
  flights.
- **Outdoor photo (`26f172cd`):** shows the full vehicle against mountains. It
  appears to be airborne at low height, though this isn't certain. The mast is
  very tall and slender, roughly 2× the leg span, with a red top and a yellow
  band. Its 3–4 long splayed legs give a wide footprint.

## Vehicle C: open-frame Raspberry Pi hopper (1 image)

File: `303aa96c-…jpg`.

- **Frame:** stacked plates on threaded rods, with a Raspberry Pi (fan heatsink)
  mid-stack, yellow XT60 connectors at the top and a lot of loose wiring.
- **Propulsion and legs:** a pink/red coaxial motor unit at the bottom, a large
  two-blade prop and a spinner. It stands on 3 thin splayed legs.

## Vehicle D: "VOID" (1 image, PhotonDelta logo)

File: `79f67b5a-…jpg`.

- **Spine:** a tall square-section truss of four black longerons with
  avionics boards stacked inside. A silver battery pack sits near the top and
  a Pi-style board near the bottom.
- **Top:** a T-crossbar with curved arms, each ending in a small black unit. It
  is unclear whether these are roll thrusters or sensors. A tall black object at
  the top centre appears to be a GNSS antenna.
- **Bottom:** a red coaxial motor with white servos on either side (the gimbal
  actuators) and a two-blade prop. It stands on a tripod of thin legs.

## Takeaways for this project (provisional)

- These photos support the existing choices: bottom-mounted coaxial propulsion
  (REQ-PROPULSION-PLACEMENT), a common two-axis gimbal, and a tripod or quadpod
  of thin CFRP tubes.
- Successful builds keep the avionics simple and off-the-shelf: a Nucleo or
  Raspberry Pi, one integrated contra-rotating motor, and a small LiPo
  (2200 mAh is seen once).
- Their legs reach below the prop plane, with a stance wider than the prop disc.
- Vehicle B used an overhead safety tether for early autonomous flights. Consider
  doing the same in the test procedures.
- The CG sits well above the gimbal pivot. The PID/6-DoF model should represent
  this geometry rather than a compact quad-style mass distribution.
