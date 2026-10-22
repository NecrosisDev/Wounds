"""Wound skins stage 3, into an ExCamera copy with wounds-08 (CRLF files): wet gloss baked into a copy of
the spec map (unit 1), and fractures (Injuries' "injuries.broken" mark: one bit per limb bone) drawn as
dark, wide, swollen bruises. Edits tools/wounds_bake.inl (the source) and copies it in.
Usage: python apply_stage3.py <excamera root>"""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"
here = Path(__file__).resolve().parent


def sub(text, old, new, where):
    assert text.count(old) == 1, (where, old[:80], text.count(old))
    return text.replace(old, new)


def edit(rel, pairs):
    p = root / rel
    t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        t = sub(t, old, new, rel)
    p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))


# ---- wounds_bake.inl (source in tools/) ----
bake = here / "wounds_bake.inl"
b = bake.read_text(encoding="utf-8").replace("\r\n", "\n")
pairs = [
    ("""// body in first person takes both copies through the headwear path's swap (stone_skin.inl).""",
     """// body in first person takes both copies through the headwear path's swap (stone_skin.inl). Stage 3: wet
// gloss goes into a copy of the spec map (unit 1: the skin shading reads R as specular strength, G as
// gloss, B as metal, shading.flb shadesss_f), fresh blood glossy and dried blood dull; a fracture (R.w 1)
// draws as a wider, darker bruise and swells more."""),
    ("""    WoundSkinMap diffuse, normal;       // units 0 and 2""", """    WoundSkinMap diffuse, normal, spec; // units 0, 2 and 1"""),
    ("""    bool ready = false, normalReady = false;
};""", """    bool ready = false, normalReady = false, specReady = false;
};"""),
    # Fragment: fracture colours.
    ("""        float severity = R.y, seed = R.z;
        if (kind == 2.0) {
            float mottle = 0.78 + 0.22 * sin(q.x * 0.9 + seed * 31.0) * sin(q.y * 1.3 - seed * 17.0);
            float r = length(q) / (Q.z * mottle);
            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity);
            vec3 outer = mix(vec3(0.85, 0.42, 0.4), vec3(0.62, 0.45, 0.62), aux);
            vec3 inner = mix(vec3(0.6, 0.18, 0.16), vec3(0.42, 0.17, 0.2), aux);""",
     """        float severity = R.y, seed = R.z, fracture = R.w;
        if (kind == 2.0) {
            float mottle = 0.78 + 0.22 * sin(q.x * 0.9 + seed * 31.0) * sin(q.y * 1.3 - seed * 17.0);
            float r = length(q) / (Q.z * mottle);
            float w = min((1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * (1.0 + 0.35 * fracture), 1.0);
            // Over a broken bone the bruise spreads wide and goes deep purple-black at its centre.
            vec3 outer = mix(mix(vec3(0.85, 0.42, 0.4), vec3(0.62, 0.45, 0.62), aux), vec3(0.5, 0.33, 0.5), fracture);
            vec3 inner = mix(mix(vec3(0.6, 0.18, 0.16), vec3(0.42, 0.17, 0.2), aux), vec3(0.26, 0.08, 0.13), fracture);"""),
    # Normal: fracture swelling.
    ("""            h += 0.15 * severity * (1.0 - smoothstep(0.0, 1.0, r)); // the swelling""",
     """            h += (0.15 * severity + 0.45 * R.w) * (1.0 - smoothstep(0.0, 1.0, r)); // the swelling, a fracture's more"""),
]
for old, new in pairs:
    b = sub(b, old, new, "wounds_bake.inl")
