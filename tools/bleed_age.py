"""ExCamera (CRLF files): blood that runs while the game says the character bleeds (character +0x10DC)
and dries after, and bruises that darken from red to purple. Usage: bleed_age.py <excamera root>"""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src" / "mod"


def sub(name, old, new):
    p = root / name
    t = p.read_bytes().decode("utf-8")
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert t.count(old) == 1, (name, old[:70], t.count(old))
    p.write_bytes(t.replace(old, new).encode("utf-8"))


W = "wounds.inl"
sub(W, """    float fade = 1.f; // 1 as struck; closes towards 0 while the character is marked injuries.mend
""", """    float fade = 1.f; // 1 as struck; closes towards 0 while the character is marked injuries.mend
    float run = 0.f;  // length of the blood runs below a cut (cm); grows while the character bleeds
    float wet = 1.f;  // 1 fresh blood, falls to 0 (dried) about a minute after the bleeding stops
""")
sub(W, """enum WoundKind : uint8_t { woundCut = 1, woundCrush = 2, woundThrust = 3 };
""", """enum WoundKind : uint8_t { woundCut = 1, woundCrush = 2, woundThrust = 3 };
// The character's bleeding rate (0..20): 0x168410 raises it from the wound inflow (+0x10D4) and, above
// 1, drains health and balance with it; it falls by 0.1 a tick once the inflow stops.
constexpr size_t woundCharacterBleed = 0x10DC;
constexpr float woundBleedFull = 6.f, woundFreshSeconds = 10.f, woundDrySeconds = 60.f, woundBruiseSeconds = 90.f;
""")
sub(W, """        float world[3], path[3];
        outOfPose(pose, w.local, true, world);""", """        if (w.kind != woundCrush && fadeDt > 0.f) {
            // Blood runs while the game says this character bleeds (and for the first seconds after any
            // cut), then dries.
            float bleed = 0.f;
            __try { bleed = *(const float*)(owner + woundCharacterBleed); }
            __except (EXCEPTION_EXECUTE_HANDLER) { bleed = 0.f; }
            if (!std::isfinite(bleed)) bleed = 0.f;
            const float age = float(now - w.born) / 1000.f;
            const float flow = (std::max)(std::clamp(bleed / woundBleedFull, 0.f, 1.f), age < woundFreshSeconds ? 0.6f : 0.f);
            if (flow > 0.02f) w.run = (std::min)(w.run + fadeDt * (0.4f + 1.6f * flow), 4.f + 14.f * w.severity);
            w.wet = flow >= w.wet ? flow : (std::max)(w.wet - fadeDt / woundDrySeconds, flow);
        }
        float world[3], path[3];
        outOfPose(pose, w.local, true, world);""")
sub(W, """        // Fresh cuts bleed: the runs lengthen over the first half minute.
        const float age = float(now - w.born) / 1000.f;
        const float run = w.kind == woundCrush ? 0.f : (std::min)(age / 30.f, 1.f) * (4.f + 14.f * w.severity);
        // A closing wound shrinks towards its middle and pales.
        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade};
        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind)};
        const float c[4] = {w.severity * w.fade, w.seed, w.halfWidth * w.fade, run * w.fade};""",
    """        // Kind in the whole part of b[3]; its fraction carries a cut's wetness or a bruise's age, 0..1.
        const float age = float(now - w.born) / 1000.f;
        const float aux = w.kind == woundCrush ? (std::min)(age / woundBruiseSeconds, 1.f) : std::clamp(w.wet, 0.f, 1.f);
        // A closing wound shrinks towards its middle and pales.
        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade};
        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind) + 0.98f * aux};
        const float c[4] = {w.severity * w.fade, w.seed, w.halfWidth * w.fade, w.run * w.fade};""")

V = "view_effects.inl"
sub(V, """uniform vec4 woundB[12];   // the blade's path, view space; w: 1 cut, 2 crush, 3 thrust""",
    """uniform vec4 woundB[12];   // the blade's path, view space; w: kind (1 cut, 2 crush, 3 thrust) + 0.98 x a cut's
                           // wetness or a bruise's age, 0..1""")
sub(V, """        float severity = C.x, seed = C.y;
        if (B.w > 1.5 && B.w < 2.5) {""", """        float severity = C.x, seed = C.y;
        float kind = floor(B.w + 0.01), aux = clamp((B.w - kind) / 0.98, 0.0, 1.0);
        if (kind == 2.0) {""")
sub(V, """            vec3 bruise = mix(vec3(0.62, 0.45, 0.62), vec3(0.42, 0.17, 0.2), 1.0 - smoothstep(0.0, 0.7, r));""",
    """            // Fresh it is an angry red swelling; over the next minute and a half it darkens to purple.
            vec3 outer = mix(vec3(0.85, 0.42, 0.4), vec3(0.62, 0.45, 0.62), aux);
            vec3 inner = mix(vec3(0.6, 0.18, 0.16), vec3(0.42, 0.17, 0.2), aux);
            vec3 bruise = mix(outer, inner, 1.0 - smoothstep(0.0, 0.7, r));""")
sub(V, """        vec3 cut = mix(vec3(1.0), vec3(0.7, 0.22, 0.2), smear * (0.55 + 0.35 * severity));""",
    """        // Wet blood is bright red; dried blood goes dark brown.
        vec3 blood = mix(vec3(0.3, 0.08, 0.05), vec3(0.32, 0.02, 0.018), aux);
        vec3 cut = mix(vec3(1.0), mix(vec3(0.55, 0.3, 0.24), vec3(0.7, 0.22, 0.2), aux), smear * (0.55 + 0.35 * severity));""")
sub(V, """            cut = mix(cut, vec3(0.32, 0.02, 0.018), run * 0.9);""", """            cut = mix(cut, blood, run * 0.9);""")
sub(V, """        wet += (inside * (0.5 + 0.5 * severity) + 0.6 * run) * stick;""",
    """        wet += (inside * (0.5 + 0.5 * severity) + 0.6 * run) * stick * (0.15 + 0.85 * aux);""")
print("ok")
