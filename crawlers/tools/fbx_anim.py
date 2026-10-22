"""Reads the skeleton and its animation from a binary FBX (Mixamo exports), with no FBX SDK: the node
tree, the LimbNode models with their rest transforms (Lcl Translation/Rotation, PreRotation,
RotationOrder), and the AnimationCurveNodes driving them. `sample(t)` gives every bone's world matrix
(column-vector 4x4 as nested lists) at time t seconds.

Only what Mixamo writes is handled: Euler order XYZ (eEulerXYZ, R = Rz Ry Rx), PreRotation, no
rotation/scaling pivots or offsets (checked: a non-zero one fails loudly).
    python -I fbx_anim.py <file.fbx>      prints the bones, parents and the animation length"""
import math
import struct
import sys
import zlib

TICKS_PER_SECOND = 46186158000


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props, children):
        self.name, self.props, self.children = name, props, children

    def find(self, name):
        return next((c for c in self.children if c.name == name), None)

    def all(self, name):
        return [c for c in self.children if c.name == name]


def _props(data, pos, count):
    out = []
    for _ in range(count):
        t = chr(data[pos])
        pos += 1
        if t in "YCIFDL":
            fmt = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}[t]
            out.append(struct.unpack_from(fmt, data, pos)[0])
            pos += struct.calcsize(fmt)
        elif t in "fdlib":
            n, enc, clen = struct.unpack_from("<III", data, pos)
            pos += 12
            raw = data[pos:pos + clen]
            pos += clen
            if enc == 1:
                raw = zlib.decompress(raw)
            fmt = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}[t]
            out.append(list(struct.unpack(f"<{n}{fmt}", raw)))
        elif t in "SR":
            (n,) = struct.unpack_from("<I", data, pos)
            pos += 4
            v = data[pos:pos + n]
            pos += n
            out.append(v.decode("utf-8", "replace") if t == "S" else v)
        else:
            raise ValueError(f"FBX property type {t!r} at {pos - 1}")
    return out


def parse(data):
    assert data[:21] == b"Kaydara FBX Binary  \x00", "not a binary FBX"
    (version,) = struct.unpack_from("<I", data, 23)
    wide = version >= 7500
    head = "<QQQB" if wide else "<IIIB"
    hsize = struct.calcsize(head)

    def node(pos):
        end, nprops, plen, nlen = struct.unpack_from(head, data, pos)
        if end == 0:
            return None, pos + hsize
        name = data[pos + hsize:pos + hsize + nlen].decode("ascii", "replace")
        p = pos + hsize + nlen
        props = _props(data, p, nprops)
        p += plen
        children = []
        while p < end:
            child, p = node(p)
            if child is None:
                break
            children.append(child)
        return Node(name, props, children), end

    top, pos = [], 27
    while pos < len(data) - hsize:
        n, pos = node(pos)
        if n is None:
            break
        top.append(n)
    return Node("", [], top)


def _p70(model):
    out = {}
    p70 = model.find("Properties70")
    for p in (p70.children if p70 else []):
        out[p.props[0]] = p.props[4:]
    return out


def _euler_xyz(r):
    """Column-vector 3x3 for FBX eEulerXYZ (degrees): R = Rz * Ry * Rx."""
    x, y, z = (math.radians(a) for a in r)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    return mat3(mat3(Rz, Ry), Rx)


