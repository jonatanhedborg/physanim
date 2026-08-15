# Changelog

All notable changes to this project are documented here.

## [1.5.0] - 2026-08-15

### Added
- Pin: a pin button next to Show Preview that keeps the panel, the trajectory
  overlay, the drag handle and the operators on one object while the selection
  changes, so an aim target can be moved without losing the setup being edited.
  The pin is stored on the scene, saved with the file, and clears itself when
  the pinned object is deleted.
- Aim At: point the launch at another object, typically an empty snapped to a
  launch tube. The velocity is then derived from that object and follows it
  live, so aiming uses Blender's normal snapping instead of the drag handle
  (which hides itself while a target is set). Distance sets the speed as usual,
  unless the speed is locked, in which case the target gives direction only.
- Thrust: a list of burns applied over a window of time after the launch, each
  with a start and duration in seconds, a direction (along the current velocity,
  like a rocket motor, or a fixed world vector), and a strength entered either
  as a delta-v (total speed added over the burn) or as an acceleration held for
  its length. Burns can be staged and may overlap, so a booster charge followed
  by a motor is two entries. The arc marks where each burn lights and cuts out,
  and Convert to Rigid Body Sim warns that burns are not transferred.

### Changed
- With Lock Speed on, the velocity handle can be dragged to any distance
  instead of snapping back to the distance implied by the locked speed. Only
  its direction is read, and the distance is remembered separately, so the
  handle can be parked wherever it reads best in the viewport.

## [1.4.0] - 2026-08-15

### Added
- Align to Motion: a toggle that rotates the object to face its direction of
  travel, with a pick of which local axis is forward (+/- X, Y or Z) and which
  axis is kept up. The ghost preview shows the orientation at the prediction
  point, and baking writes rotation keyframes alongside the location ones (on
  the channel matching the object's rotation mode). The direction is read off
  the baked path, so it follows drag and flips after a bounce. Convert to Rigid
  Body Sim uses it for the launch orientation only.

## [1.3.0] - 2026-06-23

### Added
- Convert to Rigid Body Sim: a button that hands the launch position and velocity
  to Blender's rigid body solver. It adds an Active rigid body and keyframes the
  Animated toggle so the object is released at the current frame moving at the
  initial velocity, then Bullet takes over. The playhead is parked on a short
  pre-roll before the launch so pressing Play runs the handoff. Air resistance is
  not reproduced and gravity comes from the scene; warnings are shown if the scene
  gravity differs or the launch is too close to the playback start.

## [1.2.0] - 2026-06-22

### Added
- Occlusion-aware overlay: the trajectory and the prediction marker/ghost fade
  out where they pass behind scene geometry, so the contact point is clear.
- Hold Shift while dragging the velocity handle to move it slowly for fine
  adjustment.

## [1.1.0] - 2026-06-22

### Added
- Ghost preview: a toggle to show the object's outline (evaluated-mesh
  wireframe, bounding-box fallback) at the predicted location instead of a
  marker dot.
- Air resistance: optional aerodynamic drag from real parameters (mass, drag
  coefficient with shape presets, cross-section auto-estimated from bounds or
  manual, air density), with a terminal-speed readout.
- Bounce: optional reflection of the object's origin off a configurable
  horizontal ground plane, with a restitution factor and multiple bounces.

### Changed
- The trajectory is now a general simulation: plain gravity keeps the exact
  closed-form parabola, while drag or bounce use a numerical integrator for the
  preview, marker, ghost, and bake.

## [1.0.0] - 2026-06-22

Initial public release.

- Live projectile trajectory preview in the 3D viewport
  (`p(t) = p0 + v0*t + 0.5*g*t^2`), with a marker at the prediction point.
- Draggable velocity handle: aim by dragging, and scroll the mouse wheel
  while dragging to scrub the prediction time (Shift = fine, Ctrl = coarse).
- Lock Speed: fix the launch speed so the handle only sets direction.
- Scrub Prediction operator for scrolling the prediction point without the
  handle.
- Apply as Keyframes: bake the trajectory to location keyframes from the
  current frame, with delta-location compensation and a warning when existing
  location keyframes overlap the range.
- Packaged as a Blender 4.2+ extension (tested on 5.1), GPL-3.0 licensed.
