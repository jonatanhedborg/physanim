# PhysAnim
#
# A small animation helper: give the active object an initial velocity and a
# gravity, preview the projectile trajectory live in the viewport (scrubbing the
# prediction point with the scroll wheel), and bake the result into location
# keyframes.
#
# Physics model is pure projectile motion:
#     p(t) = p0 + v0 * t + 0.5 * g * t^2
#
# Packaged as a Blender extension (manifest based, no bl_info). Works on
# Blender 4.2+ and is tested on 5.1.

import math

import bpy
import gpu
import blf
from bpy.types import Operator, Panel, PropertyGroup, GizmoGroup, Gizmo
from bpy.props import (
    FloatVectorProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty,
)
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
)
from mathutils import Vector, Matrix


# --------------------------------------------------------------------------- #
# Core physics
# --------------------------------------------------------------------------- #

def trajectory_point(p0, v0, g, t):
    """Position of a projectile at time ``t`` (seconds)."""
    return p0 + v0 * t + g * (0.5 * t * t)


def sample_trajectory(p0, v0, g, t_end, segments):
    """Return ``segments + 1`` points sampled evenly in time over [0, t_end]."""
    segments = max(int(segments), 1)
    pts = []
    for i in range(segments + 1):
        t = t_end * i / segments
        pts.append(trajectory_point(p0, v0, g, t))
    return pts


# Fixed integration step and a hard cap on step count, used when the motion has
# no closed form (drag, and later bounce). 240 Hz is plenty for preview/bake.
SIM_DT = 1.0 / 240.0
SIM_MAX_STEPS = 20000


# Drag coefficients (Cd) for common shapes, used by the shape preset.
_CD_PRESETS = {
    'SPHERE': 0.47,
    'CUBE': 1.05,
    'CYLINDER': 0.82,
    'STREAMLINED': 0.04,
    'FLAT_PLATE': 1.28,
}


def _auto_cross_section(ob):
    """Estimate a reference cross-sectional area (m^2) from the object bounds.

    Uses the mean of the three bounding-box face areas, so it's independent of
    which way the object happens to be moving.
    """
    d = ob.dimensions
    return (d.x * d.y + d.y * d.z + d.z * d.x) / 3.0


def _drag_k(props, ob):
    """Effective quadratic-drag coefficient k in ``a = -k*|v|*v``.

    From the aerodynamic drag equation: ``k = 0.5 * rho * Cd * A / m``.
    Returns 0 when air resistance is disabled (closed-form fast path).
    """
    if not props.drag_enabled:
        return 0.0
    area = props.cross_section
    if props.auto_cross_section and ob is not None:
        area = _auto_cross_section(ob)
    mass = max(props.mass, 1e-6)
    return 0.5 * props.air_density * props.drag_cd * area / mass


def _integrate(p0, v0, a_const, drag_k, t_end, bounce=None):
    """Semi-implicit (symplectic) Euler integration with quadratic drag.

    ``bounce`` is ``None`` or ``(ground_z, restitution)``: when the point crosses
    below the ground plane while moving down, it is clamped to the plane and its
    vertical velocity is reflected and scaled by restitution (multiple bounces
    fall out of the loop naturally).

    Returns ``(points, dt)`` where points are sampled uniformly in time.
    """
    dt = SIM_DT
    n = int(t_end / dt) + 1
    if n > SIM_MAX_STEPS:
        n = SIM_MAX_STEPS
        dt = t_end / n
    p = p0.copy()
    v = v0.copy()
    pts = [p.copy()]
    for _ in range(n):
        v = v + (a_const - (drag_k * v.length) * v) * dt
        p = p + v * dt
        if bounce is not None:
            ground_z, restitution = bounce
            if p.z < ground_z and v.z < 0.0:
                p.z = ground_z
                v.z = -v.z * restitution
        pts.append(p.copy())
    return pts, dt


