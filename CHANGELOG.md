# Changelog

All notable changes to this project are documented here.

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
