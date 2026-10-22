"""Offline check on the game's own body model (Resource.rpk humanbase.rfc): for every key of every ground
clip, the hips and chest face the floor or forward (never up), and the face looks forward (not at the sky,
not straight at the floor). "Front" is taken from the standing Idle pose, whose toes and face point +Z.
    python -I check_facing.py <tools/exanimate> <game folder> <spliced humanoid.rsq>"""
import math
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import rfc, rpk, rsq  # noqa: E402

GAME = Path(sys.argv[2])
seq = rsq.parse(Path(sys.argv[3]).read_bytes())
model = rfc.parse(rpk.read(GAME / "Resource.rpk", "humanbase.rfc"), "humanbase")


def verts(track, key, part):
    posed = rsq.pose_model(seq, model, track, key)
    xf = rfc.world_transforms(posed)
    n = next(n for n in posed.nodes if n.name == part)
    P, _, _ = rfc.render_vertices(rfc.drawable(posed, n))
    return [rfc.apply(xf[n.index], p) for p in P]


idle = seq.resolve(seq.sets[0], seq.clip_index("Idle"))
front = {}
for part in ("01Pelvis", "09Chest", "10Head", "04RFoot"):
    W = verts(idle, 0, part)
    front[part] = max(range(len(W)), key=lambda i: W[i][2])   # the most forward vertex standing
toes = verts(idle, 0, "04RFoot")


def vm(v, m):  # row vector times a row-major 3x3, as the file
    return [sum(v[i] * m[i * 3 + j] for i in range(3)) for j in range(3)]


_Ri = rsq.pose_transforms(seq, idle, 0)[10][0]
EARS = vm([1, 0, 0], [_Ri[j * 3 + i] for i in range(3) for j in range(3)])   # the standing ear line, neck frame
assert max(w[2] for w in toes) - min(w[2] for w in toes) > 15, "standing feet should point along z"


def facing(track, key, part):
    W = verts(track, key, part)
    c = [sum(w[i] for w in W) / len(W) for i in range(3)]
    v = [W[front[part]][i] - c[i] for i in range(3)]
    l = math.sqrt(sum(x * x for x in v)) or 1
    return [x / l for x in v]


failures = 0
for index in range(48, len(seq.clips)):
    track = seq.sets[0].tracks[index]
    T0 = rsq.pose_transforms(seq, track, 0)
    spine = [T0[9][1][0] - T0[1][1][0], 0.0, T0[9][1][2] - T0[1][1][2]]
    l = math.sqrt(sum(x * x for x in spine))
    forward = [x / l for x in spine]
    for key in range(len(track.times)):
        hips, chest, face = (facing(track, key, p) for p in ("01Pelvis", "09Chest", "10Head"))
        ears = vm(EARS, rsq.pose_transforms(seq, track, key)[10][0])   # head tipped toward a shoulder?
        tilt = abs(ears[1])
        look_forward = sum(face[i] * forward[i] for i in range(3))
        # Hips face down, not on their side: the captured crawl rolls them up to about 80 degrees from flat.
        ok = hips[1] < -0.15 and chest[1] < 0.2 and look_forward > 0.5 and -0.5 < face[1] < 0.7 and tilt < 0.26
        print(f"{seq.clips[index].name:13} key {key}: hips y {hips[1]:+.2f}, chest y {chest[1]:+.2f}, "
              f"face forward {look_forward:+.2f} y {face[1]:+.2f}, ear tilt {math.degrees(math.asin(min(1, tilt))):4.1f} deg {'ok' if ok else 'WRONG'}")
        failures += not ok
sys.exit(1 if failures else 0)