def _sample_path(pts, dt, t):
    """Linear-interpolated position at time ``t`` along an integrated path."""
    if t <= 0.0:
        return pts[0].copy()
    fi = t / dt
    i = int(fi)
    if i >= len(pts) - 1:
        return pts[-1].copy()
    return pts[i].lerp(pts[i + 1], fi - i)


def build_trajectory(p0, v0, props, t_end, drag_k=0.0):
    """Return ``(draw_points, sampler)`` for the trajectory over ``[0, t_end]``.

    ``draw_points`` is a list of ``Vector`` for the viewport polyline; ``sampler``
    is ``f(t) -> Vector`` giving the position at time ``t``. With no drag the
    motion uses the exact closed form; air resistance uses the integrator.
    """
    t_end = max(t_end, 1e-6)
    a_const = Vector(props.gravity)
    bounce = (props.ground_height, props.restitution) if props.bounce_enabled else None

    if drag_k <= 0.0 and bounce is None:
        def sampler(t, _p0=p0, _v0=v0, _a=a_const):
            return trajectory_point(_p0, _v0, _a, t)

        n = max(int(props.resolution), 2)
        draw = [sampler(t_end * i / n) for i in range(n + 1)]
        return draw, sampler

    pts, dt = _integrate(p0, v0, a_const, drag_k, t_end, bounce)

    def sampler(t, _pts=pts, _dt=dt):
        return _sample_path(_pts, _dt, t)

    stride = max(1, len(pts) // 512)
    draw = pts[::stride]
    if draw[-1] is not pts[-1]:
        draw.append(pts[-1])
    return draw, sampler


def scene_fps(scene):
    return scene.render.fps / scene.render.fps_base


def _has_location_keyframes(ob, frame_lo, frame_hi):
    """True if the object already has location keyframes within [lo, hi].

    Tolerant of both legacy actions (Blender < 4.4) and slotted actions (4.4+).
    """
    ad = ob.animation_data
    if ad is None or ad.action is None:
        return False
    action = ad.action

    def in_range(fc):
        return fc.data_path == "location" and any(
            frame_lo <= kp.co[0] <= frame_hi for kp in fc.keyframe_points)

    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return any(in_range(fc) for fc in legacy)

    slot = getattr(ad, "action_slot", None)
    for layer in action.layers:
        for strip in layer.strips:
            try:
                bag = strip.channelbag(slot) if slot is not None else None
            except (TypeError, RuntimeError):
                bag = None
            if bag is not None and any(in_range(fc) for fc in bag.fcurves):
                return True
    return False


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _tag_view3d_redraw(context):
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        screen = win.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _redraw_update(self, context):
    _tag_view3d_redraw(context)


def _update_lock(self, context):
    # When locking, keep the current launch speed as the locked target so the
    # velocity doesn't jump. Setting locked_speed re-normalises via its own update.
    if self.lock_speed:
        v = Vector(self.velocity)
        if v.length > 1e-9:
            self.locked_speed = v.length
        else:
            self.velocity = Vector((0.0, 0.0, 1.0)) * self.locked_speed
    _tag_view3d_redraw(context)


def _update_locked_speed(self, context):
    # While locked, the stored velocity always has magnitude == locked_speed,
    # so downstream physics/drawing can use `velocity` directly.
    if self.lock_speed:
        v = Vector(self.velocity)
        if v.length < 1e-9:
            v = Vector((0.0, 0.0, 1.0))
        self.velocity = v.normalized() * self.locked_speed
    _tag_view3d_redraw(context)


def _update_cd_preset(self, context):
    # Selecting a shape fills in its drag coefficient; 'CUSTOM' leaves it alone.
    cd = _CD_PRESETS.get(self.cd_preset)
    if cd is not None:
        self.drag_cd = cd
    _tag_view3d_redraw(context)


# --------------------------------------------------------------------------- #
# Properties (stored per object)
# --------------------------------------------------------------------------- #

class PHYS_PG_props(PropertyGroup):
    show_preview: BoolProperty(
        name="Show Preview",
        description="Draw the predicted trajectory and the velocity handle in the viewport",
        default=False,
        update=_redraw_update,
    )
    ghost: BoolProperty(
        name="Ghost",
        description="Show a ghost outline of the object at the predicted location "
                    "instead of a marker dot",
        default=False,
        update=_redraw_update,
    )
    velocity: FloatVectorProperty(
        name="Initial Velocity",
        description="Launch velocity in world space (metres per second)",
        size=3,
        subtype='VELOCITY',
        unit='VELOCITY',
        default=(0.0, 0.0, 8.0),
        update=_redraw_update,
    )
    lock_speed: BoolProperty(
        name="Lock Speed",
        description="Fix the launch speed: the viewport handle then only sets the "
                    "direction, and the velocity inputs are driven from the locked speed",
        default=False,
        update=_update_lock,
    )
    locked_speed: FloatProperty(
        name="Launch Speed",
        description="Fixed launch speed (metres per second) used when Lock Speed is on",
        default=10.0,
        min=0.0,
        soft_max=100.0,
        step=10,
        precision=3,
        unit='VELOCITY',
        update=_update_locked_speed,
    )
    gravity: FloatVectorProperty(
        name="Gravity",
        description="Constant acceleration in world space (metres per second squared)",
        size=3,
        subtype='ACCELERATION',
        unit='ACCELERATION',
        default=(0.0, 0.0, -9.81),
        update=_redraw_update,
    )
    drag_enabled: BoolProperty(
        name="Air Resistance",
        description="Apply aerodynamic drag: a = -(0.5*rho*Cd*A/m) * |v|*v",
        default=False,
        update=_redraw_update,
    )
    mass: FloatProperty(
        name="Mass",
        description="Object mass used by the drag equation",
        default=1.0,
        min=1e-4,
        soft_max=100.0,
        step=10,
        precision=3,
        unit='MASS',
        update=_redraw_update,
    )
    cd_preset: EnumProperty(
        name="Shape",
        description="Fill in a typical drag coefficient for a common shape",
        items=[
            ('SPHERE', "Sphere", "Cd ~ 0.47"),
            ('CUBE', "Cube", "Cd ~ 1.05"),
            ('CYLINDER', "Cylinder", "Cd ~ 0.82"),
            ('STREAMLINED', "Streamlined", "Cd ~ 0.04"),
            ('FLAT_PLATE', "Flat Plate", "Cd ~ 1.28"),
            ('CUSTOM', "Custom", "Use the drag coefficient set below"),
        ],
        default='SPHERE',
        update=_update_cd_preset,
    )
    drag_cd: FloatProperty(
        name="Drag Coefficient",
        description="Dimensionless drag coefficient (Cd)",
        default=0.47,
        min=0.0,
        soft_max=2.0,
        step=1,
        precision=3,
        update=_redraw_update,
    )
    auto_cross_section: BoolProperty(
        name="Area from Bounds",
        description="Estimate the reference cross-sectional area from the object's "
                    "bounding box, instead of entering it manually",
        default=True,
        update=_redraw_update,
    )
    cross_section: FloatProperty(
        name="Cross-section",
        description="Reference cross-sectional area facing the airflow",
        default=0.05,
        min=1e-6,
        soft_max=10.0,
        precision=4,
        unit='AREA',
        update=_redraw_update,
    )
    air_density: FloatProperty(
        name="Air Density",
        description="Air density in kg/m^3 (sea level is about 1.225)",
        default=1.225,
        min=0.0,
        soft_max=2.0,
        precision=3,
        update=_redraw_update,
    )
    bounce_enabled: BoolProperty(
        name="Bounce",
        description="Bounce the object's origin off a horizontal ground plane",
        default=False,
        update=_redraw_update,
    )
    ground_height: FloatProperty(
        name="Ground Height",
        description="Z height of the ground plane the object's origin bounces on",
        default=0.0,
        unit='LENGTH',
        update=_redraw_update,
    )
    restitution: FloatProperty(
        name="Bounciness",
        description="Fraction of speed kept after each bounce "
                    "(1 = perfectly elastic, 0 = no bounce)",
        default=0.5,
        min=0.0,
        max=1.0,
        precision=3,
        update=_redraw_update,
    )
    prediction_time: FloatProperty(
        name="Prediction Time",
        description="How far into the future to predict, in seconds",
        default=1.0,
        min=0.0,
        soft_max=10.0,
        step=10,
        precision=3,
        update=_redraw_update,
    )
    resolution: IntProperty(
        name="Path Steps",
        description="Number of segments used to draw the trajectory arc",
        default=64,
        min=2,
        max=1024,
        update=_redraw_update,
    )
    display_scale: FloatProperty(
        name="Handle Distance",
        description="Viewport distance (in metres) per 1 m/s of velocity, for the drag handle. "
                    "Does not affect the simulation",
        default=1.0,
        min=0.001,
        soft_min=0.05,
        soft_max=5.0,
        update=_redraw_update,
    )
    keyframe_step: IntProperty(
        name="Keyframe Every",
        description="Insert a keyframe every N frames. Use 1 for an exact parabola",
        default=1,
        min=1,
        max=30,
    )


# --------------------------------------------------------------------------- #
# Viewport drawing
# --------------------------------------------------------------------------- #

_handle_view = None
_handle_px = None

# Alpha multiplier for the parts of the overlay hidden behind scene geometry.
OCCLUDED_ALPHA = 0.15


def _active_props(context):
    ob = context.object
    if ob is None:
        return None, None
    props = getattr(ob, "phys_predict", None)
    if props is None or not props.show_preview:
        return None, None
    return ob, props


# Edge connectivity of Blender's 8-corner bound_box, for the ghost fallback.
_BBOX_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0),
               (4, 5), (5, 6), (6, 7), (7, 4),
               (0, 4), (1, 5), (2, 6), (3, 7))


