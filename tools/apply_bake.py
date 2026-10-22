"""Wound skins stage 1 into an ExCamera copy (CRLF files): python apply_bake.py <excamera root>.
Adds src/mod/wounds_bake.inl (from tools/), wires the store, the view-effects pass, the body draw
hook, the shared face-split draw (stone_skin.inl) and the GL objects (cue_resources.h)."""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"
here = Path(__file__).resolve().parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_bytes().decode("utf-8")
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert t.count(old) == 1, (rel, old[:80], t.count(old))
    p.write_bytes(t.replace(old, new).encode("utf-8"))


text = (here / "wounds_bake.inl").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
(root / "mod" / "wounds_bake.inl").write_bytes(text.encode("utf-8"))

sub("first_person.cpp", '#include "mod/stone_skin.inl"\n', '#include "mod/stone_skin.inl"\n#include "mod/wounds_bake.inl"\n')

# --- cue_resources.h: the slot textures and the bake's objects, retired with the context.
sub("cue_resources.h", """    bool stoneLive() const { return stoneTex[0] || stoneTex[1] || stoneTex[2]; }
""", """    bool stoneLive() const { return stoneTex[0] || stoneTex[1] || stoneTex[2]; }
    // Wound skins (mod/wounds_bake.inl): per-character copies of the body diffuse with the wounds
    // baked in, and the bake's program, vertex array, buffer and framebuffer. Their own liveness.
    static constexpr unsigned woundSkinLimit = 6;
    unsigned woundSkinTex[woundSkinLimit]{};
    unsigned woundBakeProgram = 0, woundBakeVao = 0, woundBakeVbo = 0, woundBakeFbo = 0;
    bool woundLive() const {
        for (unsigned t : woundSkinTex)
            if (t) return true;
        return woundBakeProgram || woundBakeVao || woundBakeVbo || woundBakeFbo;
    }
    template <class Api> void retireWound(Api& g) {
        for (unsigned& t : woundSkinTex) {
            if (t) g.deleteTextures(1, &t);
            t = 0;
        }
        if (woundBakeProgram) g.deleteProgram(woundBakeProgram);
        if (woundBakeVao) g.deleteVertexArrays(1, &woundBakeVao);
        if (woundBakeVbo) g.deleteBuffers(1, &woundBakeVbo);
        if (woundBakeFbo && g.deleteFramebuffers) g.deleteFramebuffers(1, &woundBakeFbo);
        woundBakeProgram = woundBakeVao = woundBakeVbo = woundBakeFbo = 0;
    }
""")
sub("cue_resources.h", "    bool live() const { return cueLive() || viewLive() || stoneLive(); }",
    "    bool live() const { return cueLive() || viewLive() || stoneLive() || woundLive(); }")
sub("cue_resources.h", "        if (stoneLive()) retireStone(g);\n", "        if (stoneLive()) retireStone(g);\n        if (woundLive()) retireWound(g);\n")

# --- stone_skin.inl: the face-split draw becomes shared; stone passes its maps through a callback.
S = "mod/stone_skin.inl"
sub(S, """static bool stoneSkinEmit(const WearPlan& plan, bool bind, const unsigned char* stone, const GLuint* originals) { // SEH-only frame""",
    """// Draws the plan with `replacement` (from `prepare`, cueLock held) on units 0..units-1 for the faces
// marked in `faces` and the material's own textures elsewhere. Stone skin and wound skins
// (wounds_bake.inl) share it.
using SkinReplacement = const GLuint* (*)(fp::CueResources&, const StoneGl&, const void*);
static bool skinFacesEmit(const WearPlan& plan, bool bind, const unsigned char* stone, const GLuint* originals, GLsizei units,
                          SkinReplacement prepare, const void* context) { // SEH-only frame""")
sub(S, """        auto* owner = prepareCue();
        if (!owner || !stoneSkinTextures(owner->resources, s)) return false;
        if (bind) {
            wearBind(plan.material + 8);""", """        auto* owner = prepareCue();
        const GLuint* replacement = owner ? prepare(owner->resources, s, context) : nullptr;
        if (!replacement) return false;
        if (bind) {
            wearBind(plan.material + 8);""")
sub(S, """                    s.bind(0, 3, stone[f] ? owner->resources.stoneTex : originals);""",
    """                    s.bind(0, units, stone[f] ? replacement : originals);""")
sub(S, """            if (swapped) s.bind(0, 3, originals);""", """            if (swapped) s.bind(0, units, originals);""")
sub(S, """static bool stoneSkinDrawBody(uintptr_t node, uintptr_t material, bool bind, bool ownBody) {""",
    """static const GLuint* stoneSkinReplacement(fp::CueResources& r, const StoneGl& s, const void*) {
    return stoneSkinTextures(r, s) ? r.stoneTex : nullptr;
}

static bool stoneSkinDrawBody(uintptr_t node, uintptr_t material, bool bind, bool ownBody) {""")
sub(S, """    return stoneSkinEmit(plan, bind, stone.data(), originals);""",
    """    return skinFacesEmit(plan, bind, stone.data(), originals, 3, stoneSkinReplacement, nullptr);""")

