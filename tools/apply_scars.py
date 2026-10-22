"""Stage 5, scars (Hunter 2026-10-22 12:02: "on living characters, wounds should fade to scars"), into an
ExCamera copy with wounds-10 (CRLF files), and the bake source in tools/:
- on the living, cuts close into pale, slightly raised scar lines (5 min; Regenerate: its mend time) and stay;
  bruises fade away (a fracture's bruise stays while the bone is broken); the dead keep their wounds;
- healed burns leave mottled, shiny scar tissue (Injuries' "injuries.burnscar" mark, 0..255).
Usage: python apply_scars.py <excamera root>"""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"
here = Path(__file__).resolve().parent


def subs(t, pairs, where):
    for old, new in pairs:
        assert t.count(old) == 1, (where, old[:80], t.count(old))
        t = t.replace(old, new)
    return t


def edit(rel, pairs):
    p = root / rel
    t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
    p.write_bytes(subs(t, pairs, rel).replace("\n", "\r\n").encode("utf-8"))


# ---- the bake source ----
bake_path = here / "wounds_bake.inl"
b = bake_path.read_text(encoding="utf-8").replace("\r\n", "\n")
b = subs(b, [
    ("""// patches; a burnt character without cuts gets a slot too.""", """// patches; a burnt character without cuts gets a slot too. Stage 5: scars. A healing cut (kind + 4, its
// fraction the scar's progress) closes into a pale, thin, slightly raised line with a faint pink halo and
// a little sheen; healed burns (Injuries' "injuries.burnscar") leave mottled, shiny, slightly lumpy tissue."""),
    ("""uniform float burnSeed;
""", """uniform float burnSeed;
uniform float burnScar;  // 0..1: scar tissue left by healed burns
"""),
    ("""// x: reddened, y: blistered, z: charred, w: ash speckle, each 0..1 at this texel.""",
     """// Healed-burn scar tissue: x how much of it, y its mottling, at this texel.
vec2 burnScarAt(vec2 t) {
    vec2 o = vec2(burnSeed * 13.1, burnSeed * 7.7);
    float f = 0.55 * burnNoise(t * 18.0 + o) + 0.3 * burnNoise(t * 41.0 + o) + 0.15 * burnNoise(t * 97.0 + o);
    return vec2(smoothstep(f - 0.15, f + 0.15, burnScar * 1.6), burnNoise(t * 60.0 + o.yx));
}
// x: reddened, y: blistered, z: charred, w: ash speckle, each 0..1 at this texel."""),
    # diffuse
    ("""    vec3 tint = vec3(1.0);
    if (burnLevel > 0.0) {
        vec4 b = burnAt(texUv);
        tint = mix(vec3(1.0), vec3(1.0, 0.62, 0.52), b.x * 0.8);""", """    vec3 tint = vec3(1.0);
    if (burnScar > 0.0) {
        vec2 s = burnScarAt(texUv);
        tint *= mix(vec3(1.0), mix(vec3(1.1, 0.9, 0.88), vec3(1.2, 1.1, 1.05), s.y), s.x * 0.7);
    }
    if (burnLevel > 0.0) {
        vec4 b = burnAt(texUv);
        tint *= mix(vec3(1.0), vec3(1.0, 0.62, 0.52), b.x * 0.8);"""),
    ("""        float kind = floor(R.x + 0.01), aux = clamp((R.x - kind) / 0.98, 0.0, 1.0);
        float severity = R.y, seed = R.z, fracture = R.w;""", """        float kind = floor(R.x + 0.01), aux = clamp((R.x - kind) / 0.98, 0.0, 1.0), scar = 0.0;
        if (kind > 4.0) { kind -= 4.0; scar = aux; aux = 0.0; }
        float severity = R.y, seed = R.z, fracture = R.w;"""),
    ("""        cut = mix(cut, mix(vec3(0.5, 0.035, 0.03), vec3(0.07, 0.003, 0.003), 1.0 - smoothstep(0.0, 0.8, x)), inside);
        tint *= cut;""", """        cut = mix(cut, mix(vec3(0.5, 0.035, 0.03), vec3(0.07, 0.003, 0.003), 1.0 - smoothstep(0.0, 0.8, x)), inside);
        // Healing into a scar: the gash closes to a pale, thin line with a faint pink halo.
        float line = taper * (1.0 - smoothstep(0.25, 0.6, x));
        float halo = taper * (1.0 - smoothstep(0.6, 2.0, x));
        cut = mix(cut, mix(mix(vec3(1.0), vec3(1.05, 0.9, 0.88), halo * 0.45), vec3(1.14, 1.02, 0.97), line * 0.85), scar);
        tint *= cut;"""),
    # normal
    ("""        float kind = floor(R.x + 0.01);
        float severity = R.y, seed = R.z, near;""", """        float kind = floor(R.x + 0.01), scar = 0.0;
        if (kind > 4.0) { scar = clamp((R.x - kind) / 0.98, 0.0, 1.0); kind -= 4.0; }
        float severity = R.y, seed = R.z, near;"""),
    ("""            h += -0.4 * severity * taper * (1.0 - smoothstep(0.0, 1.0, x)) + 0.12 * severity * lip; // the gash, its lips""",
     """            float line = taper * (1.0 - smoothstep(0.25, 0.6, x));
            h += mix(-0.4 * severity * taper * (1.0 - smoothstep(0.0, 1.0, x)) + 0.12 * severity * lip, 0.06 * line, scar); // the gash and lips, or the scar's ridge"""),
    ("""        slope += vec2(dFdx(hb) * texSize.x, dFdy(hb) * texSize.y) / 150.0;
    }""", """        slope += vec2(dFdx(hb) * texSize.x, dFdy(hb) * texSize.y) / 150.0;
    }
    if (burnScar > 0.0) {
        vec2 s = burnScarAt(texUv);
        float hs = 0.04 * s.x * (s.y - 0.5); // lumpy scar tissue
        slope += vec2(dFdx(hs) * texSize.x, dFdy(hs) * texSize.y) / 150.0;
    }"""),
    # spec
    ("""        float kind = floor(R.x + 0.01), aux = clamp((R.x - kind) / 0.98, 0.0, 1.0);
        if (kind == 2.0) continue; // bruises leave the skin's own sheen""", """        float kind = floor(R.x + 0.01), aux = clamp((R.x - kind) / 0.98, 0.0, 1.0), scar = 0.0;
        if (kind > 4.0) { kind -= 4.0; scar = aux; aux = 0.0; }
        if (kind == 2.0) continue; // bruises leave the skin's own sheen"""),
    ("""        float cover = max(inside, 0.6 * smear * R.y);
        if (cover > blood) { blood = cover; wet = aux; }
    }""", """        float cover = max(inside, 0.6 * smear * R.y) * (1.0 - scar);
        if (cover > blood) { blood = cover; wet = aux; }
        sheen = max(sheen, taper * (1.0 - smoothstep(0.25, 0.6, x)) * scar);
    }"""),
    ("""    float blood = 0.0, wet = 0.0;""", """    float blood = 0.0, wet = 0.0, sheen = 0.0;"""),
    ("""    vec3 skin = base.rgb;
    if (burnLevel > 0.0) {""", """    vec3 skin = mix(base.rgb, vec3(0.3, 0.6, 0.0), sheen * 0.6); // scars: a little sheen
    if (burnScar > 0.0) skin = mix(skin, vec3(0.35, 0.75, 0.0), burnScarAt(texUv).x * 0.8);
    if (burnLevel > 0.0) {"""),
    # C++: burn scar per slot, the full quad, the encoding, re-bakes while scarring
    ("""    for (int b = 0; b < woundBurnCount; ++b)
        if (woundBurns[b].level) claim(woundBurns[b].actor, 0);""", """    for (int b = 0; b < woundBurnCount; ++b)
        if (woundBurns[b].level) claim(woundBurns[b].actor, 0);
    for (int b = 0; b < woundBurnScarCount; ++b)
        if (woundBurnScars[b].level) claim(woundBurnScars[b].actor, 0);"""),
    ("""            const float burn = woundBurnLevel(slot.actor);""", """            const float burn = woundBurnLevel(slot.actor), burnScar = woundBurnScar(slot.actor);"""),
    ("""                const float aux = w.kind == woundCrush ? (std::min)(age / woundBruiseSeconds, 1.f) : std::clamp(w.wet, 0.f, 1.f);
                ages = ages || (w.kind == woundCrush && age < woundBruiseSeconds) || w.fade < 1.f || (w.kind != woundCrush && w.wet > 0.f);""",
     """                const bool scarring = w.kind != woundCrush && w.scar > 0.001f;
                const float aux = scarring ? (std::min)(w.scar, 1.f)
                                : w.kind == woundCrush ? (std::min)(age / woundBruiseSeconds, 1.f) : std::clamp(w.wet, 0.f, 1.f);
                ages = ages || (w.kind == woundCrush && age < woundBruiseSeconds) || w.fade < 1.f ||
                       (w.kind != woundCrush && w.wet > 0.f) || (scarring && w.scar < 1.f);"""),
    ("""                const float m[4] = {float(w.kind) + 0.98f * aux, w.severity * w.fade, w.seed, w.fracture ? 1.f : 0.f};""",
     """                const float m[4] = {float(w.kind + (scarring ? 4 : 0)) + 0.98f * aux, w.severity * w.fade, w.seed, w.fracture ? 1.f : 0.f};"""),
    ("""            if (!count && burn <= 0.f) continue;""", """            if (!count && burn <= 0.f && burnScar <= 0.f) continue;"""),
    ("""            if (burn > 0.f) {
                const float all[6][2]""", """            if (burn > 0.f || burnScar > 0.f) {
                const float all[6][2]"""),
    ("""                g.uniform1f(g.getUniformLocation(program, "burnLevel"), burn);""",
     """                g.uniform1f(g.getUniformLocation(program, "burnLevel"), burn);
                g.uniform1f(g.getUniformLocation(program, "burnScar"), burnScar);"""),
], "wounds_bake.inl")
bake_path.write_text(b, encoding="utf-8")
(root / "mod" / "wounds_bake.inl").write_bytes(b.replace("\n", "\r\n").encode("utf-8"))