# The spec fragment and its program.
b = sub(b, """static GLuint woundSkinProgram(gl::Api& g, const char* fragmentText) {""", """// The spec map's copy: fresh blood (the gash, the smear) glossy and strong, dried blood dull, never metal.
static const char* const woundSkinSpecFragment = R"glsl(#version 130
uniform sampler2D baseTex;
uniform vec4 markP[16];
uniform vec4 markQ[16];
uniform vec4 markR[16];
uniform float markCount;
in vec2 texUv;
out vec4 fragColor;
void main() {
    vec4 base = textureLod(baseTex, texUv, 0.0);
    float blood = 0.0, wet = 0.0;
    for (int i = 0; i < 16; ++i) {
        if (float(i) >= markCount) break;
        vec4 P = markP[i], Q = markQ[i], R = markR[i];
        float kind = floor(R.x + 0.01), aux = clamp((R.x - kind) / 0.98, 0.0, 1.0);
        if (kind == 2.0) continue; // bruises leave the skin's own sheen
        vec2 o = texUv - P.xy;
        vec2 q = vec2(dot(P.zw, o), dot(Q.xy, o));
        float a = q.x / Q.z;
        float taper = sqrt(max(1.0 - a * a, 0.0));
        float wobble = 0.22 * Q.w * sin(a * 5.0 + R.z * 40.0);
        float x = abs(q.y - wobble) / max(Q.w * (0.25 + 0.75 * taper), 0.05);
        float inside = taper > 0.0 ? 1.0 - smoothstep(0.6, 1.0, x) : 0.0;
        float smear = (1.0 - smoothstep(1.2, 4.0, x)) * (1.0 - smoothstep(0.8, 1.25, abs(a)));
        float cover = max(inside, 0.6 * smear * R.y);
        if (cover > blood) { blood = cover; wet = aux; }
    }
    vec3 spec = vec3(mix(0.12, 0.75, wet), mix(0.25, 0.9, wet), 0.0); // strength, gloss, metal
    fragColor = vec4(mix(base.rgb, spec, blood), base.a);
}
)glsl";

static GLuint woundSkinProgram(gl::Api& g, const char* fragmentText) {""", "wounds_bake.inl")
b = sub(b, """        r.woundBakeNormalProgram = woundSkinProgram(g, woundSkinNormalFragment); // none: colour only""",
        """        r.woundBakeNormalProgram = woundSkinProgram(g, woundSkinNormalFragment); // none: colour only
        r.woundBakeSpecProgram = woundSkinProgram(g, woundSkinSpecFragment);     // none: the skin's own sheen""", "wounds_bake.inl")
b = sub(b, """            slot.normalReady = bakeMap(slot.normal, r.woundSkinNrm[k], r.woundBakeNormalProgram, slot.normalReady);""",
        """            slot.normalReady = bakeMap(slot.normal, r.woundSkinNrm[k], r.woundBakeNormalProgram, slot.normalReady);
            slot.specReady = bakeMap(slot.spec, r.woundSkinSpc[k], r.woundBakeSpecProgram, slot.specReady);""", "wounds_bake.inl")
# Fractures in the bake: R.w and a wider reach.
b = sub(b, """                const float length = w.halfLength * w.fade, width = w.halfWidth * w.fade;""",
        """                const float length = w.halfLength * w.fade * (w.fracture ? woundFractureScale : 1.f), width = w.halfWidth * w.fade;""",
        "wounds_bake.inl")
b = sub(b, """                const float m[4] = {float(w.kind) + 0.98f * aux, w.severity * w.fade, w.seed, 0.f};""",
        """                const float m[4] = {float(w.kind) + 0.98f * aux, w.severity * w.fade, w.seed, w.fracture ? 1.f : 0.f};""",
        "wounds_bake.inl")
# The draw and the first-person swap take the spec copy too.
b = sub(b, """    if (woundSkinSlots[k].normalReady && r.woundSkinNrm[k]) swap->textures[2] = r.woundSkinNrm[k];""",
        """    if (woundSkinSlots[k].normalReady && r.woundSkinNrm[k]) swap->textures[2] = r.woundSkinNrm[k];
    if (woundSkinSlots[k].specReady && r.woundSkinSpc[k]) swap->textures[1] = r.woundSkinSpc[k];""", "wounds_bake.inl")
b = sub(b, """    if (slot.material == material && slot.diffuse.source == originals[0] && slot.normal.source == originals[2]) return slot.ready;
    slot.material = material;
    slot.diffuse = {};
    slot.normal = {};
    slot.diffuse.source = originals[0];
    slot.normal.source = originals[2];
    slot.ready = slot.normalReady = false;""", """    if (slot.material == material && slot.diffuse.source == originals[0] && slot.normal.source == originals[2] &&
        slot.spec.source == originals[1])
        return slot.ready;
    slot.material = material;
    slot.diffuse = {};
    slot.normal = {};
    slot.spec = {};
    slot.diffuse.source = originals[0];
    slot.normal.source = originals[2];
    slot.spec.source = originals[1];
    slot.ready = slot.normalReady = slot.specReady = false;""", "wounds_bake.inl")
