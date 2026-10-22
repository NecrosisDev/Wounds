"""Authors the ground clips for downed undead and writes them as this mod's own data (scripts/clips.bin),
never a copy of the game's file. The addon splices them into the installed humanoid.rsq when the game
reads it (levels.serve).

Built on the game's own lying face-down pose ("Unconcious 1", key 0; "Unconscious 2" lies face up), then posed the way a body dragging
itself would be: the hips and legs stay on the floor, the back arches so the chest comes up off it and
faces forward (toward the target), the head lifts to look ahead, and the weight is on the forearms.
- "Ground Crawl" (loops): a forearm is thrown far ahead with the chest turning and rolling after it and
  the knee on that side drawn up to push, then the body is dragged up to the planted arm; then the
  other side.
- "Ground Grab": a coil (chest dropped, arms drawn back, knees up), a lunge up and out at the target's
  legs, a clutch, and a haul that slams the chest back down.
- "Ground Swipe": a wind-up twisting the chest away with the arm cocked back, then a fast low sweep across
  the front, the chest following through, on the left forearm.

Every bone change is the smallest rotation that does the job, applied on top of the bone's current
rotation (so no bone loses its twist): spine segments aimed, the neck tilted, arms by two-bone IK to hand
targets on or above the floor (y = 0 under the lying body). The fifth float per bone is copied from the
lying pose.

clips.bin: u32 count, then per clip its 24-byte name record (16-byte name, two u32 0) and its track in
the RSQ clip-chunk encoding (i32 keys, u32 flags, keys x f32 time, keys x 3 f32 root, keys x 18 x 5 f32).

    python -I make_clips.py <tools/exanimate> <game folder> <out clips.bin> [--check]
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import rpk, rsq  # noqa: E402

GAME, OUT = Path(sys.argv[2]), Path(sys.argv[3])
CHECK = "--check" in sys.argv
seq = rsq.parse(rpk.read(GAME / "Resource.rpk", "humanoid.rsq"))
default = seq.sets[0]
base = seq.resolve(default, seq.clip_index("Unconcious 1"))  # the file's own spelling; lying face down
BASE_KEY = [list(b) for b in base.bones[0]]
BASE_ROOT = tuple(base.root[0])
by_index = {n.index: n for n in seq.bones}

# ---------------------------------------------------------------- vectors and rotations (row-vector form, as the file)


def norm(v):
    l = math.sqrt(sum(x * x for x in v))
    return [x / l for x in v]


def add(*vs):
    return [sum(v[i] for v in vs) for i in range(3)]


def scale(v, s):
    return [x * s for x in v]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def vm(v, m):  # row vector times a row-major 3x3
    return [v[0] * m[0] + v[1] * m[3] + v[2] * m[6], v[0] * m[1] + v[1] * m[4] + v[2] * m[7], v[0] * m[2] + v[1] * m[5] + v[2] * m[8]]


def mm(a, b):
    return tuple(sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3)) for i in range(3) for j in range(3))


def tr(m):
    return (m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8])


def axis_angle(axis, angle):
    """Row-form rotation: v * R turns v by `angle` about `axis` (right-handed)."""
    x, y, z = norm(axis)
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    col = (t * x * x + c, t * x * y - s * z, t * x * z + s * y,
           t * x * y + s * z, t * y * y + c, t * y * z - s * x,
           t * x * z - s * y, t * y * z + s * x, t * z * z + c)
    return tr(col)


def arc(a, b):
    """Row-form rotation taking a onto b by the shortest way."""
    a, b = norm(a), norm(b)
    axis = cross(a, b)
    s = math.sqrt(dot(axis, axis))
    if s < 1e-9:
        if dot(a, b) > 0:
            return (1, 0, 0, 0, 1, 0, 0, 0, 1)
        axis = cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0])
        return axis_angle(axis, math.pi)
    return axis_angle(axis, math.atan2(s, dot(a, b)))


def to_quat(m):
    """Row-major row-form matrix -> (x, y, z, w), the inverse of rsq.quat_to_rot."""
    r00, r01, r02, r10, r11, r12, r20, r21, r22 = tr(m)  # column form
    t = r00 + r11 + r22
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = ((r21 - r12) / s, (r02 - r20) / s, (r10 - r01) / s, 0.25 * s)
    elif r00 > r11 and r00 > r22:
        s = math.sqrt(1.0 + r00 - r11 - r22) * 2
        q = (0.25 * s, (r01 + r10) / s, (r02 + r20) / s, (r21 - r12) / s)
    elif r11 > r22:
        s = math.sqrt(1.0 + r11 - r00 - r22) * 2
        q = ((r01 + r10) / s, 0.25 * s, (r12 + r21) / s, (r02 - r20) / s)
    else:
        s = math.sqrt(1.0 + r22 - r00 - r11) * 2
        q = ((r02 + r20) / s, (r12 + r21) / s, 0.25 * s, (r10 - r01) / s)
    l = math.sqrt(sum(x * x for x in q))
    return tuple(x / l for x in q)


_probe = axis_angle([0.3, 0.8, -0.5], 1.1)
assert max(abs(x - y) for x, y in zip(rsq.quat_to_rot(to_quat(_probe)), _probe)) < 1e-9, "quaternion convention"

# ---------------------------------------------------------------- posing on a key


def transforms(key, root=None):
    track = rsq.Track(0, [0.0], [root or BASE_ROOT], [[tuple(b) for b in key]])
    return rsq.pose_transforms(seq, track, 0)


def local(key, bone):
    return rsq.quat_to_rot(key[bone - 1])


def set_local(key, bone, m):
    q = to_quat(m)
    key[bone - 1] = [q[0], q[1], q[2], q[3], key[bone - 1][4]]


def aim(key, bone, child, direction):
    """Turn `bone` the least so its offset to `child` points along `direction` (model space)."""
    T = transforms(key)
    parent_world = T[by_index[bone].parent][0]
    L = local(key, bone)
    c = vm(list(by_index[child].translation), L)         # the offset now, in the parent's frame
    b = vm(norm(direction), tr(parent_world))            # where it should point, same frame
    set_local(key, bone, mm(L, arc(c, b)))


def turn(key, bone, axis, angle):
    """Turn `bone` (and all below it) by `angle` about a model-space axis."""
    T = transforms(key)
    P = T[by_index[bone].parent][0] if by_index[bone].parent in T else (1, 0, 0, 0, 1, 0, 0, 0, 1)  # the root has no parent frame
    set_local(key, bone, mm(mm(mm(local(key, bone), P), axis_angle(axis, angle)), tr(P)))


def position(key, bone):
    return list(transforms(key)[bone][1])


# The lying body's frame, from the pose itself.
_T0 = transforms(BASE_KEY)
_spine = add(list(_T0[9][1]), scale(list(_T0[1][1]), -1))
FORWARD = norm([_spine[0], 0.0, _spine[2]])                              # where the head is
UP = [0.0, 1.0, 0.0]
RIGHT = norm(cross(FORWARD, UP))
if dot(RIGHT, add(list(_T0[12][1]), scale(list(_T0[15][1]), -1))) < 0:   # the body's own right (right humerus side)
    RIGHT = scale(RIGHT, -1)
LEFT = scale(RIGHT, -1)
ARM = {"right": (12, 13, 17), "left": (15, 16, 18)}
L_UPPER = math.sqrt(sum(x * x for x in by_index[13].translation))
L_FORE = math.sqrt(sum(x * x for x in by_index[17].translation))
HAND_ABOVE_FLOOR = 3.0
# The neck as when standing (Idle), and in its own frame: the face (+Z standing), the neck's axis (up
# standing) and the ear-to-ear line (x standing).
_idle = seq.resolve(default, seq.clip_index("Idle"))
NECK_IDLE = rsq.quat_to_rot(_idle.bones[0][9])
_Ri = rsq.pose_transforms(seq, _idle, 0)[10][0]
FACE, NECK_AXIS, EARS = (vm(v, tr(_Ri)) for v in ([0, 0, 1], [0, 1, 0], [1, 0, 0]))


def ik(key, side, hand, elbow_hint):
    """Two-bone IK: the hand at `hand`, the elbow bent toward `elbow_hint` (a model-space direction)."""
    humerus, forearm, tip = ARM[side]
    s = position(key, humerus)
    to = add(hand, scale(s, -1))
    dist = math.sqrt(dot(to, to))
    dist = max(min(dist, L_UPPER + L_FORE - 0.5), abs(L_UPPER - L_FORE) + 0.5)
    u = norm(to)
    v = norm(add(elbow_hint, scale(u, -dot(elbow_hint, u))))
    a = (L_UPPER ** 2 - L_FORE ** 2 + dist ** 2) / (2 * dist)
    h = math.sqrt(max(L_UPPER ** 2 - a * a, 0.0))
    elbow = add(s, scale(u, a), scale(v, h))
    aim(key, humerus, forearm, add(elbow, scale(s, -1)))
    aim(key, forearm, tip, add(add(s, scale(u, dist)), scale(elbow, -1)))


def body(arch=40.0, lift=12.0, head=25.0, yaw=0.0, roll=0.0, hips=0.0):
    """The lying pose with the back arched: lumbar `lift` degrees, chest `arch` degrees above the floor,
    the chest turned `yaw` degrees toward the body's right and rolled `roll` degrees, the face looking
    `head` degrees above level toward the target, the hips swung `hips` degrees about the vertical."""
    key = [list(b) for b in BASE_KEY]
    if hips:
        turn(key, 1, UP, math.radians(hips))
    fwd = norm(add(scale(FORWARD, math.cos(math.radians(yaw))), scale(RIGHT, math.sin(math.radians(yaw)))))
    aim(key, 8, 9, add(scale(fwd, math.cos(math.radians(lift))), scale(UP, math.sin(math.radians(lift)))))
    aim(key, 9, 10, add(scale(fwd, math.cos(math.radians(arch))), scale(UP, math.sin(math.radians(arch)))))
    if roll:
        turn(key, 9, fwd, math.radians(roll))
    look(key, head)
    return key


def look(key, raise_by, captured=0.0):
    """The neck: straight on the chest as when standing (the lying pose has it turned so the cheek is on
    the floor), then turned on its own axis back toward the target and tipped back about its own ear-to-ear
    line until the face looks `raise_by` degrees above level. Never a roll toward a shoulder.
    With `captured` > 0 the neck already holds a captured pose: it still turns toward the target and
    levels its ears fully, but tips up only (1 - captured) of the way, so the captured nod survives."""
    share = 1.0 - captured
    passes = 3 if captured == 0 else 1
    if captured == 0:
        set_local(key, 10, NECK_IDLE)
    R = transforms(key)[10][0]
    axis = vm(NECK_AXIS, R)
    face = vm(FACE, R)
    flat = lambda v: norm(add(v, scale(axis, -dot(v, axis))))
    a, b = flat(face), flat(FORWARD)
    turn_by = math.atan2(dot(cross(a, b), axis), dot(a, b))
    reach = 1.3 if captured else 0.9                         # a neck turns about 75 degrees each way
    turn(key, 10, axis, max(-reach, min(reach, turn_by * (1.0 if captured else 0.8))))   # eyes on the target
    R = transforms(key)[10][0]
    face, ears = vm(FACE, R), vm(EARS, R)
    for _ in range(3):                                    # the neck leans against the chest's roll: ears level,
        lean = math.asin(max(-1, min(1, ears[1])))        # always fully (never scrunched to a shoulder)
        sign = 1 if dot(cross(face, ears), UP) >= 0 else -1
        turn(key, 10, face, -sign * max(-0.6, min(0.6, lean)))
        R = transforms(key)[10][0]
        face, ears = vm(FACE, R), vm(EARS, R)
    want = math.radians(raise_by)
    for _ in range(passes):                               # the tip about the ear line that levels the face
        tip = math.asin(max(-1, min(1, math.sin(want)))) - math.asin(max(-1, min(1, face[1])))
        sign = 1 if dot(cross(face, UP), ears) >= 0 else -1
        turn(key, 10, ears, sign * max(-1.2, min(1.2, tip * share)))
        R = transforms(key)[10][0]
        face, ears = vm(FACE, R), vm(EARS, R)
    if captured:
        # A neck lying forward turns the face sideways mostly by bending to the side: swing the face about
        # the vertical onto the target, then level the ears again.
        for _ in range(2):
            flat_face = norm([face[0], 0.0, face[2]])
            swing = math.atan2(dot(cross(flat_face, FORWARD), UP), dot(flat_face, FORWARD))
            turn(key, 10, UP, max(-1.0, min(1.0, swing)))
            R = transforms(key)[10][0]
            face, ears = vm(FACE, R), vm(EARS, R)
            lean = math.asin(max(-1, min(1, ears[1])))
            sign = 1 if dot(cross(face, ears), UP) >= 0 else -1
            turn(key, 10, face, -sign * max(-0.6, min(0.6, lean)))
            R = transforms(key)[10][0]
            face, ears = vm(FACE, R), vm(EARS, R)


# ---------------------------------------------------------------- the clips


LEG = {"right": (2, 3, 4), "left": (5, 6, 7)}
L_SHIN = math.sqrt(sum(x * x for x in by_index[4].translation))


def leg(key, side, w, forward=16.0, out=24.0):
    """The leg on `side` drawn up to push by `w`: 0 as it fell, 1 the knee out and forward on the floor
    with the foot behind it."""
    if w <= 0.001:
        return
    hip_bone, knee_bone, foot_bone = LEG[side]
    hip = position(key, hip_bone)
    o = RIGHT if side == "right" else LEFT
    k0 = position(key, knee_bone)
    k1 = add(hip, scale(FORWARD, forward), scale(o, out))
    k1[1] = 11.0
    aim(key, hip_bone, knee_bone, add(add(scale(k0, 1 - w), scale(k1, w)), scale(hip, -1)))
    knee = position(key, knee_bone)
    f0 = position(key, foot_bone)
    f1 = add(knee, scale(FORWARD, -L_SHIN * 0.92), scale(o, 6))
    f1[1] = 6.0
    aim(key, knee_bone, foot_bone, add(add(scale(f0, 1 - w), scale(f1, w)), scale(knee, -1)))


# Hands are placed on the floor relative to where the shoulders sit in a typical propped pose, not to
# the shoulders of each key: a planted hand stays put while the chest moves over it.
_REF = body(arch=56, lift=12, head=12)
SHOULDER = {side: position(_REF, ARM[side][0]) for side in ARM}
_rolled = body(arch=56, lift=12, head=12, roll=10)
ROLL_RIGHT = 1 if position(_rolled, 12)[1] > position(_rolled, 15)[1] else -1   # + raises the right shoulder


def hand_at(side, forward, out, up):
    o = RIGHT if side == "right" else LEFT
    p = add(SHOULDER[side], scale(FORWARD, forward), scale(o, out))
    p[1] = HAND_ABOVE_FLOOR + up
    return p


def elbow_toward(side, f, o, u):
    return add(scale(FORWARD, f), scale(RIGHT if side == "right" else LEFT, o), scale(UP, u))


PROPPED = (-0.4, 0.5, -1.0)   # a forearm on the floor: elbow down, a little back and out


def pose(p):
    """A key from numbers: spine (arch, lift, yaw toward the right, roll raising the right shoulder, hips
    swung toward the right), face `head` degrees above level, each hand at (forward, out, up) cm from its
    shoulder's floor spot with the elbow bent toward e<side>, each leg drawn up by k<side>."""
    key = body(arch=p["arch"], lift=p["lift"], head=p["head"], yaw=p["yaw"], roll=p["roll"] * ROLL_RIGHT, hips=p["hips"])
    for side in ("right", "left"):
        ik(key, side, hand_at(side, *p[side]), elbow_toward(side, *p["e" + side]))
        leg(key, side, p["k" + side])
    return key