def _ghost_segments(ob, matrix, context):
    """Line segments outlining ``ob`` placed at ``matrix``.

    Uses the evaluated-mesh wireframe when the object can produce a mesh,
    otherwise falls back to the bounding box (works for any object type).
    Returns a flat list of vertex tuples for a ``'LINES'`` batch.
    """
    coords = []
    ob_eval = None
    me = None
    try:
        depsgraph = context.evaluated_depsgraph_get()
        ob_eval = ob.evaluated_get(depsgraph)
        me = ob_eval.to_mesh()
    except (RuntimeError, AttributeError):
        me = None

    if me is not None and len(me.edges) > 0:
        verts = [matrix @ v.co for v in me.vertices]
        for e in me.edges:
            a, b = e.vertices
            coords.append(verts[a].to_tuple())
            coords.append(verts[b].to_tuple())
        ob_eval.to_mesh_clear()
        return coords

    if ob_eval is not None and me is not None:
        ob_eval.to_mesh_clear()

    corners = [matrix @ Vector(c) for c in ob.bound_box]
    for a, b in _BBOX_EDGES:
        coords.append(corners[a].to_tuple())
        coords.append(corners[b].to_tuple())
    return coords


def _draw_geometry():
    context = bpy.context
    ob, props = _active_props(context)
    if ob is None:
        return

    p0 = ob.matrix_world.translation.copy()
    v0 = Vector(props.velocity)
    t_end = max(props.prediction_time, 1e-6)

    draw_pts, sampler = build_trajectory(p0, v0, props, t_end, _drag_k(props, ob))
    pts = [p.to_tuple() for p in draw_pts]
    marker_vec = sampler(t_end)

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # Build the drawables: (batch, base_color, line_width). Points use a
    # line_width of 0 (point size is set separately).
    arc = batch_for_shader(shader, 'LINE_STRIP', {"pos": pts})
    start = batch_for_shader(shader, 'POINTS', {"pos": [p0.to_tuple()]})
    drawables = [
        (arc, (1.0, 0.62, 0.12, 0.95), 2.0),
        (start, (0.95, 0.95, 0.95, 1.0), 0.0),
    ]
    if props.ghost:
        ghost_mat = ob.matrix_world.copy()
        ghost_mat.translation = marker_vec
        segs = _ghost_segments(ob, ghost_mat, context)
        if segs:
            ghost = batch_for_shader(shader, 'LINES', {"pos": segs})
            drawables.append((ghost, (0.15, 0.95, 0.35, 0.8), 1.5))
    else:
        marker = batch_for_shader(shader, 'POINTS', {"pos": [marker_vec.to_tuple()]})
        drawables.append((marker, (0.15, 0.95, 0.35, 1.0), 0.0))

    prev_blend = gpu.state.blend_get()
    prev_depth = gpu.state.depth_test_get()
    gpu.state.blend_set('ALPHA')
    gpu.state.point_size_set(11.0)
    gpu.state.depth_mask_set(False)  # test against the scene depth, don't write
    shader.bind()

    def render(alpha):
        for batch, color, width in drawables:
            if width:
                gpu.state.line_width_set(width)
            shader.uniform_float("color", (color[0], color[1], color[2], color[3] * alpha))
            batch.draw(shader)

    # Visible (in front of geometry) at full strength, occluded faded out so the
    # intersection with geometry reads as a bright-to-faint transition.
    gpu.state.depth_test_set('LESS_EQUAL')
    render(1.0)
    gpu.state.depth_test_set('GREATER')
    render(OCCLUDED_ALPHA)

    gpu.state.depth_test_set(prev_depth)
    gpu.state.depth_mask_set(True)
    gpu.state.line_width_set(1.0)
    gpu.state.point_size_set(1.0)
    gpu.state.blend_set(prev_blend)


