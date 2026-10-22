"""Floor drops: no specks and a smooth rim. The specks lay on cells of (sideways, distance) around each drop, so
they formed rings, and their hard hash threshold flickered as the floor's reconstructed depth wobbled from
frame to frame. Usage: python drip_fix.py <view_effects.inl> (CRLF)"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
pairs = [
    ("""    // Drops of blood on the first upward surface 20..200 cm below where they fell from: a round drop
    // with a ragged rim and a few specks, bright and wet at first, dark brown once dry.""",
     """    // Drops of blood on the first upward surface 20..200 cm below where they fell from: a round drop with a
    // softly uneven rim, bright and wet at first, dark brown once dry. Smooth everywhere: no hard thresholds,
    // which flicker as the floor's depth wobbles from frame to frame."""),
    ("""        if (r > radius * 3.0) continue;""", """        if (r > radius * 1.3) continue;"""),
    ("""        float rim = 0.85 + 0.3 * woundHash(floor(atan(spread.z, spread.x) * 3.0) + D.x * 0.37);
        float drop = 1.0 - smoothstep(0.8, 1.0, r / (radius * rim));
        vec2 cell = floor(vec2(dot(spread, normalize(cross(worldUp.xyz, vec3(0.0, 0.0, 1.0)))), r) * 0.9);
        float speck = step(0.93, woundHash(cell.x * 17.0 + cell.y * 59.0 + D.y * 0.71)) * (1.0 - smoothstep(radius, radius * 3.0, r));
        float m = max(drop, speck * 0.8);""", """        float angle = atan(spread.z, spread.x);
        float rim = 1.0 + 0.1 * sin(angle * 5.0 + D.x * 0.37) + 0.05 * sin(angle * 11.0 - D.y * 0.53);
        float m = 1.0 - smoothstep(0.7, 1.0, r / (radius * rim));"""),
]
for old, new in pairs:
    assert t.count(old) == 1, (old[:70], t.count(old))
    t = t.replace(old, new)
p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("ok")
