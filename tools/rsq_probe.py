"""Read-only: which of the game's clips lie face down. For key 0 (and the last key) of each clip in the
Default set, the spine's direction and the chest's facing in model space (+Y up, standing faces +Z or -Z,
measured from Walk). Usage: python -I rsq_probe.py <tools/exanimate> <game>"""
import math
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import rpk, rsq  # noqa: E402

seq = rsq.parse(rpk.read(Path(sys.argv[2]) / "Resource.rpk", "humanoid.rsq"))
default = seq.sets[0]


def pos(t):
    return t[1]


def vec(a, b):
    return [b[i] - a[i] for i in range(3)]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(v):
    l = math.sqrt(sum(x * x for x in v)) or 1
    return [round(x / l, 2) for x in v]


def frame(track, key):
    T = rsq.pose_transforms(seq, track, key)
    pelvis, thorax = pos(T[1]), pos(T[9])
    rs, ls = pos(T[12]), pos(T[15])          # humerus heads: right, left
    spine = norm(vec(pelvis, thorax))
    chest = norm(cross(vec(ls, rs), vec(pelvis, thorax)))  # facing, by the right-hand rule
    return spine, chest, [round(x) for x in pelvis]


for ci, clip in enumerate(seq.clips):
    t = seq.resolve(default, ci)
    if not t:
        continue
    s0, c0, p0 = frame(t, 0)
    s1, c1, p1 = frame(t, len(t.times) - 1)
    print(f"{ci:2} {clip.name:16} keys {len(t.times):3} ticks {t.times[-1]:6.0f}  first spine {s0} chest {c0} pelvis {p0}  last spine {s1} chest {c1}")