def _draw_text():
    context = bpy.context
    ob, props = _active_props(context)
    if ob is None:
        return

    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return

    p0 = ob.matrix_world.translation.copy()
    v0 = Vector(props.velocity)
    t_end = max(props.prediction_time, 1e-6)
    _, sampler = build_trajectory(p0, v0, props, t_end, _drag_k(props, ob))
    marker = sampler(t_end)

    co = location_3d_to_region_2d(region, rv3d, marker)
    if co is None:
        return

    fps = scene_fps(context.scene)
    frame = context.scene.frame_current + round(props.prediction_time * fps)
    text = "t={:.2f}s  frame {}".format(props.prediction_time, frame)

    ui_scale = context.preferences.system.ui_scale
    font_id = 0
    blf.size(font_id, 14.0 * ui_scale)
    blf.color(font_id, 0.15, 0.95, 0.35, 1.0)
    blf.position(font_id, co.x + 12.0 * ui_scale, co.y + 12.0 * ui_scale, 0.0)
    blf.draw(font_id, text)


# --------------------------------------------------------------------------- #
# Velocity gizmo (draggable handle in the viewport)
# --------------------------------------------------------------------------- #

def _sphere_shape(radius=1.0, segs=16, rings=8):
    """Triangle-soup vertices for a small UV sphere, used as the handle shape."""
    def p(i, j):
        theta = math.pi * j / rings
        phi = 2.0 * math.pi * i / segs
        st = math.sin(theta)
        return (radius * st * math.cos(phi),
                radius * st * math.sin(phi),
                radius * math.cos(theta))
    verts = []
    for j in range(rings):
        for i in range(segs):
            a, b = p(i, j), p(i + 1, j)
            c, d = p(i + 1, j + 1), p(i, j + 1)
            # Outward-facing (CCW) winding so back-face culling renders solid.
            verts += [a, c, b, a, d, c]
    return verts


