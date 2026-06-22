# PhysAnim

A Blender animation helper. Give the active object an initial velocity and a
gravity, preview the trajectory live in the viewport, scrub the prediction
point with the scroll wheel, and bake the result into location keyframes.
Optional air resistance and ground bouncing make the motion as simple or as
physical as you need.

With no air resistance the motion is the exact projectile parabola:

```
p(t) = p0 + v0 * t + 0.5 * g * t^2
```

Enabling air resistance applies the aerodynamic drag equation
(`a = -(0.5*rho*Cd*A/m) * |v|*v`), which has no closed form and is solved by
numerical integration. Bouncing reflects the object off a ground plane.

Tested on **Blender 5.1** (requires 4.2+, ships as an extension).

## Install

It's packaged as a Blender extension.

1. Download `physanim-<version>.zip` from the
   [latest release](https://github.com/jonatanhedborg/physanim/releases/latest).
2. In Blender: `Edit ▸ Preferences ▸ Get Extensions ▸ (top-right ▾) ▸ Install from Disk…`
3. Select the downloaded zip.
4. Enable it if it isn't already.

Alternatively, drag the zip into Blender.

## Use

The panel lives in the 3D Viewport sidebar (press **N**) under the
**PhysAnim** tab.

1. Select an object.
2. Click **Show Preview**. An orange handle and an orange trajectory arc appear,
   with a green dot at the prediction point. The ghost button next to it swaps
   that dot for a **ghost outline** of the object at the predicted location.
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
4. Optionally enable physics:
   - **Air Resistance**: set the **Mass**, pick a **Shape** preset (or a custom
     drag coefficient), give a cross-section (**Area from Bounds** estimates it
     from the object, or enter it), and set **Air Density**. A terminal-speed
     readout shows the combined effect.
   - **Bounce**: set the **Ground Height** and **Bounciness** to bounce the
     object's origin off a horizontal plane (multiple decaying bounces).
5. Choose how far ahead to look:
   - Drag **Prediction Time**, or
   - Click **Scrub Prediction** and roll the **scroll wheel** (Shift = fine,
     Ctrl = coarse). Enter/click confirms, Esc cancels.
   The predicted frame is shown in the panel and next to the green marker.
6. Click **Apply as Keyframes** to insert location keyframes from the current
   frame through the predicted frame.

### Notes & options

- **Handle Distance** changes only how far away the drag handle sits per m/s
  (visual convenience); it does not affect the simulation.
- **Path Steps** controls how smooth the drawn arc looks (plain-gravity only;
  with drag or bounce the path is drawn from the integration steps).
- **Keyframe Every** = `1` keys every frame and is recommended. Larger values
  insert sparser keys, whose interpolation won't follow the true curve, which
  matters most with drag or bounce.
- Baking starts at the **current scene frame** using the object's current
  position as the first keyframe.
- Velocity, gravity and the ground plane are in **world space**. If the object
  is parented, keyframes are written in world space and a warning is shown, so
  the result may not match the parent's transform.
- **Bounce** reflects the object's **origin** off the ground plane, so set the
  height to suit the object's pivot/size.
