"""view_effects.inl woundMarks (CRLF): an outer layer (cloth, padding, armour) shows a torn slit with frayed
edges and blood soaking out through it; plate-grey surfaces only take smears and runs; bruises stay
on skin. Usage: cloth_soak.py <excamera root>"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "src" / "mod" / "view_effects.inl"
t = p.read_bytes().decode("utf-8")


def sub(old, new):
    global t
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert t.count(old) == 1, (old[:70], t.count(old))
    t = t.replace(old, new)


sub("""    vec3 tint = vec3(1.0);
    float wet = 0.0;
    for (int i = 0; i < 12; ++i) {
        if (float(i) >= woundCount) break;""", """    vec3 tint = vec3(1.0);
    float wet = 0.0;
    // A grey, unsaturated surface is taken for metal: it takes blood smears and runs but no tear or soak.
    vec3 base = toLight(color);
    float brightest = max(base.r, max(base.g, base.b)), darkest = min(base.r, min(base.g, base.b));
    float grey = 1.0 - smoothstep(0.08, 0.2, (brightest - darkest) / max(brightest, 1e-4));
    for (int i = 0; i < 12; ++i) {
        if (float(i) >= woundCount) break;""")
sub("""        // Only the surface at the wound: something a few cm off it (another limb, a wall behind) is left alone.
        float stick = 1.0 - smoothstep(2.0, 4.5, abs(dot(d, n)));""", """        // The hit point lies on the body, so a surface well in front of it along its normal is an outer
        // layer: cloth, padding or armour (inferred from geometry; a loose collision shape can blur it).
        float off = dot(d, n);
        float layer = smoothstep(0.6, 1.6, off);
        float metal = layer * grey, cloth = layer * (1.0 - grey);
        // Only the surface at the wound: something a few cm off it (another limb, a wall behind) is left alone.
        float stick = 1.0 - smoothstep(2.0 + 2.5 * layer, 4.5 + 2.5 * layer, abs(off));""")
sub("""            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick;""",
    """            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick * (1.0 - layer); // skin only""")
sub("""        cut = mix(cut, mix(vec3(0.5, 0.035, 0.03), vec3(0.07, 0.003, 0.003), 1.0 - smoothstep(0.0, 0.8, x)), inside);
""", """        cut = mix(cut, mix(vec3(0.5, 0.035, 0.03), vec3(0.07, 0.003, 0.003), 1.0 - smoothstep(0.0, 0.8, x)), inside);
        // Through cloth or padding: a ragged slit with frayed threads at its edge and the dark wound behind,
        // and blood soaking outward through the weave, wider the longer the wound bleeds, with a dried rim.
        float rag = 0.35 * (woundHash(floor(q.x * 3.0) + seed * 17.0) - 0.5);
        float xs = abs(q.y - wobble) / max(C.z * 0.7 * taper, 0.05) + rag;
        float slit = taper > 0.0 ? 1.0 - smoothstep(0.5, 0.9, xs) : 0.0;
        float fray = taper * smoothstep(0.8, 1.0, xs) * (1.0 - smoothstep(1.0, 1.9, xs)) *
                     step(0.45, fract(q.x * 2.5 + woundHash(floor(q.x * 2.5) + seed)));
        float spread = A.w * 0.5 + C.z * 2.0 + C.w * 0.45;
        float e = length(vec2(q.x / (A.w * 1.1 + C.w * 0.2), q.y / spread)) *
                  (0.8 + 0.4 * woundHash(floor(q.x * 0.8) + floor(q.y * 0.8) * 13.0 + seed * 7.0));
        float soak = (1.0 - smoothstep(0.75, 1.0, e)) * (0.5 + 0.5 * severity);
        float tide = smoothstep(0.7, 0.9, e) * (1.0 - smoothstep(0.9, 1.0, e));
        vec3 stain = mix(vec3(0.42, 0.16, 0.12), vec3(0.5, 0.07, 0.06), aux);
        vec3 fabric = mix(vec3(1.0), stain, soak * 0.85);
        fabric = mix(fabric, stain * 0.7, tide * 0.5);
        fabric = mix(fabric, fabric * 0.65, fray);
        fabric = mix(fabric, vec3(0.1, 0.02, 0.02), slit);
        vec3 plate = mix(vec3(1.0), blood * 1.6, smear * 0.6);
        cut = mix(cut, fabric, cloth);
        cut = mix(cut, plate, metal);
        inside = mix(inside, slit, cloth) * (1.0 - metal);
""")
sub("""            cut = mix(cut, blood, run * 0.9);""", """            cut = mix(cut, blood, run * 0.9 * (1.0 - 0.7 * cloth)); // cloth drinks most of it""")
sub("""        wet += (inside * (0.5 + 0.5 * severity) + 0.6 * run) * stick * (0.15 + 0.85 * aux);""",
    """        wet += (inside * (0.5 + 0.5 * severity) + 0.6 * run) * stick * (0.15 + 0.85 * aux) * (1.0 - 0.6 * cloth);""")
p.write_bytes(t.encode("utf-8"))
print("ok")
