"""Authors the ground clips for downed undead and writes them as this mod's own data (scripts/clips.bin),
never a copy of the game's file. The addon splices them into the installed humanoid.rsq when the game
reads it (levels.serve).

Clips, posed on the game's own lying face-down pose (Unconscious 2, key 0: chest to the ground, head
forward), with only the arms animated:
- "Ground Crawl" (loops): one arm reaches past the head and plants, the other pulls back to the body,
  then they swap: a drag along the floor.
- "Ground Grab": both arms reach forward and up, close, and pull back hard to the chest.
- "Ground Swipe": the right arm sweeps along the floor from beside the hip to across the front.

Each hand is placed on a target point (on the floor, or lifted) and the arm solved by two-bone IK
with the elbow up and out; each bone's direction is then set in model space from the lying pose (the
shortest arc in the parent's frame), so it holds whatever the bones' local axes are. The fifth float per bone is copied from the lying pose.

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
base = seq.resolve(default, seq.clip_index("Unconscious 2"))
BASE_KEY = [list(b) for b in base.bones[0]]
BASE_ROOT = tuple(base.root[0])
by_index = {n.index: n for n in seq.bones}


def norm(v):
    l = math.sqrt(sum(x * x for x in v))
    return [x / l for x in v]


def add(*vs):
    return [sum(v[i] for v in vs) for i in range(3)]


def scale(v, s):
    return [x * s for x in v]


def rowmul(v, m):  # row vector times a row-major 3x3
    return [v[0] * m[0] + v[1] * m[3] + v[2] * m[6], v[0] * m[1] + v[1] * m[4] + v[2] * m[7], v[0] * m[2] + v[1] * m[5] + v[2] * m[8]]


def transpose(m):
    return (m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8])


def arc(a, b):
    """The quaternion (x, y, z, w) of the shortest rotation taking unit a onto unit b."""
    c = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    d = sum(a[i] * b[i] for i in range(3))
    if d < -0.9999:
        axis = norm([0.0, -a[2], a[1]] if abs(a[0]) < 0.9 else [-a[2], 0.0, a[0]])
        return (axis[0], axis[1], axis[2], 0.0)
    q = (c[0], c[1], c[2], 1.0 + d)
    l = math.sqrt(sum(x * x for x in q))
    return tuple(x / l for x in q)


def transforms(key):
    track = rsq.Track(0, [0.0], [BASE_ROOT], [[tuple(b) for b in key]])
    return rsq.pose_transforms(seq, track, 0)


def solve(key, bone, child, direction):
    """Set bone's local rotation so its offset to child points along `direction` (model space)."""
    T = transforms(key)
    parent = by_index[bone].parent
    rp = T[parent][0]
    a = norm(list(by_index[child].translation))
    b = norm(rowmul(norm(direction), transpose(rp)))
    q = arc(a, b)
    rot = rsq.quat_to_rot(q)
    if sum(x * y for x, y in zip(rowmul(a, rot), b)) < 0.999:  # the library's matrix is the other convention
        q = (-q[0], -q[1], -q[2], q[3])
    key[bone - 1] = [q[0], q[1], q[2], q[3], key[bone - 1][4]]


# The lying body's frame, from the pose itself.
T0 = transforms(BASE_KEY)
P = lambda i: list(T0[i][1])  # noqa: E731
FORWARD = norm(add(P(9), scale(P(1), -1)))          # pelvis to thorax: where the head is
RIGHT = norm(add(P(12), scale(P(15), -1)))          # left humerus head to right
DOWN = [0.0, -1.0, 0.0]
UP = [0.0, 1.0, 0.0]
BACK = scale(FORWARD, -1)
LEFT = scale(RIGHT, -1)
ARM = {"right": (12, 13, 17), "left": (15, 16, 18)}


def pose(right=None, left=None):
    """A key from the lying pose with each arm's (upper arm, forearm) directions."""
    key = [list(b) for b in BASE_KEY]
    for side, dirs in (("right", right), ("left", left)):
        if not dirs:
            continue
        humerus, forearm, hand = ARM[side]
        solve(key, humerus, forearm, dirs[0])
        solve(key, forearm, hand, dirs[1])
    return key


# Hands are placed, not aimed: each arm reaches a target point (the floor is y = 0 under the lying body,
# the hand bone sits 3 cm above it) and the elbow bends out and a little up, two-bone IK, so the hands
# land on the floor instead of through it.
FLOOR_HAND = 3.0
L_UPPER = math.sqrt(sum(x * x for x in by_index[13].translation))
L_FORE = math.sqrt(sum(x * x for x in by_index[17].translation))


def at(side, forward=0.0, out=0.0, up=0.0, floor=True):
    """A hand target relative to that side's shoulder: cm forward (toward the head), outward, and up
    (absolute height above the floor when floor is set)."""
    s = P(12 if side == "right" else 15)
    o = RIGHT if side == "right" else LEFT
    p = add(s, scale(FORWARD, forward), scale(o, out))
    p[1] = FLOOR_HAND + up if floor else p[1] + up
    return p


