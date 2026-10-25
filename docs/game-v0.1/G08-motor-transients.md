# FPV-G08 Motor Transient Dynamics — frozen acceptance card

Base: 7b0170f7e1b4848b6405abd21e0c6fd526e72fef. Scope: browser player only.
Research Draft PRs 1–3 and all G07 reference sources/fixtures remain immutable.

Implement a separate `g08-transient-v1` powertrain. Rotor inertia, motor friction,
ESC current limit and all response parameters are synthetic assumptions, not
measurements. Use passive one-quadrant ESC drive: no battery regeneration;
zero command coasts down rather than deleting stored rotor energy. Fixed 240 Hz
rigid body remains Rapier's sole state; bounded electrical substeps are internal.
Account chemical energy, pack/copper/ESC heat, bearing friction, aerodynamic
shaft work and change in rotor kinetic energy using one consistent midpoint.
Apply motor acceleration reaction and rotor gyroscopic moment as forces/torques,
not direct changes of body position, orientation or angular velocity.

Keep the original G07 class, Python fixtures and tests unchanged. New replay
metadata chooses the model explicitly; missing metadata means G07. Reset and
model selection are explicit. Never interpret old recorded inputs under G08.

Acceptance established before implementation:
- All inherited numerical/input/build/Chromium tests stay binding.
- New initial-rest zero duty, finite spin-up, coast-down, limiting/stall,
  varying-duty energy closure (<1e-6 J over ten seconds), charge (<1e-7 C),
  thermal (<1e-7 J), and invalid-input no-mutation tests.
- 120/240/480 Hz comparison and finer independent ODE reference for transient
  speed; refinement must decrease error, not be tuned by changing old goldens.
- Same-state G07/G08 throttle-step, steady hover and flight trajectories are
  reported, not asserted equal. Same-model replay is deterministic.
- Real Chromium desktop/mobile screenshots and software-renderer performance,
  with original 250 ms interruption safety and unchanged quality budgets.
- Xbox USB/Bluetooth and DualSense USB/Bluetooth, physical-phone performance:
  NOT RUN unless actual hardware exists; software mocks do not satisfy them.
- Draft PR first. No merge or Pages publication until applicable repository
  rules, verification and authorized review are confirmed. Preserve first red.
