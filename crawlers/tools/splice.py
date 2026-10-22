"""The splice the addon does in Lua (scripts/rsq_splice.lua), in Python for the offline check: humanoid.rsq
plus clips.bin. New clip names go after the file's own; the first set (Default, the root every other set
inherits from) gets the new tracks, every other set an empty entry (an i32 0) for each."""
import struct

TAG_CLIPS = 0x3DAB
BONE_STRIDE = 20


def splice(data: bytes, blob: bytes) -> bytes:
    count = struct.unpack_from("<I", blob, 0)[0]
    p, names, tracks = 4, [], []
    for _ in range(count):
        names.append(blob[p:p + 24])
        p += 24
        n = struct.unpack_from("<i", blob, p)[0]
        size = 8 + n * 4 + n * 12 + n * 18 * BONE_STRIDE
        tracks.append(blob[p:p + size])
        p += size
    out, q = bytearray(), 0
    while q < len(data):
        tag, size = struct.unpack_from("<II", data, q)
        body = data[q + 8:q + 8 + size]
        if tag == TAG_CLIPS:
            nb, nc, ns = struct.unpack_from("<III", body, 0)
            r = 12 + nc * 24
            new = bytearray(struct.pack("<III", nb, nc + count, ns)) + body[12:r] + b"".join(names)
            for s in range(ns):
                start = r
                r += 32
                for _ in range(nc):
                    n = struct.unpack_from("<i", body, r)[0]
                    r += 4 if n < 1 else 8 + n * 4 + n * 12 + n * nb * BONE_STRIDE
                new += body[start:r] + (b"".join(tracks) if s == 0 else struct.pack("<i", 0) * count)
            assert r == len(body)
            body = bytes(new)
        out += struct.pack("<II", tag, len(body)) + body
        q += 8 + size
    return bytes(out)