class PHYS_GT_velocity_handle(Gizmo):
    """Draggable velocity handle.

    Dragging moves the handle in the view plane through the object origin,
    setting the velocity (or, when speed is locked, just the direction).
    The scroll wheel during the drag scrubs the prediction time.
    """
    bl_idname = "PHYS_GT_velocity_handle"

    def _props(self, context):
        return context.object.phys_predict

    def _origin(self, context):
        return context.object.matrix_world.translation.copy()

    def _scale(self, context):
        return max(self._props(context).display_scale, 1e-4)

    def handle_position(self, context):
        return self._origin(context) + Vector(self._props(context).velocity) * self._scale(context)

    def setup(self):
        if not hasattr(self, "custom_shape"):
            self.custom_shape = self.new_custom_shape('TRIS', _sphere_shape())

    def draw(self, context):
        # Always on top and solid: depth test off so the handle isn't occluded
        # by geometry, back-face culling so the sphere reads as solid (rather
        # than a tangle of overlapping triangles).
        state = gpu.state
        prev_test = state.depth_test_get()
        state.depth_test_set('NONE')
        state.face_culling_set('BACK')
        self.draw_custom_shape(self.custom_shape)
        state.face_culling_set('NONE')
        state.depth_test_set(prev_test)

    def draw_select(self, context, select_id):
        self.draw_custom_shape(self.custom_shape, select_id=select_id)

    def invoke(self, context, event):
        p = self._props(context)
        self._start_velocity = Vector(p.velocity)
        self._start_time = p.prediction_time
        # Integrate per-event mouse deltas into the handle position so holding
        # Shift can scale movement down without jumping.
        self._handle = self.handle_position(context)
        self._last_proj = region_2d_to_location_3d(
            context.region, context.region_data,
            (event.mouse_region_x, event.mouse_region_y), self._origin(context))
        return {'RUNNING_MODAL'}

    def exit(self, context, cancel):
        if context.area is not None:
            context.area.header_text_set(None)
        if cancel:
            p = self._props(context)
            p.velocity = self._start_velocity
            p.prediction_time = self._start_time
        _tag_view3d_redraw(context)

    def _scrub(self, context, event):
        p = self._props(context)
        step = 1.0 / scene_fps(context.scene)
        if event.shift:
            step *= 0.2
        elif event.ctrl:
            step *= 5.0
        if event.type == 'WHEELDOWNMOUSE':
            step = -step
        p.prediction_time = max(0.0, p.prediction_time + step)

    def modal(self, context, event, tweak):
        p = self._props(context)

        # Scroll wheel scrubs the prediction point while dragging.
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            self._scrub(context, event)
            self._update_header(context)
            _tag_view3d_redraw(context)
            return {'RUNNING_MODAL'}

        # Move: project the mouse onto the view plane through the origin and
        # integrate the per-event delta into the handle (Shift = fine, 0.1x).
        origin = self._origin(context)
        proj = region_2d_to_location_3d(
            context.region, context.region_data,
            (event.mouse_region_x, event.mouse_region_y), origin)
        if proj is not None and self._last_proj is not None:
            factor = 0.1 if event.shift else 1.0
            self._handle = self._handle + (proj - self._last_proj) * factor
            new_vel = (self._handle - origin) / self._scale(context)
            if p.lock_speed:
                if new_vel.length > 1e-9:
                    p.velocity = new_vel.normalized() * p.locked_speed
            else:
                p.velocity = new_vel
        if proj is not None:
            self._last_proj = proj

        self._update_header(context)
        _tag_view3d_redraw(context)
        return {'RUNNING_MODAL'}

    def _update_header(self, context):
        if context.area is None:
            return
        p = self._props(context)
        fps = scene_fps(context.scene)
        frame = context.scene.frame_current + round(p.prediction_time * fps)
        context.area.header_text_set(
            "Speed {:.2f} m/s   Prediction {:.3f}s -> frame {}   "
            "[Scroll] scrub time   [Shift] fine   [Ctrl] coarse".format(
                Vector(p.velocity).length, p.prediction_time, frame))