# --- headwear_render.inl: the wound skins ride the same submit and draw hooks, after stone.
H = "mod/headwear_render.inl"
sub(H, """static bool stoneSkinDraw(uintptr_t node, uintptr_t material, bool bind, bool ownBody = false);
""", """static bool stoneSkinDraw(uintptr_t node, uintptr_t material, bool bind, bool ownBody = false);
// Wound skins (wounds_bake.inl, included after stone_skin.inl) too.
static bool woundSkinSubmission(uintptr_t node);
static bool woundSkinDraw(uintptr_t node, uintptr_t material, bool bind);
""")
sub(H, """(trackedHandSubmission(node) || trackedBodySubmission(node) || stoneSkinSubmission(node));""",
    """(trackedHandSubmission(node) || trackedBodySubmission(node) || stoneSkinSubmission(node) ||
                                                woundSkinSubmission(node));""")
sub(H, """        stoneSkinDraw(submitted.node, material, bind)) return; // a stone character: body faces with the stone maps
""", """        stoneSkinDraw(submitted.node, material, bind)) return; // a stone character: body faces with the stone maps
    if (caller == expected && submitted.node && submitted.material == material && !wearDrawing && !cueGlDepth &&
        woundSkinDraw(submitted.node, material, bind)) return; // a wounded character: body faces with its baked skin
""")

# --- wounds.inl: the mapping fields, the version, the baked flag for the screen pass.
W = "mod/wounds.inl"
sub(W, """    float wet = 1.f;  // 1 fresh blood, falls to 0 (dried) about a minute after the bleeding stops
""", """    float wet = 1.f;  // 1 fresh blood, falls to 0 (dried) about a minute after the bleeding stops
    // Its spot on the character's skin texture (wounds_bake.inl): UV, and UV per cm along the blade and across.
    uintptr_t skinNode = 0;
    float uv[2]{}, uvAlong[2]{}, uvAcross[2]{};
    bool mapTried = false, mapped = false;
""")
sub(W, """static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0}, woundsMended{0};
""", """static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0}, woundsMended{0};
static unsigned woundSkinVersion = 1; // woundLock: bumped when a baked (mapped) mark changes or goes
static bool woundSkinBaked(uintptr_t character);            // wounds_bake.inl
static void bakeWoundSkins(gl::Api& g, fp::CueResources& r); // wounds_bake.inl, from the view-effects pass
""")
sub(W, """        if (e.kind == w.kind && dx * dx + dy * dy + dz * dz < woundMergeCm * woundMergeCm) {
""", """        if (e.kind == w.kind && dx * dx + dy * dy + dz * dz < woundMergeCm * woundMergeCm) {
            if (e.mapped) ++woundSkinVersion;
""")
sub(W, """        if (!read || owner != w.owner) { // the character is gone, or the part was freed or reused
            w = {};""", """        if (!read || owner != w.owner) { // the character is gone, or the part was freed or reused
            if (w.mapped) ++woundSkinVersion;
            w = {};""")
sub(W, """            if (w.fade <= 0.02f) { // closed
                w = {};""", """            if (w.fade <= 0.02f) { // closed
                if (w.mapped) ++woundSkinVersion;
                w = {};""")
sub(W, """        const float c[4] = {w.severity * w.fade, w.seed, w.halfWidth * w.fade, w.run * w.fade};""",
    """        // A mark baked into the skin passes its seed negated: the screen pass then leaves its skin part out.
        const bool baked = w.mapped && woundSkinBaked(w.owner);
        const float c[4] = {w.severity * w.fade, baked ? -(w.seed + 0.001f) : w.seed, w.halfWidth * w.fade, w.run * w.fade};""")

# --- view_effects.inl: the screen pass skips baked skin; the bake runs after the finishing pass.
V = "mod/view_effects.inl"
sub(V, """uniform vec4 woundC[12];   // severity 0..1, seed, half width (cm), length of the blood runs (cm)""",
    """uniform vec4 woundC[12];   // severity 0..1, seed (negative: the skin part is baked into the skin texture), half width (cm),
                           // length of the blood runs (cm)""")
sub(V, """        float severity = C.x, seed = C.y;
        float kind = floor(B.w + 0.01), aux = clamp((B.w - kind) / 0.98, 0.0, 1.0);""",
    """        float baked = C.y < 0.0 ? 1.0 : 0.0;
        float severity = C.x, seed = abs(C.y);
        float kind = floor(B.w + 0.01), aux = clamp((B.w - kind) / 0.98, 0.0, 1.0);""")
sub(V, """            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick * (1.0 - layer); // skin only""",
    """            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick * (1.0 - layer) * (1.0 - baked); // skin only""")
sub(V, """        cut = mix(cut, fabric, cloth);
        cut = mix(cut, plate, metal);""", """        cut = mix(cut, vec3(1.0), baked * (1.0 - layer)); // the skin already carries it
        cut = mix(cut, fabric, cloth);
        cut = mix(cut, plate, metal);""")
sub(V, """            g.uniform1f(u.at[uExposure], exposure);
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        }""", """            g.uniform1f(u.at[uExposure], exposure);
            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
            // Wound skins for the next frame's body draws; the snapshot's restore covers its state.
            if (request.wounds.count) bakeWoundSkins(g, r);
        }""")

# --- session.inl: counters.
sub("mod/session.inl", """    j.unum("wound_faults", woundFaults.load());
""", """    j.unum("wound_faults", woundFaults.load());
    j.unum("wound_skin_mapped", woundSkinMapped.load());
    j.unum("wound_skin_unmapped", woundSkinUnmapped.load());
    j.unum("wound_skin_bakes", woundSkinBakes.load());
    j.unum("wound_skin_draws", woundSkinDraws.load());
    j.unum("wound_skin_faults", woundSkinFaults.load());
""")
print("ok")
