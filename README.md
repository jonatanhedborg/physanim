# PhysAnim

A Blender animation helper. Give the active object an initial velocity and a
gravity, preview the projectile trajectory live in the viewport, scrub the
prediction point with the scroll wheel, and bake the result into location
keyframes.

Physics is pure projectile motion:

```
p(t) = p0 + v0 * t + 0.5 * g * t^2
```

Tested on **Blender 5.1** (requires 4.2+, ships as an extension).

## Install

It's packaged as a Blender extension.

1. `Edit ▸ Preferences ▸ Get Extensions ▸ (top-right ▾) ▸ Install from Disk…`
2. Pick this folder, or a zip of it (`blender_manifest.toml` must be at the root).
3. Enable it if it isn't already.

Alternatively, drag the folder/zip into Blender, or for quick iteration symlink
this folder into your user extensions directory.

## Use

The panel lives in the 3D Viewport sidebar (press **N**) under the
**PhysAnim** tab.

1. Select an object.
2. Click **Show Preview**. An orange handle and an orange trajectory arc appear,
   with a green dot at the prediction point.
3. Set the launch:
   - **Drag the orange handle** in the viewport to aim; the handle sits at
     `object + velocity`, so dragging it towards a target updates the
     **Initial Velocity** X/Y/Z numbers to match. (Or type the numbers directly.)
   - **While dragging the handle, roll the scroll wheel** to scrub the
     prediction time live (Shift = fine, Ctrl = coarse).
   - The panel shows the **launch speed**. Toggle the lock to fix the
     speed: the handle then only sets *direction*, the velocity inputs are
     driven from the locked speed, and editing **Launch Speed** rescales the
     velocity while keeping its direction.
   - Adjust **Gravity** if needed (default `0, 0, -9.81`).
4. Choose how far ahead to look:
   - Drag **Prediction Time**, or
   - Click **Scrub Prediction** and roll the **scroll wheel** (Shift = fine,
     Ctrl = coarse). Enter/click confirms, Esc cancels.
   The predicted frame is shown in the panel and next to the green marker.
5. Click **Apply as Keyframes** to insert location keyframes from the current
   frame through the predicted frame.

### Notes & options

- **Handle Distance** changes only how far away the drag handle sits per m/s
  (visual convenience); it does not affect the simulation.
- **Path Steps** controls how smooth the drawn arc looks.
- **Keyframe Every** = `1` keys every frame, giving an exact parabola. Larger
  values insert sparser keys (interpolation between them won't be perfectly
  parabolic).
- Baking starts at the **current scene frame** using the object's current
  position as the first keyframe.
- Velocity and gravity are interpreted in **world space**. If the object is
  parented, keyframes are written in world space and a warning is shown, so the
  result may not match the parent's transform.
