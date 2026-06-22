# Changelog

All notable changes to this project are documented here.

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
