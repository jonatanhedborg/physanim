# PhysAnim

A Blender animation helper. Give the active object an initial velocity and a
gravity, preview the trajectory live in the viewport, scrub the prediction
point with the scroll wheel, and bake the result into location keyframes.
Optional settings air resistance, ground bouncing, thrust burns and aligning the
object to its direction of travel.

![PhysAnim in the Blender viewport: an orange velocity handle and a trajectory
arc over a ground plane with a green prediction marker, and the PhysAnim sidebar
panel on the right.](docs/physanim.jpg)

With no air resistance the motion is the exact projectile parabola:

```
p(t) = p0 + v0 * t + 0.5 * g * t^2
```

Enabling air resistance applies the aerodynamic drag equation
(`a = -(0.5*rho*Cd*A/m) * |v|*v`), which has no closed form and is solved by
numerical integration. Bouncing reflects the object off a ground plane.

Tested on **Blender 5.1** (should work on 4.2+).

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
   that dot for an outline of the object at the predicted location. The pin
   button at the end of the row keeps the panel and preview on this object
   while you select and move other things, which is what you want when the
   launch is aimed at an empty.
3. Set the velocity:
   - **Drag the orange handle** in the viewport to aim; the handle sits at
     `object + velocity`, so dragging it towards a target updates the
     **Initial Velocity** X/Y/Z numbers to match. (Or type the numbers directly.)
   - **While dragging the handle, roll the scroll wheel** to scrub the
     prediction time live (Shift = fine, Ctrl = coarse).
   - The panel shows the **launch speed**. Toggle the lock to fix the
     speed: the handle then only sets *direction*, the velocity inputs are
     driven from the locked speed, and editing **Launch Speed** rescales the
     velocity while keeping its direction. With the speed locked the handle can
     also be dragged to any distance you like, since only its direction is
     read, so park it wherever it is easiest to see.
   - Or set **Aim At** to another object, typically an empty snapped to a launch
     tube or a barrel. The velocity then points from the object at that target
     and follows it live, so aiming becomes a matter of moving the empty with
     Blender's normal snapping. The drag handle steps aside while a target is
     set, and a faint line shows what is being aimed at.
   - Adjust **Gravity** if needed (default `0, 0, -9.81`).
4. Optional physics:
   - **Air Resistance**: set the **Mass**, pick a **Shape** preset (or a custom
     drag coefficient), give a cross-section (**Area from Bounds** estimates it
     from the object, or enter it), and set **Air Density**. A terminal-speed
     readout shows the combined effect.
   - **Bounce**: set the **Ground Height** and **Bounciness** to bounce the
     object's origin off a horizontal plane.
   - **Thrust**: click **+** to add a burn, a push applied over a window of
     time after the launch. Set when it starts and how long it lasts (in
     seconds after the launch, with the frame range shown below), whether it
     pushes **Along Velocity** (like a rocket motor) or along a fixed **World
     Vector**, and how strong it is. Add more burns to stage them, for example
     a short booster charge followed by a longer motor. Blue dots on the arc
     mark where each burn lights and cuts out.
   - **Align to Motion**: rotate the object so it faces the way it is moving.
     Pick which local axis is **Forward** (+/- X, Y or Z; the default is +Y,
     Blender's usual "front" for an object modelled facing away from you) and
     which axis is kept **Up**, which fixes the roll around the forward axis.
     With the ghost preview on you can see the orientation at the prediction
     point before baking.
5. Choose how far ahead to look:
   - Drag **Prediction Time**, or
   - Click **Scrub Prediction** and roll the **scroll wheel** (Shift = fine,
     Ctrl = coarse). Enter/click confirms, Esc cancels.
   The predicted frame is shown in the panel and next to the green marker.
6. Click **Apply as Keyframes** to insert location keyframes from the current
   frame through the predicted frame (plus rotation keyframes if **Align to
   Motion** is on).

Or, instead of baking keyframes, click **Convert to Rigid Body Sim** to hand the
launch off to Blender's own physics. It adds an Active rigid body to the object
and keyframes the **Animated** toggle so the object is released at the current
frame moving at the initial velocity, after which the Bullet solver takes over.
The button parks the playhead a few frames before the launch (a short pre-roll
that Bullet needs to pick up the velocity), so just press **Play** from there to
run it. The motion appears once you play through or bake the rigid body cache,
not by scrubbing.

### Notes & options

- **Handle Distance** changes only how far away the drag handle sits (visual
  convenience); it does not affect the simulation. Unlocked it is metres per
  1 m/s of velocity, since the handle's distance is what sets the speed. With
  the speed locked it is a plain distance in metres, free of the speed.
- The **pin** applies to everything the add-on does, not just the panel: the
  trajectory overlay, the drag handle, and the Apply/Convert buttons all keep
  working on the pinned object while another one is selected. The panel says
  which object is pinned. The pin is saved with the file and clears itself if
  the pinned object is deleted.
- **Aim At** derives the velocity rather than storing it, so the direction
  tracks the target and the launcher as either moves, with no need to re-aim.
  Distance still sets the speed unless the speed is locked, in which case the
  target gives direction only. Clearing the target returns to the **Initial
  Velocity** values, which are the last ones set by hand.
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
- A burn's strength is entered either as **Delta-V**, the total speed it adds
  over the burn, or as an **Acceleration** held for the burn's length. The two
  are the same number divided by the duration, and the panel always shows the
  other one below the field. The choice decides what happens when you retime
  the burn: in Delta-V mode the speed change stays put and the acceleration
  moves, in Acceleration mode the push stays put and the speed change moves.
- The delta-v of a burn is the **thrust contribution only**. Gravity and drag
  take their share over the same window, so a 30 m/s burn lasting 3 seconds
  straight up leaves the object roughly 0.6 m/s faster, not 30. The total shown
  under the burn list is thrust delta-v, not a final speed.
- Burns push **Along Velocity** by default, which is what makes a rocket
  accelerate along its flight path without curving it. From a standstill there
  is no velocity to follow, so the thrust starts along the launch direction, or
  straight up if the launch velocity is zero too.
- Any burn switches the trajectory to the numerical integrator, the same as air
  resistance and bounce do, so the exact parabola is used only for plain
  unpowered throws.
- **Align to Motion** replaces the object's rotation rather than adding to it,
  and writes keys on whichever rotation channel matches the object's rotation
  mode (euler, quaternion or axis-angle). The direction is read off the baked
  path, so it follows drag and flips after a bounce. At the apex of a straight-up
  throw the direction is undefined for an instant, and the rotation there is
  left as it is.
- **Convert to Rigid Body Sim** transfers only the initial conditions (position,
  velocity, mass). From there Blender's solver runs the motion, so the result
  diverges from the preview where the preview used effects Bullet does not model
  the same way: air resistance is not reproduced, bouncing needs a collider
  object and uses the scene gravity, thrust burns are not transferred at all
  (the body gets the launch velocity only), and **Align to Motion** only sets the
  orientation at the launch frame, since Bullet owns the rotation from there on. A warning is shown if the scene gravity does
  not match the gravity set here, since the rigid body world uses the scene value.
- The rigid body setup sits just before the launch frame, and a rigid body
  only simulates when you play from the cache start. If the launch is too close to
  the start of the playback range the pre-roll falls outside it and the velocity
  is lost; the button warns when this happens, so move the launch later or lower
  the playback **Start** frame.