b = sub(b, """        swap.stone[1] = swap.originals[1];""",
        """        swap.stone[1] = slot.specReady && owner->resources.woundSkinSpc[found] ? owner->resources.woundSkinSpc[found]
                                                                                 : swap.originals[1];""", "wounds_bake.inl")
bake.write_text(b, encoding="utf-8")
(root / "mod" / "wounds_bake.inl").write_bytes(b.replace("\n", "\r\n").encode("utf-8"))

# ---- cue_resources.h ----
edit("cue_resources.h", [
    ("""    unsigned woundSkinTex[woundSkinLimit]{}, woundSkinNrm[woundSkinLimit]{};
    unsigned woundBakeProgram = 0, woundBakeNormalProgram = 0, woundBakeVao = 0, woundBakeVbo = 0, woundBakeFbo = 0;""",
     """    unsigned woundSkinTex[woundSkinLimit]{}, woundSkinNrm[woundSkinLimit]{}, woundSkinSpc[woundSkinLimit]{};
    unsigned woundBakeProgram = 0, woundBakeNormalProgram = 0, woundBakeSpecProgram = 0, woundBakeVao = 0, woundBakeVbo = 0,
             woundBakeFbo = 0;"""),
    ("""            if (woundSkinTex[k] || woundSkinNrm[k]) return true;
        return woundBakeProgram || woundBakeNormalProgram || woundBakeVao || woundBakeVbo || woundBakeFbo;""",
     """            if (woundSkinTex[k] || woundSkinNrm[k] || woundSkinSpc[k]) return true;
        return woundBakeProgram || woundBakeNormalProgram || woundBakeSpecProgram || woundBakeVao || woundBakeVbo || woundBakeFbo;"""),
    ("""            if (woundSkinNrm[k]) g.deleteTextures(1, &woundSkinNrm[k]);
            woundSkinTex[k] = woundSkinNrm[k] = 0;
        }
        if (woundBakeNormalProgram) g.deleteProgram(woundBakeNormalProgram);
        woundBakeNormalProgram = 0;""", """            if (woundSkinNrm[k]) g.deleteTextures(1, &woundSkinNrm[k]);
            if (woundSkinSpc[k]) g.deleteTextures(1, &woundSkinSpc[k]);
            woundSkinTex[k] = woundSkinNrm[k] = woundSkinSpc[k] = 0;
        }
        if (woundBakeNormalProgram) g.deleteProgram(woundBakeNormalProgram);
        if (woundBakeSpecProgram) g.deleteProgram(woundBakeSpecProgram);
        woundBakeNormalProgram = woundBakeSpecProgram = 0;"""),
])