# ---- wounds.inl ----
edit("mod/wounds.inl", [
    ("""    float drip = 0.f;      // counts up to the next drop of blood falling from a bleeding cut
""", """    float drip = 0.f;      // counts up to the next drop of blood falling from a bleeding cut
    float scar = 0.f;      // a cut on the living closing into a scar: 0 open .. 1 a scar for good
"""),
    ("""constexpr float woundDripSeconds = 120.f, woundDripDrySeconds = 30.f;""",
     """constexpr float woundDripSeconds = 120.f, woundDripDrySeconds = 30.f;
// On the living: an open cut closes into a scar over this long (the Regenerate mark's own time while it
// runs); a bruise fades away over this long.
constexpr float woundScarSeconds = 300.f, woundBruiseHealSeconds = 900.f;"""),
    ("""static WoundBurn woundBurns[64];
static int woundBurnCount = 0;
static float woundBurnLevel(uintptr_t actor) {
    for (int b = 0; b < woundBurnCount; ++b)
        if (woundBurns[b].actor == actor) return float(woundBurns[b].level) / 255.f;
    return 0.f;
}""", """static WoundBurn woundBurns[64], woundBurnScars[64]; // "injuries.burn" and "injuries.burnscar"
static int woundBurnCount = 0, woundBurnScarCount = 0;
static float woundLevelOf(const WoundBurn* table, int count, uintptr_t actor) {
    for (int b = 0; b < count; ++b)
        if (table[b].actor == actor) return float(table[b].level) / 255.f;
    return 0.f;
}
static float woundBurnLevel(uintptr_t actor) { return woundLevelOf(woundBurns, woundBurnCount, actor); }
static float woundBurnScar(uintptr_t actor) { return woundLevelOf(woundBurnScars, woundBurnScarCount, actor); }
// One mark's levels into its table; a change of 4/255 or more anywhere re-bakes the skins.
static void woundReadLevels(int (*marks)(const char*, uintptr_t*, uint32_t*, int), const char* name, WoundBurn* table,
                            int& count) {
    uintptr_t markNodes[64]{};
    uint32_t levels[64]{};
    int found = 0;
    __try { found = marks(name, markNodes, levels, 64); }
    __except (EXCEPTION_EXECUTE_HANDLER) { found = 0; woundFaults.fetch_add(1, std::memory_order_relaxed); }
    found = std::clamp(found, 0, 64);
    bool changed = found != count;
    for (int b = 0; b < found && !changed; ++b)
        changed = std::abs(woundLevelOf(table, count, markNodes[b]) * 255.f - float(levels[b])) >= 4.f;
    if (!changed) return;
    for (int b = 0; b < found; ++b) table[b] = {markNodes[b], (std::min)(levels[b], 255u)};
    count = found;
    ++woundSkinVersion;
}"""),
    ("""    {
        uintptr_t burnNodes[64]{};
        uint32_t burnLevels[64]{};
        int found = 0;
        if (const WoundMarkNodes marks = woundMarkExport()) {
            __try { found = marks("injuries.burn", burnNodes, burnLevels, 64); }
            __except (EXCEPTION_EXECUTE_HANDLER) { found = 0; woundFaults.fetch_add(1, std::memory_order_relaxed); }
            found = std::clamp(found, 0, 64);
        }
        bool changed = found != woundBurnCount;
        for (int b = 0; b < found && !changed; ++b) {
            const float before = woundBurnLevel(burnNodes[b]) * 255.f;
            changed = std::abs(before - float(burnLevels[b])) >= 4.f;
        }
        if (changed) {
            for (int b = 0; b < found; ++b) woundBurns[b] = {burnNodes[b], (std::min)(burnLevels[b], 255u)};
            woundBurnCount = found;
            ++woundSkinVersion;
        }
        out.burning = woundBurnCount > 0;
    }""", """    if (const WoundMarkNodes marks = woundMarkExport()) {
        woundReadLevels(marks, "injuries.burn", woundBurns, woundBurnCount);
        woundReadLevels(marks, "injuries.burnscar", woundBurnScars, woundBurnScarCount);
    }
    out.burning = woundBurnCount > 0 || woundBurnScarCount > 0;"""),
    ("""        uintptr_t ownerNode = 0;
        if (mendCount || brokenCount) {
            __try { ownerNode = *(const uintptr_t*)(owner + field::character::sceneNode); }
            __except (EXCEPTION_EXECUTE_HANDLER) { ownerNode = 0; }
        }""", """        uintptr_t ownerNode = 0;
        bool alive = true;
        __try {
            alive = (*(const unsigned*)(owner + field::character::lifeFlags) & 0x100) == 0;
            if (mendCount || brokenCount) ownerNode = *(const uintptr_t*)(owner + field::character::sceneNode);
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            ownerNode = 0;
        }"""),
    ("""        if (mendCount && fadeDt > 0.f) {
            for (int k = 0; ownerNode && k < mendCount; ++k) {
                if (mendNodes[k] != ownerNode || !mendSeconds[k]) continue;
                w.fade -= fadeDt / float(mendSeconds[k]);
                break;
            }
            if (w.fade <= 0.02f) { // closed""", """        // Healing on the living: a cut closes into a scar that stays, a bruise fades away (not while its
        // bone is broken); Regenerate's mark sets its own, faster pace. The dead keep their wounds.
        if (alive && fadeDt > 0.f) {
            float mend = 0.f;
            for (int k = 0; ownerNode && k < mendCount; ++k)
                if (mendNodes[k] == ownerNode && mendSeconds[k]) mend = float(mendSeconds[k]);
            if (w.kind == woundCrush) {
                if (!w.fracture || mend > 0.f) w.fade -= fadeDt / (mend > 0.f ? mend : woundBruiseHealSeconds);
            } else if (w.scar < 1.f) {
                const float before = w.scar;
                w.scar = (std::min)(w.scar + fadeDt / (mend > 0.f ? mend : woundScarSeconds), 1.f);
                if (w.mapped && std::floor(before * 10.f) != std::floor(w.scar * 10.f)) ++woundSkinVersion;
            }
            if (w.fade <= 0.02f) { // a bruise gone"""),
    ("""            const float flow = (std::max)(std::clamp(bleed / woundBleedFull, 0.f, 1.f), age < woundFreshSeconds ? 0.6f : 0.f);""",
     """            const float flow = w.scar > 0.3f ? 0.f // a closing cut has stopped bleeding
                               : (std::max)(std::clamp(bleed / woundBleedFull, 0.f, 1.f), age < woundFreshSeconds ? 0.6f : 0.f);"""),
    ("""        const float aux = w.kind == woundCrush ? (std::min)(age / woundBruiseSeconds, 1.f) : std::clamp(w.wet, 0.f, 1.f);""",
     """        // Kind + 4 for a scarring cut, its fraction then the scar's progress.
        const bool scarring = w.kind != woundCrush && w.scar > 0.001f;
        const float aux = scarring ? (std::min)(w.scar, 1.f)
                        : w.kind == woundCrush ? (std::min)(age / woundBruiseSeconds, 1.f) : std::clamp(w.wet, 0.f, 1.f);"""),
    ("""        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind) + 0.98f * aux};""",
     """        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind + (scarring ? 4 : 0)) + 0.98f * aux};"""),
    ("""                            w.halfWidth * w.fade, w.run * w.fade};""", """                            w.halfWidth * w.fade, w.run * w.fade * (1.f - w.scar)};"""),
])

# ---- view_effects.inl woundShader: scars on the screen pass ----
edit("mod/view_effects.inl", [
    ("""        float kind = floor(B.w + 0.01), aux = clamp((B.w - kind) / 0.98, 0.0, 1.0);""",
     """        float kind = floor(B.w + 0.01), aux = clamp((B.w - kind) / 0.98, 0.0, 1.0), scar = 0.0;
        if (kind > 4.0) { kind -= 4.0; scar = aux; aux = 0.0; } // a cut closing into a scar"""),
    ("""        cut = mix(cut, vec3(1.0), baked * (1.0 - layer)); // the skin already carries it""",
     """        // Healing into a scar: a pale, thin line with a faint pink halo.
        float scarLine = taper * (1.0 - smoothstep(0.25, 0.6, x)), scarHalo = taper * (1.0 - smoothstep(0.6, 2.0, x));
        cut = mix(cut, mix(mix(vec3(1.0), vec3(1.05, 0.9, 0.88), scarHalo * 0.45), vec3(1.14, 1.02, 0.97), scarLine * 0.85), scar);
        inside *= 1.0 - scar;
        cut = mix(cut, vec3(1.0), baked * (1.0 - layer)); // the skin already carries it"""),
])
print("ok")
