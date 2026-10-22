"""Wound skins stage 2 + the screen pass's early out, into an ExCamera copy that already has wounds-06
(CRLF files): python apply_stage2.py <excamera root>."""
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

sub("cue_resources.h", """    unsigned woundSkinTex[woundSkinLimit]{};
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
        if (woundBakeProgram) g.deleteProgram(woundBakeProgram);""", """    unsigned woundSkinTex[woundSkinLimit]{}, woundSkinNrm[woundSkinLimit]{};
    unsigned woundBakeProgram = 0, woundBakeNormalProgram = 0, woundBakeVao = 0, woundBakeVbo = 0, woundBakeFbo = 0;
    bool woundLive() const {
        for (unsigned k = 0; k < woundSkinLimit; ++k)
            if (woundSkinTex[k] || woundSkinNrm[k]) return true;
        return woundBakeProgram || woundBakeNormalProgram || woundBakeVao || woundBakeVbo || woundBakeFbo;
    }
    template <class Api> void retireWound(Api& g) {
        for (unsigned k = 0; k < woundSkinLimit; ++k) {
            if (woundSkinTex[k]) g.deleteTextures(1, &woundSkinTex[k]);
            if (woundSkinNrm[k]) g.deleteTextures(1, &woundSkinNrm[k]);
            woundSkinTex[k] = woundSkinNrm[k] = 0;
        }
        if (woundBakeNormalProgram) g.deleteProgram(woundBakeNormalProgram);
        woundBakeNormalProgram = 0;
        if (woundBakeProgram) g.deleteProgram(woundBakeProgram);""")

# stone_skin.inl: the player's own first-person body falls back to the wound skin when not stone.
S = "mod/stone_skin.inl"
sub(S, """static bool stoneSkinWearBegin(uintptr_t node, uintptr_t material, StoneSwap& swap) {
    swap = {};
    __try {
        if (!stoneScope.count || !wearScope.colourPass || !readable(node, 0x2a0) || strncmp(nodeName(node), "_SKIN", 5) ||
            !stoneSkinActor(*(uintptr_t*)(node + field::sceneNode::parent)) || !stoneSkinOriginals(material, swap.originals)) return false;""",
    """static bool woundSkinWearBegin(uintptr_t node, uintptr_t material, StoneSwap& swap); // wounds_bake.inl
static bool stoneSkinWearBegin(uintptr_t node, uintptr_t material, StoneSwap& swap) {
    swap = {};
    bool stone = false;
    __try {
        stone = stoneScope.count && wearScope.colourPass && readable(node, 0x2a0) && !strncmp(nodeName(node), "_SKIN", 5) &&
                stoneSkinActor(*(uintptr_t*)(node + field::sceneNode::parent));
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        stone = false;
    }
    if (!stone) return woundSkinWearBegin(node, material, swap); // a wounded (not stone) player: the baked skin
    __try {
        if (!stoneSkinOriginals(material, swap.originals)) return false;""")

# view_effects.inl: the screen pass returns at once outside the wounds' screen box; the metal test
# runs only near a wound.
V = "mod/view_effects.inl"
sub(V, """uniform float woundCount;
""", """uniform float woundCount;
uniform vec4 woundRect;    // screen box (uv min xy, max zw) that holds every wound's reach; outside it nothing to do
""")
sub(V, """vec3 woundMarks(vec3 color) {
    float raw = texture2D(depthTex, uv).r;""", """vec3 woundMarks(vec3 color) {
    if (uv.x < woundRect.x || uv.y < woundRect.y || uv.x > woundRect.z || uv.y > woundRect.w) return color;
    float raw = texture2D(depthTex, uv).r;""")
sub(V, """    // A grey, unsaturated surface is taken for metal: it takes blood smears and runs but no tear or soak.
    vec3 base = toLight(color);
    float brightest = max(base.r, max(base.g, base.b)), darkest = min(base.r, min(base.g, base.b));
    float grey = 1.0 - smoothstep(0.08, 0.2, (brightest - darkest) / max(brightest, 1e-4));
""", """    float grey = 0.0;
""")
sub(V, """        if (!near) {
            n = viewNormal(uv, p);
            near = true;
        }""", """        if (!near) {
            n = viewNormal(uv, p);
            near = true;
            // A grey, unsaturated surface is taken for metal: it takes blood smears and runs but no tear or soak.
            vec3 base = toLight(color);
            float brightest = max(base.r, max(base.g, base.b)), darkest = min(base.r, min(base.g, base.b));
            grey = 1.0 - smoothstep(0.08, 0.2, (brightest - darkest) / max(brightest, 1e-4));
        }""")
sub(V, ", viewUniformCount\n", ", uWoundRect, viewUniformCount\n")
sub(V, '"woundA", "woundB", "woundC", "woundCount"};', '"woundA", "woundB", "woundC", "woundCount", "woundRect"};')
sub(V, """                g.uniform4fv(u.at[uWoundC], GLsizei(wounds.count), &wounds.c[0][0]);
            }""", """                g.uniform4fv(u.at[uWoundC], GLsizei(wounds.count), &wounds.c[0][0]);
                // The screen box of every wound's reach (centre +- half length + runs + 6 cm, as the shader
                // tests); a wound the camera stands within covers the whole view.
                float box[4] = {1.f, 1.f, 0.f, 0.f};
                for (unsigned k = 0; k < wounds.count; ++k) {
                    const float* c = wounds.a[k];
                    const float reach = c[3] + wounds.c[k][3] + 6.f, depth = -c[2];
                    if (!(depth - reach > 1.f)) { box[0] = box[1] = 0.f; box[2] = box[3] = 1.f; break; }
                    const float sx = (projection.p0 * c[0] / depth - projection.p8) * 0.5f + 0.5f;
                    const float sy = (projection.p5 * c[1] / depth - projection.p9) * 0.5f + 0.5f;
                    const float rx = std::abs(projection.p0) * reach / (depth - reach) * 0.5f;
                    const float ry = std::abs(projection.p5) * reach / (depth - reach) * 0.5f;
                    box[0] = (std::min)(box[0], sx - rx); box[1] = (std::min)(box[1], sy - ry);
                    box[2] = (std::max)(box[2], sx + rx); box[3] = (std::max)(box[3], sy + ry);
                }
                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);
            }""")
print("ok")