def ik(side, hand):
    s = P(12 if side == "right" else 15)
    to = add(hand, scale(s, -1))
    dist = math.sqrt(sum(x * x for x in to))
    dist = max(min(dist, L_UPPER + L_FORE - 0.5), abs(L_UPPER - L_FORE) + 0.5)
    u = norm(to)
    bend = add(scale(UP, 0.45), RIGHT if side == "right" else LEFT)  # mostly outward, a little up
    v = add(bend, scale(u, -sum(bend[i] * u[i] for i in range(3))))
    v = norm(v)
    a = (L_UPPER ** 2 - L_FORE ** 2 + dist ** 2) / (2 * dist)
    h = math.sqrt(max(L_UPPER ** 2 - a * a, 0.0))
    elbow = add(s, scale(u, a), scale(v, h))
    return add(elbow, scale(s, -1)), add(add(s, scale(u, dist)), scale(elbow, -1))


def pose(right=None, left=None):
    """A key from the lying pose with each hand at its target."""
    key = [list(b) for b in BASE_KEY]
    for side, hand in (("right", right), ("left", left)):
        if hand is None:
            continue
        humerus, forearm, tip = ARM[side]
        upper, fore = ik(side, hand)
        solve(key, humerus, forearm, upper)
        solve(key, forearm, tip, fore)
    return key


reach_r, reach_l = at("right", 44, 8), at("left", 44, 8)
pull_r, pull_l = at("right", 4, 22), at("left", 4, 22)
raised_r, raised_l = at("right", 42, 4, 26), at("left", 42, 4, 26)
clutch_r, clutch_l = at("right", 40, -6, 10), at("left", 40, -6, 10)
chest_r, chest_l = at("right", 12, -6, 8), at("left", 12, -6, 8)
side_r = at("right", -12, 44)
front_r = at("right", 44, 8)
across_r = at("right", 30, -36)
brace_l = at("left", 34, 16)

# (name, flags, [(ticks, key)]); 1 loops. Ticks: 83 a second.
CLIPS = [
    ("Ground Crawl", 1, [(0, pose(reach_r, pull_l)), (45, pose(pull_r, reach_l)), (90, pose(reach_r, pull_l))]),
    ("Ground Grab", 0, [(0, pose(pull_r, pull_l)), (25, pose(raised_r, raised_l)), (40, pose(clutch_r, clutch_l)),
                        (70, pose(chest_r, chest_l)), (95, pose(pull_r, pull_l))]),
    ("Ground Swipe", 0, [(0, pose(side_r, brace_l)), (14, pose(front_r, brace_l)), (26, pose(across_r, brace_l)),
                         (55, pose(side_r, brace_l))]),
]


def encode():
    out = bytearray(struct.pack("<I", len(CLIPS)))
    for name, flags, keys in CLIPS:
        assert len(name) <= 15
        out += name.encode("latin-1").ljust(16, b"\0") + struct.pack("<II", 0, 0)
        out += struct.pack("<iI", len(keys), flags)
        out += struct.pack(f"<{len(keys)}f", *[float(t) for t, _ in keys])
        for _ in keys:
            out += struct.pack("<3f", *BASE_ROOT)
        for _, key in keys:
            for b in key:
                out += struct.pack("<5f", *b)
    return bytes(out)


blob = encode()
OUT.write_bytes(blob)
print(f"{OUT}: {len(blob)} bytes, {len(CLIPS)} clips")

if CHECK:
    # Splice as the addon will, re-read with the editor's own parser, and check the solved directions.
    import importlib.util

    spec = importlib.util.spec_from_file_location("splice", Path(__file__).with_name("splice.py"))
    splice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(splice)
    data = rpk.read(GAME / "Resource.rpk", "humanoid.rsq")
    out = splice.splice(data, blob)
    s2 = rsq.parse(out)
    assert [c.name for c in s2.clips[:len(seq.clips)]] == [c.name for c in seq.clips]
    assert [c.name for c in s2.clips[len(seq.clips):]] == [c[0] for c in CLIPS]
    for i, (name, flags, keys) in enumerate(CLIPS):
        t = s2.sets[0].tracks[len(seq.clips) + i]
        assert t.flags == flags and len(t.times) == len(keys)
        for other in s2.sets[1:]:
            assert len(seq.clips) + i not in other.tracks
    for name, flags, keys in CLIPS:
        for tick, key in keys:
            T = transforms(key)
            for bone in (17, 18):
                assert T[bone][1][1] > -1.0, (name, tick, bone, T[bone][1])  # no hand through the floor
    T = transforms(CLIPS[0][2][0][1])
    gap = math.sqrt(sum((T[17][1][i] - reach_r[i]) ** 2 for i in range(3)))
    assert gap < 1.0, gap  # the IK puts the hand on its target
    print("check: splice re-reads,", len(s2.clips), "clips; hands on their targets and above the floor; other sets unchanged")