class PHYS_GGT_velocity(GizmoGroup):
    bl_idname = "PHYS_GGT_velocity"
    bl_label = "Velocity"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob is not None and getattr(ob, "phys_predict", None) is not None \
            and ob.phys_predict.show_preview

    def setup(self, context):
        gz = self.gizmos.new(PHYS_GT_velocity_handle.bl_idname)
        gz.color = 1.0, 0.45, 0.1
        gz.alpha = 0.7
        gz.color_highlight = 1.0, 0.6, 0.25
        gz.alpha_highlight = 1.0
        gz.scale_basis = 0.16
        gz.use_draw_modal = True
        self.handle = gz

    def refresh(self, context):
        self.handle.matrix_basis = Matrix.Translation(self.handle.handle_position(context))


# --------------------------------------------------------------------------- #
# Operators
# --------------------------------------------------------------------------- #

class PHYS_OT_scrub(Operator):
    bl_idname = "phys.scrub_time"
    bl_label = "Scrub Prediction"
    bl_description = ("Scroll the mouse wheel to move the prediction point in time "
                      "(Shift = fine, Ctrl = coarse). Click or Enter to confirm, Esc to cancel")

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Run this from the 3D Viewport")
            return {'CANCELLED'}
        ob = context.object
        if ob is None:
            self.report({'WARNING'}, "No active object")
            return {'CANCELLED'}
        ob.phys_predict.show_preview = True
        self._initial = ob.phys_predict.prediction_time
        self._update_header(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _frame_step(self, context):
        return 1.0 / scene_fps(context.scene)

    def _update_header(self, context):
        props = context.object.phys_predict
        fps = scene_fps(context.scene)
        frame = context.scene.frame_current + round(props.prediction_time * fps)
        context.area.header_text_set(
            "Prediction: {:.3f}s  -> frame {}     "
            "[Scroll] adjust   [Shift] fine   [Ctrl] coarse   "
            "[Enter/Click] confirm   [Esc] cancel".format(props.prediction_time, frame)
        )

    def _finish(self, context):
        if context.area is not None:
            context.area.header_text_set(None)
        _tag_view3d_redraw(context)

    def modal(self, context, event):
        props = context.object.phys_predict

        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            mult = 0.2 if event.shift else (5.0 if event.ctrl else 1.0)
            delta = self._frame_step(context) * mult
            if event.type == 'WHEELDOWNMOUSE':
                delta = -delta
            props.prediction_time = max(0.0, props.prediction_time + delta)
            self._update_header(context)
            _tag_view3d_redraw(context)
            return {'RUNNING_MODAL'}

        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._finish(context)
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            props.prediction_time = self._initial
            self._finish(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}


class PHYS_OT_apply(Operator):
    bl_idname = "phys.apply_prediction"
    bl_label = "Apply as Keyframes"
    bl_description = ("Insert location keyframes along the predicted trajectory, "
                      "starting at the current frame")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        ob = context.object
        props = ob.phys_predict
        scene = context.scene
        fps = scene_fps(scene)

        start_frame = scene.frame_current
        p0 = ob.matrix_world.translation.copy()
        v0 = Vector(props.velocity)
        t_end = props.prediction_time

        if t_end <= 0.0:
            self.report({'WARNING'}, "Prediction time is zero; nothing to bake")
            return {'CANCELLED'}

        if ob.parent is not None:
            self.report(
                {'WARNING'},
                "Object is parented: keyframes are written in world space and may not "
                "match the parent's transform.",
            )

        end_frame = start_frame + round(t_end * fps)
        step = max(int(props.keyframe_step), 1)
        frames = list(range(start_frame, end_frame + 1, step))
        if not frames or frames[-1] != end_frame:
            frames.append(end_frame)

        if _has_location_keyframes(ob, start_frame, end_frame):
            self.report(
                {'WARNING'},
                "Object already has location keyframes between frames {}-{}; "
                "the baked path is mixed with them.".format(start_frame, end_frame),
            )

        _, sampler = build_trajectory(p0, v0, props, t_end, _drag_k(props, ob))
        for fr in frames:
            t = (fr - start_frame) / fps
            world = sampler(t)
            if ob.parent is not None:
                mw = ob.matrix_world.copy()
                mw.translation = world
                ob.matrix_world = mw
            else:
                # location excludes delta_location, but the world-space target
                # (and p0) include it, so compensate to land at the right spot.
                ob.location = world - ob.delta_location
            ob.keyframe_insert(data_path="location", frame=fr)

        # Snap evaluation back to the start so the object sits at p0 again.
        scene.frame_set(start_frame)
        self.report(
            {'INFO'},
            "Inserted {} location keyframes (frames {}-{}).".format(
                len(frames), start_frame, end_frame),
        )
        return {'FINISHED'}


# --------------------------------------------------------------------------- #
# UI panel
# --------------------------------------------------------------------------- #

class PHYS_PT_panel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PhysAnim"
    bl_label = "PhysAnim"

    def draw(self, context):
        layout = self.layout
        ob = context.object

        if ob is None:
            layout.label(text="Select an object", icon='INFO')
            return

        props = ob.phys_predict

        row = layout.row(align=True)
        row.prop(props, "show_preview", toggle=True, icon='HIDE_OFF')
        sub = row.row(align=True)
        sub.active = props.show_preview
        sub.prop(props, "ghost", text="", toggle=True, icon='GHOST_ENABLED')

        col = layout.column(align=True)
        col.enabled = not props.lock_speed
        col.prop(props, "velocity")

        row = layout.row(align=True)
        row.prop(props, "lock_speed", text="",
                 icon='LOCKED' if props.lock_speed else 'UNLOCKED')
        if props.lock_speed:
            row.prop(props, "locked_speed", text="Launch Speed")
        else:
            row.label(text="Launch speed: {:.2f} m/s".format(Vector(props.velocity).length))

        col = layout.column(align=True)
        col.prop(props, "gravity")

        box = layout.box()
        box.prop(props, "drag_enabled")
        if props.drag_enabled:
            box.prop(props, "mass")
            box.prop(props, "cd_preset")
            row = box.row()
            row.enabled = props.cd_preset == 'CUSTOM'
            row.prop(props, "drag_cd")
            box.prop(props, "auto_cross_section")
            if props.auto_cross_section:
                box.label(text="Area: {:.3f} m²".format(_auto_cross_section(ob)))
            else:
                box.prop(props, "cross_section")
            box.prop(props, "air_density")
            k = _drag_k(props, ob)
            a = Vector(props.gravity)
            if k > 1e-9 and a.length > 1e-9:
                box.label(text="Terminal speed: {:.1f} m/s".format((a.length / k) ** 0.5))

        box = layout.box()
        box.prop(props, "bounce_enabled")
        if props.bounce_enabled:
            box.prop(props, "ground_height")
            box.prop(props, "restitution", slider=True)

        layout.prop(props, "prediction_time")

        fps = scene_fps(context.scene)
        frame = context.scene.frame_current + round(props.prediction_time * fps)
        layout.label(text="Predicted frame: {}".format(frame), icon='TIME')

        row = layout.row()
        row.scale_y = 1.2
        row.operator("phys.scrub_time", icon='MOUSE_MMB')

        box = layout.box()
        box.label(text="Display", icon='HIDE_OFF')
        box.prop(props, "display_scale")
        box.prop(props, "resolution")

        layout.separator()
        col = layout.column(align=True)
        col.prop(props, "keyframe_step")
        col.scale_y = 1.3
        col.operator("phys.apply_prediction", icon='KEYTYPE_KEYFRAME_VEC')


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #

classes = (
    PHYS_PG_props,
    PHYS_OT_scrub,
    PHYS_OT_apply,
    PHYS_PT_panel,
    PHYS_GT_velocity_handle,
    PHYS_GGT_velocity,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.phys_predict = PointerProperty(type=PHYS_PG_props)

    global _handle_view, _handle_px
    _handle_view = bpy.types.SpaceView3D.draw_handler_add(
        _draw_geometry, (), 'WINDOW', 'POST_VIEW')
    _handle_px = bpy.types.SpaceView3D.draw_handler_add(
        _draw_text, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle_view, _handle_px
    if _handle_view is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_view, 'WINDOW')
        _handle_view = None
    if _handle_px is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_px, 'WINDOW')
        _handle_px = None

    del bpy.types.Object.phys_predict
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