STILL = dict(arch=56, lift=12, head=12, yaw=0, roll=0, hips=0, right=(18, 8, 0), left=(18, 8, 0),
             eright=PROPPED, eleft=PROPPED, kright=0, kleft=0)


def keyed(*frames):
    """Keyframes as (tick, changes from the previous frame); between keys more than 14 ticks apart a
    Catmull-Rom in-between is added, so the motion arcs through the keys instead of stopping at each."""
    full, p = [], dict(STILL)
    for tick, changes in frames:
        p = dict(p, **changes)
        full.append((tick, p))

    def mix(a, b, c, d, t):
        if isinstance(b, tuple):
            return tuple(mix(*(v[i] for v in (a, b, c, d)), t) for i in range(len(b)))
        return 0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3)

    out = []
    for i, (tick, p) in enumerate(full):
        out.append((tick, pose(p)))
        if i + 1 < len(full) and full[i + 1][0] - tick > 14:
            a, b, c, d = full[max(i - 1, 0)][1], p, full[i + 1][1], full[min(i + 2, len(full) - 1)][1]
            out.append(((tick + full[i + 1][0]) / 2, pose({k: mix(a[k], b[k], c[k], d[k], 0.5) for k in p})))
    return out


# ---- the crawl: Mixamo's "Zombie Crawl" motion capture (downloaded separately), retargeted onto
# the game's 18 parts by direction: each part is turned so it points where the matching captured bone
# points; the hips and head take the captured frame (hip line and spine, neck axis and face). The capture
# crawls along its own +Z; that is turned onto FORWARD (toward the target). The body is not moved here:
# the clip plays in place and the addon drags the body (characters.drift) at the capture's own speed
# (config crawl_speed). The raw download is never shipped or committed (mocap-src/ is git-ignored);
# the retargeted keys are cached beside this file so the clips rebuild without it.
import importlib.util  # noqa: E402
import json  # noqa: E402