# ---- wounds.inl: the part's index at intake, the broken bits per frame, fracture marks out ----
edit("mod/wounds.inl", [
    ("""    bool mapTried = false, mapped = false;
    uint8_t kind = 0;
};""", """    bool mapTried = false, mapped = false;
    bool fracture = false; // a bruise over a bone Injuries reports broken ("injuries.broken")
    int8_t partIndex = -1; // the struck part's index (+0x468), 0..17
    uint8_t kind = 0;
};"""),
    ("""constexpr size_t woundCharacterBleed = 0x10DC;""", """constexpr size_t woundCharacterBleed = 0x10DC;
// Injuries' "injuries.broken" mark: one bit per limb bone, the part indices (+0x468) each covers. A fracture
// bruise spreads this much wider.
constexpr size_t woundPartIndex = 0x468;
constexpr float woundFractureScale = 1.6f;
inline int woundBoneBit(int part) {
    switch (part) {
    case 1: return 0;           // right thigh
    case 2: case 3: return 1;   // right shin, foot
    case 4: return 2;           // left thigh
    case 5: case 6: return 3;   // left shin, foot
    case 10: case 11: return 4; // right shoulder, upper arm
    case 12: case 16: return 5; // right forearm, hand
    case 13: case 14: return 6; // left shoulder, upper arm
    case 15: case 17: return 7; // left forearm, hand
    default: return -1;
    }
}"""),
    ("""    w.kind = kind;
""", """    w.kind = kind;
    __try {
        const int index = *(const int*)(w.part + woundPartIndex);
        w.partIndex = int8_t(index >= 0 && index < 18 ? index : -1);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        w.partIndex = -1;
    }
"""),
    ("""    const float fadeDt = woundFadeTick ? (std::min)(float(now - woundFadeTick) / 1000.f, 0.5f) : 0.f;""",
     """    uintptr_t brokenNodes[woundMendLimit]{};
    uint32_t brokenBits[woundMendLimit]{};
    int brokenCount = 0;
    if (const WoundMarkNodes marks = woundMarkExport()) {
        __try { brokenCount = marks("injuries.broken", brokenNodes, brokenBits, int(woundMendLimit)); }
        __except (EXCEPTION_EXECUTE_HANDLER) { brokenCount = 0; woundFaults.fetch_add(1, std::memory_order_relaxed); }
        brokenCount = std::clamp(brokenCount, 0, int(woundMendLimit));
    }
    const float fadeDt = woundFadeTick ? (std::min)(float(now - woundFadeTick) / 1000.f, 0.5f) : 0.f;"""),
    ("""        if (mendCount && fadeDt > 0.f) {
            uintptr_t ownerNode = 0;
            __try { ownerNode = *(const uintptr_t*)(owner + field::character::sceneNode); }
            __except (EXCEPTION_EXECUTE_HANDLER) { ownerNode = 0; }""",
     """        uintptr_t ownerNode = 0;
        if (mendCount || brokenCount) {
            __try { ownerNode = *(const uintptr_t*)(owner + field::character::sceneNode); }
            __except (EXCEPTION_EXECUTE_HANDLER) { ownerNode = 0; }
        }
        // A bruise over a bone Injuries reports broken is a fracture (and back to a bruise once it heals).
        if (w.kind == woundCrush) {
            bool fracture = false;
            const int bit = woundBoneBit(w.partIndex);
            for (int k = 0; ownerNode && bit >= 0 && k < brokenCount; ++k)
                if (brokenNodes[k] == ownerNode) fracture = ((brokenBits[k] >> bit) & 1) != 0;
            if (fracture != w.fracture) {
                w.fracture = fracture;
                if (w.mapped) ++woundSkinVersion;
            }
        }
        if (mendCount && fadeDt > 0.f) {"""),
    ("""        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade};""",
     """        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade * (w.fracture ? woundFractureScale : 1.f)};"""),
    ("""        const float c[4] = {w.severity * w.fade, baked ? -(w.seed + 0.001f) : w.seed, w.halfWidth * w.fade, w.run * w.fade};""",
     """        // A fracture passes its severity above 1.25 (the screen pass reads it as one).
        const float c[4] = {w.severity * w.fade + (w.fracture ? 1.5f : 0.f), baked ? -(w.seed + 0.001f) : w.seed,
                            w.halfWidth * w.fade, w.run * w.fade};"""),
])

# ---- view_effects.inl woundShader: fracture colours ----
edit("mod/view_effects.inl", [
    ("""        float baked = C.y < 0.0 ? 1.0 : 0.0;
        float severity = C.x, seed = abs(C.y);""", """        float baked = C.y < 0.0 ? 1.0 : 0.0;
        float fracture = step(1.25, C.x);
        float severity = C.x - 1.5 * fracture, seed = abs(C.y);"""),
    ("""            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick * (1.0 - layer) * (1.0 - baked); // skin only
            // Fresh it is an angry red swelling; over the next minute and a half it darkens to purple.
            vec3 outer = mix(vec3(0.85, 0.42, 0.4), vec3(0.62, 0.45, 0.62), aux);
            vec3 inner = mix(vec3(0.6, 0.18, 0.16), vec3(0.42, 0.17, 0.2), aux);""",
     """            float w = min((1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * (1.0 + 0.35 * fracture), 1.0) *
                      stick * (1.0 - layer) * (1.0 - baked); // skin only
            // Fresh it is an angry red swelling; over the next minute and a half it darkens to purple. Over a
            // broken bone it is wider and goes deep purple-black at its centre.
            vec3 outer = mix(mix(vec3(0.85, 0.42, 0.4), vec3(0.62, 0.45, 0.62), aux), vec3(0.5, 0.33, 0.5), fracture);
            vec3 inner = mix(mix(vec3(0.6, 0.18, 0.16), vec3(0.42, 0.17, 0.2), aux), vec3(0.26, 0.08, 0.13), fracture);"""),
])
print("ok")
