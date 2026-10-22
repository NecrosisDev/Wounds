"""Offline preview: each ground clip as an animated GIF of the game's own body model (Resource.rpk
humanbase.rfc, the rigid parts the skeleton moves) posed by the clip, flat shaded on a floor, seen from
in front at a target's eye line and from the side. Rotations are blended between keys as quaternions.
This shows the clip's targets: the game's physics, weight and skinning will soften them.
    python -I render_clips.py <tools/exanimate> <game folder> <spliced humanoid.rsq> <out dir>"""
import math
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import rfc, rpk, rsq  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

GAME = Path(sys.argv[2])
seq = rsq.parse(Path(sys.argv[3]).read_bytes())
OUT = Path(sys.argv[4])
OUT.mkdir(parents=True, exist_ok=True)
model = rfc.parse(rpk.read(GAME / "Resource.rpk", "humanbase.rfc"), "humanbase")
TICKS, FPS, W, H = 1000.0 / 12.0, 25, 420, 340


def slerp(a, b, t):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = [-x for x in b], -d
    if d > 0.9995:
        q = [x + (y - x) * t for x, y in zip(a, b)]
    else:
        th = math.acos(d)
        s = math.sin(th)
        q = [(math.sin((1 - t) * th) * x + math.sin(t * th) * y) / s for x, y in zip(a, b)]
    l = math.sqrt(sum(x * x for x in q))
    return [x / l for x in q]


def track_at(track, tick):
    times = track.times
    if tick >= times[-1]:
        i, t = len(times) - 2, 1.0
    else:
        i = max(k for k in range(len(times) - 1) if times[k] <= tick)
        t = (tick - times[i]) / (times[i + 1] - times[i])
    key = [tuple(slerp(track.bones[i][b][:4], track.bones[i + 1][b][:4], t)) + (0.0,) for b in range(18)]
    root = tuple(track.root[i][k] + (track.root[i + 1][k] - track.root[i][k]) * t for k in range(3))
    return rsq.Track(0, [0.0], [root], [key])


def triangles(posed):
    xf = rfc.world_transforms(posed)
    out = []
    for n in posed.nodes:
        mesh = rfc.drawable(posed, n)
        if mesh is None:
            continue
        P, _, _ = rfc.render_vertices(mesh)
        Wv = [rfc.apply(xf[n.index], p) for p in P]
        out += [(Wv[a], Wv[b], Wv[c]) for a, b, c in mesh.triangles]
    return out


def camera(eye, target):
    f = [target[i] - eye[i] for i in range(3)]
    l = math.sqrt(sum(x * x for x in f))
    f = [x / l for x in f]
    r = [-f[2], 0.0, f[0]]                       # forward x world up: the screen's right
    l = math.sqrt(sum(x * x for x in r))
    r = [x / l for x in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    if u[1] < 0:                                  # keep the world's up at the top of the image
        u = [-x for x in u]
    return eye, r, u, f


def render(tris, cam, title):
    eye, r, u, f = cam
    img = Image.new("RGB", (W, H), (22, 20, 19))
    d = ImageDraw.Draw(img)
    focal = 1.25 * W

    def proj(p):
        v = [p[i] - eye[i] for i in range(3)]
        z = sum(v[i] * f[i] for i in range(3))
        if z < 1:
            return None
        return (W / 2 + focal * sum(v[i] * r[i] for i in range(3)) / z, H * 0.55 - focal * sum(v[i] * u[i] for i in range(3)) / z, z)

    # The floor: a grid at y = 0.
    for k in range(-6, 7):
        for a, b in (((k * 25, 0, -175), (k * 25, 0, 125)), ((-150, 0, k * 25 - 25), (150, 0, k * 25 - 25))):
            pa, pb = proj(a), proj(b)
            if pa and pb:
                d.line([pa[:2], pb[:2]], fill=(52, 46, 42), width=1)
    light = [0.35, 0.85, 0.4]
    l = math.sqrt(sum(x * x for x in light))
    light = [x / l for x in light]
    faces = []
    for a, b, c in tris:
        pa, pb, pc = proj(a), proj(b), proj(c)
        if not (pa and pb and pc):
            continue
        n = [(b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])]
        nl = math.sqrt(sum(x * x for x in n)) or 1
        shade = 0.25 + 0.75 * abs(sum(n[i] / nl * light[i] for i in range(3)))
        faces.append(((pa[2] + pb[2] + pc[2]) / 3, [pa[:2], pb[:2], pc[:2]], shade))
    faces.sort(key=lambda x: -x[0])
    for _, pts, shade in faces:
        col = tuple(int(c * shade) for c in (196, 168, 148))
        d.polygon(pts, fill=col)
    d.text((8, 6), title, fill=(210, 200, 185))
    return img


def cameras(track):
    """Front: where the target stands, ahead of the head, at a standing person's eye line and a little
    to the side; side: from the body's right. From the clip's first key (the body lies at an angle)."""
    T = rsq.pose_transforms(seq, track, 0)
    pelvis, thorax, head = T[1][1], T[9][1], T[10][1]
    f = [thorax[0] - pelvis[0], 0.0, thorax[2] - pelvis[2]]
    l = math.sqrt(f[0] ** 2 + f[2] ** 2)
    f = [f[0] / l, 0.0, f[2] / l]
    r = [-f[2], 0.0, f[0]]
    if (T[12][1][0] - T[15][1][0]) * r[0] + (T[12][1][2] - T[15][1][2]) * r[2] < 0:
        r = [-r[0], 0.0, -r[2]]
    look = [head[0] - f[0] * 20, 18.0, head[2] - f[2] * 20]
    front = camera((head[0] + f[0] * 260 + r[0] * 50, 115.0, head[2] + f[2] * 260 + r[2] * 50), look)
    mid = [(pelvis[0] + head[0]) / 2, 20.0, (pelvis[2] + head[2]) / 2]
    side = camera((mid[0] + r[0] * 300, 75.0, mid[2] + r[2] * 300), mid)
    return front, side


for index in range(48, len(seq.clips)):
    name = seq.clips[index].name
    track = seq.sets[0].tracks[index]
    length = track.times[-1]
    count = max(int(length / TICKS * FPS), 2)
    frames = []
    FRONT, SIDE = cameras(track)
    for i in range(count + 1):
        posed = rsq.pose_model(seq, model, track_at(track, length * i / count), 0)
        tris = triangles(posed)
        frame = Image.new("RGB", (W * 2, H))
        frame.paste(render(tris, FRONT, f"{name}: from where its target stands"), (0, 0))
        frame.paste(render(tris, SIDE, f"{name}: from the side"), (W, 0))
        frames.append(frame)
    path = OUT / (name.lower().replace(" ", "-") + ".gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
    print(path, len(frames), "frames", f"{length / TICKS:.2f} s")