TICKS_PER_SECOND = 1000.0 / 12.0
MOCAP = Path(__file__).resolve().parents[1] / "mocap-src" / "zombie-crawl.fbx"
MOCAP_CACHE = Path(__file__).with_name("mocap_crawl.json")
NECK_LIMIT = 35.0                    # degrees the one-piece neck may bend from straight (see limit_neck)
HEAD_KEEP = 0.35                     # how much of the captured head pose is kept over the look at the target
MOCAP_KEYS = 16                      # the most keys a clip gets: a few more than the game's own clips (10)


def _fbx():
    spec = importlib.util.spec_from_file_location("fbx_anim", Path(__file__).with_name("fbx_anim.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _basis(a, b):
    """Rows of an orthonormal basis from a primary direction `a` and a secondary `b`."""
    x = norm(a)
    z = norm(cross(x, b))
    y = cross(z, x)
    return (x, y, z)


def _rotation(local_pair, world_pair):
    """Row-form R with local_pair[i] * R along world_pair[i] (the first exactly, the second in its plane)."""
    A, B = _basis(*local_pair), _basis(*world_pair)
    return tuple(sum(A[k][i] * B[k][j] for k in range(3)) for i in range(3) for j in range(3))


def _set_world(key, bone, R):
    parent = by_index[bone].parent
    T = transforms(key)
    P = T[parent][0] if parent in T else (1, 0, 0, 0, 1, 0, 0, 0, 1)
    set_local(key, bone, mm(R, tr(P)))


def retarget(world):
    """One key from the captured bones' positions and head frame (already turned into the game's axes)."""
    P = lambda name: world[name][0]
    d = lambda a, b: add(P(b), scale(P(a), -1))
    key = [list(b) for b in BASE_KEY]
    hips_local = (add(list(by_index[2].translation), scale(list(by_index[5].translation), -1)), list(by_index[8].translation))
    _set_world(key, 1, _rotation(hips_local, (d("LeftUpLeg", "RightUpLeg"), d("Hips", "Spine"))))
    aim(key, 8, 9, d("Spine", "Spine2"))
    aim(key, 9, 10, d("Spine2", "Neck"))
    T = transforms(key)                                    # the chest's twist: the shoulder line as captured
    axis = norm(d("Spine2", "Neck"))
    flat = lambda v: norm(add(v, scale(axis, -dot(v, axis))))
    a, b = flat(add(list(T[12][1]), scale(list(T[15][1]), -1))), flat(d("LeftArm", "RightArm"))
    turn(key, 9, axis, math.atan2(dot(cross(a, b), axis), dot(a, b)))
    _set_world(key, 10, _rotation((NECK_AXIS, FACE), (d("Neck", "Head"), world["Head"][1])))
    # The captured zombie hangs its head at the floor; it keeps that sway but lifts most of the way toward
    # the target and levels its ears (the chest and eyes face the target).
    look(key, 0.0, captured=HEAD_KEEP)
    limit_neck(key, NECK_LIMIT)
    level_ears(key)                                        # cutting the bend short can tip the ears again
    limit_neck(key, NECK_LIMIT)
    for side, (shoulder, humerus, forearm, hand), cap in (("right", (11, 12, 13, 17), "Right"), ("left", (14, 15, 16, 18), "Left")):
        aim(key, shoulder, humerus, d(cap + "Shoulder", cap + "Arm"))
        aim(key, humerus, forearm, d(cap + "Arm", cap + "ForeArm"))
        aim(key, forearm, hand, d(cap + "ForeArm", cap + "Hand"))
    for (hip, knee, foot), cap in (((2, 3, 4), "Right"), ((5, 6, 7), "Left")):
        aim(key, hip, knee, d(cap + "UpLeg", cap + "Leg"))
        aim(key, knee, foot, d(cap + "Leg", cap + "Foot"))
    return key


def _capture():
    """[(seconds, {bone: (position, face)})] at 30 a second over the whole take, in the game's axes,
    plus the take's length and its speed along its own +Z."""
    fbx = _fbx()
    sk = fbx.Skeleton(MOCAP.read_bytes())
    yaw = math.atan2(FORWARD[0], FORWARD[2])               # the capture's +Z onto FORWARD
    c, s = math.cos(yaw), math.sin(yaw)
    turn_y = lambda v: [c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2]]
    frames = []
    count = int(sk.length * 30)
    for i in range(count + 1):
        t = sk.length * i / count
        W = sk.sample(t)
        frames.append((t, {n: (turn_y(fbx.position(m)), turn_y([m[0][2], m[1][2], m[2][2]])) for n, m in W.items()}))
    travel = frames[-1][1]["Hips"][0]
    start = frames[0][1]["Hips"][0]
    speed = dot(add(travel, scale(start, -1)), FORWARD) / sk.length
    return frames, sk.length, speed


def _pick_keys(frames, count):
    """The frames that keep the motion best: greedily add the frame worst predicted by blending its
    neighbouring keys (hands, feet, head and elbows relative to the hips), first and last always kept."""
    parts = ("RightHand", "LeftHand", "RightFoot", "LeftFoot", "Head", "RightForeArm", "LeftForeArm", "Spine2")
    rel = [[x for p in parts for x in add(f[p][0], scale(f["Hips"][0], -1))] for _, f in frames]
    keys = [0, len(frames) - 1]
    while len(keys) < count:
        worst, at = -1.0, None
        ks = sorted(keys)
        for a, b in zip(ks, ks[1:]):
            for i in range(a + 1, b):
                u = (i - a) / (b - a)
                e = sum((rel[i][k] - (rel[a][k] + (rel[b][k] - rel[a][k]) * u)) ** 2 for k in range(len(rel[i])))
                if e > worst:
                    worst, at = e, i
        if at is None:
            break
        keys.append(at)
    return sorted(keys)


def level_ears(key):
    R = transforms(key)[10][0]
    face, ears = vm(FACE, R), vm(EARS, R)
    lean = math.asin(max(-1, min(1, ears[1])))
    sign = 1 if dot(cross(face, ears), UP) >= 0 else -1
    turn(key, 10, face, -sign * max(-0.6, min(0.6, lean)))


def limit_neck(key, degrees):
    """The neck and head are one rigid part: bent far from straight it juts out of the chest as a lump
    Keep its bend from the standing neck within `degrees` (the capture itself stays within
    about 30), giving up the rest of the look toward the target."""
    q, n = to_quat(local(key, 10)), to_quat(NECK_IDLE)
    d = sum(a * b for a, b in zip(q, n))
    if d < 0:
        q, d = [-x for x in q], -d
    angle = 2 * math.acos(min(1.0, d))
    if angle <= math.radians(degrees):
        return
    t = math.radians(degrees) / angle                     # slerp from straight toward the look, cut short
    th = math.acos(min(1.0, d))
    w = [(math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th) for a, b in zip(n, q)]
    set_local(key, 10, rsq.quat_to_rot(tuple(x / math.sqrt(sum(y * y for y in w)) for x in w)))


def crawl_keys():
    if MOCAP.exists():
        frames, length, speed = _capture()
        picked = _pick_keys(frames, MOCAP_KEYS)
        # The root is the pelvis position (the game's Idle has it at standing hip height, the lying poses
        # near the floor); the capture's hip height goes in, the lying pose's floor spot stays.
        root = lambda f: [BASE_ROOT[0], f["Hips"][0][1], BASE_ROOT[2]]
        keys = [(round(frames[i][0] * TICKS_PER_SECOND), retarget(frames[i][1]), root(frames[i][1])) for i in picked]
        keys[-1] = (keys[-1][0], [list(b) for b in keys[0][1]], list(keys[0][2]))   # the take loops: end on the first key
        MOCAP_CACHE.write_text(json.dumps({"source": "Mixamo Zombie Crawl, retargeted by make_clips.py",
                                           "seconds": length, "speed_cm_s": speed, "keys": keys}))
        print(f"crawl: {len(keys)} keys from {length:.2f} s of capture, travel {speed:.1f} cm/s")
    data = json.loads(MOCAP_CACHE.read_text())
    return [(t, [list(b) for b in k], tuple(r)) for t, k, r in data["keys"]]


# ---- the grab: a coil (anticipation), a lunge that overshoots, a clutch, a haul down and a settle.
GRAB = keyed(
    (0, {}),
    (16, dict(arch=42, lift=6, head=20, right=(0, 16, 6), left=(0, 16, 6), eright=(-0.5, 1, 0.8), eleft=(-0.5, 1, 0.8),
              kright=0.8, kleft=0.8)),
    (26, dict(arch=82, lift=26, head=2, roll=4, right=(54, 12, 40), left=(52, 12, 36), eright=(0, 1, -0.6),
              eleft=(0, 1, -0.6), kright=0.3, kleft=0.3)),
    (32, dict(arch=84, lift=27, head=0, right=(58, 6, 36), left=(56, 6, 33))),
    (42, dict(arch=76, lift=22, head=4, roll=0, right=(46, -6, 30), left=(45, -6, 28), eright=(0, 1, -0.4),
              eleft=(0, 1, -0.4), kright=0.2, kleft=0.2)),
    (60, dict(arch=46, lift=10, head=20, right=(6, -2, 10), left=(6, -2, 10), eright=(-0.6, 1, -0.3),
              eleft=(-0.6, 1, -0.3), kright=0.4, kleft=0.4)),
    (74, dict(arch=54, lift=12, head=14, right=(16, 6, 2), left=(16, 6, 2), eright=(-0.4, 0.6, -0.8),
              eleft=(-0.4, 0.6, -0.8), kright=0.1, kleft=0.1)),
    (90, STILL),
)

# ---- the swipe: on the left forearm. A slow wind-up twisting away, a fast low sweep across the front,
# a follow-through that carries the chest past, then a recovery.
SWIPE = keyed(
    (0, dict(yaw=8, right=(16, 10, 0), left=(24, 12, 0))),
    (14, dict(yaw=34, roll=14, arch=56, hips=-4, right=(-20, 40, 14), eright=(-0.3, 1, 0.6), left=(22, 12, 0),
              kright=0.8)),
    (22, dict(yaw=4, roll=-8, arch=68, hips=2, right=(52, 22, 6), eright=(0.2, 1, 0.4), kright=0.7)),
    (28, dict(yaw=-30, roll=-18, arch=66, hips=5, right=(30, -44, 10), eright=(0.6, 0.4, 0.6), kright=0.3)),
    (36, dict(yaw=-36, roll=-20, arch=64, right=(16, -50, 8), eright=(0.5, 0.3, 0.7), kright=0.2)),
    (52, dict(yaw=-6, roll=-4, arch=60, hips=0, right=(14, 6, 4), eright=(-0.3, 0.6, -0.6), left=(24, 12, 0),
              kright=0.1)),
    (68, dict(yaw=8, roll=0, arch=56, right=(16, 10, 0), eright=PROPPED, kright=0)),
)

# (name, flags, [(ticks, key)]); 1 loops. Ticks: 83 a second.
CLIPS = [
    ("Ground Crawl", 1, crawl_keys()),
    ("Ground Grab", 0, GRAB),
    ("Ground Swipe", 0, SWIPE),
]


def encode():
    out = bytearray(struct.pack("<I", len(CLIPS)))
    for name, flags, keys in CLIPS:
        assert len(name) <= 15
        out += name.encode("latin-1").ljust(16, b"\0") + struct.pack("<II", 0, 0)
        out += struct.pack("<iI", len(keys), flags)
        out += struct.pack(f"<{len(keys)}f", *[float(k[0]) for k in keys])
        for k in keys:   # (tick, key) or (tick, key, root): the root is the pelvis position
            out += struct.pack("<3f", *(k[2] if len(k) > 2 else BASE_ROOT))
        for k in keys:
            for b in k[1]:
                out += struct.pack("<5f", *b)
    return bytes(out)


blob = encode()
OUT.write_bytes(blob)
print(f"{OUT}: {len(blob)} bytes, {len(CLIPS)} clips")

if CHECK:
    import importlib.util

    spec = importlib.util.spec_from_file_location("splice", Path(__file__).with_name("splice.py"))
    splice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(splice)
    out = splice.splice(rpk.read(GAME / "Resource.rpk", "humanoid.rsq"), blob)
    s2 = rsq.parse(out)
    assert [c.name for c in s2.clips[:len(seq.clips)]] == [c.name for c in seq.clips]
    assert [c.name for c in s2.clips[len(seq.clips):]] == [c[0] for c in CLIPS]
    for i, (name, flags, keys) in enumerate(CLIPS):
        t = s2.sets[0].tracks[len(seq.clips) + i]
        assert t.flags == flags and len(t.times) == len(keys)
        for other in s2.sets[1:]:
            assert len(seq.clips) + i not in other.tracks
    for name, flags, keys in CLIPS:
        for k in keys:
            T = transforms(k[1], k[2] if len(k) > 2 else None)
            low = min(T[b][1][1] for b in T)
            assert low > -4.0, (name, k[0], low)        # no bone centre through the floor (the lying pose itself has a hand at -2)
            assert T[10][1][1] > 10.0, (name, k[0])      # the neck off the floor (the captured crawl drops it near 15)
    print("check: splice re-reads,", len(s2.clips), "clips; neck up, nothing through the floor; other sets unchanged")