def mat3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat4(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _trs(t, r3):
    return [[r3[0][0], r3[0][1], r3[0][2], t[0]], [r3[1][0], r3[1][1], r3[1][2], t[1]],
            [r3[2][0], r3[2][1], r3[2][2], t[2]], [0, 0, 0, 1]]


class Skeleton:
    def __init__(self, data):
        root = parse(data)
        objects = root.find("Objects")
        conns = root.find("Connections")
        self.bones = {}      # id -> dict(name, parent, T, R, pre)
        curvenodes, curves = {}, {}
        for o in objects.children:
            if o.name == "Model" and o.props[2] == "LimbNode":
                p = _p70(o)
                for bad in ("RotationOffset", "RotationPivot", "ScalingOffset", "ScalingPivot", "PostRotation"):
                    assert not any(abs(v) > 1e-6 for v in p.get(bad, [0, 0, 0])), (o.props[1], bad)
                assert int((p.get("RotationOrder") or [0])[0]) == 0, (o.props[1], "rotation order")
                self.bones[o.props[0]] = dict(name=o.props[1].split("\x00")[0].replace("mixamorig:", ""), parent=None,
                                              T=list(p.get("Lcl Translation", [0, 0, 0])),
                                              R=list(p.get("Lcl Rotation", [0, 0, 0])),
                                              pre=list(p.get("PreRotation", [0, 0, 0])), curves={})
            elif o.name == "AnimationCurveNode":
                curvenodes[o.props[0]] = dict(name=o.props[1].split("\x00")[0], channels={}, model=None, prop=None)
            elif o.name == "AnimationCurve":
                curves[o.props[0]] = ([t / TICKS_PER_SECOND for t in o.find("KeyTime").props[0]], o.find("KeyValueFloat").props[0])
        for c in conns.children:
            kind, child, parent = c.props[0], c.props[1], c.props[2]
            if kind == "OO" and child in self.bones and parent in self.bones:
                self.bones[child]["parent"] = parent
            elif kind == "OP" and child in curvenodes and parent in self.bones:
                curvenodes[child]["model"], curvenodes[child]["prop"] = parent, c.props[3]
            elif kind == "OP" and child in curves and parent in curvenodes:
                curvenodes[parent]["channels"][c.props[3]] = curves[child]
        self.length = 0.0
        for cn in curvenodes.values():
            if cn["model"] in self.bones and cn["prop"] in ("Lcl Translation", "Lcl Rotation"):
                self.bones[cn["model"]]["curves"][cn["prop"]] = cn["channels"]
                for times, _ in cn["channels"].values():
                    self.length = max(self.length, times[-1])
        self.by_name = {b["name"]: i for i, b in self.bones.items()}
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            p = self.bones[i]["parent"]
            if p is not None:
                visit(p)
            seen.add(i)
            order.append(i)
        for i in self.bones:
            visit(i)
        self.order = order

    @staticmethod
    def _curve(channels, axis, default, t):
        ch = channels.get("d|" + axis)
        if not ch:
            return default
        times, values = ch
        if t <= times[0]:
            return values[0]
        if t >= times[-1]:
            return values[-1]
        lo, hi = 0, len(times) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if times[mid] <= t:
                lo = mid
            else:
                hi = mid
        f = (t - times[lo]) / (times[hi] - times[lo])
        return values[lo] + (values[hi] - values[lo]) * f

    def sample(self, t):
        """{name: column-vector 4x4 world matrix} at t seconds."""
        world = {}
        for i in self.order:
            b = self.bones[i]
            T = [self._curve(b["curves"].get("Lcl Translation", {}), a, b["T"][k], t) for k, a in enumerate("XYZ")]
            R = [self._curve(b["curves"].get("Lcl Rotation", {}), a, b["R"][k], t) for k, a in enumerate("XYZ")]
            local = _trs(T, mat3(_euler_xyz(b["pre"]), _euler_xyz(R)))
            world[i] = mat4(world[b["parent"]], local) if b["parent"] is not None else local
        return {self.bones[i]["name"]: m for i, m in world.items()}


def position(m):
    return [m[0][3], m[1][3], m[2][3]]


if __name__ == "__main__":
    from pathlib import Path
    sk = Skeleton(Path(sys.argv[1]).read_bytes())
    print(f"{len(sk.bones)} bones, {sk.length:.3f} s")
    for i in sk.order:
        b = sk.bones[i]
        parent = sk.bones[b["parent"]]["name"] if b["parent"] is not None else "-"
        print(f"  {b['name']:20} <- {parent:18} T {[round(x, 1) for x in b['T']]} pre {[round(x, 1) for x in b['pre']]} "
              f"anim {sorted(b['curves'])}")
