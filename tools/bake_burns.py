"""tools/wounds_bake.inl stage 4: burns (Injuries' "injuries.burn" mark, 0..255 per character) baked over
the whole skin: reddening, blisters, charred patches, in all three maps. Slots are keyed by the
character's scene node so a burnt character without cuts gets one. Edits the source in place (LF)."""
from pathlib import Path

p = Path(__file__).resolve().parent / "wounds_bake.inl"
t = p.read_text(encoding="utf-8").replace("\r\n", "\n")


def sub(old, new, count=1):
    global t
    assert t.count(old) == count, (old[:80], t.count(old))
    t = t.replace(old, new)


sub("""// draws as a wider, darker bruise and swells more.""", """// draws as a wider, darker bruise and swells more. Stage 4: burns, from Injuries' "injuries.burn" mark
// (a level per character), over the whole skin: reddened first, then blistered, then charred black in
// patches; a burnt character without cuts gets a slot too.""")

# The fragments share a head: the version and the burn pattern.
sub("""static const char* const woundSkinFragment = R"glsl(#version 130
""", """// Shared by the three fragment programs: the version, a hash and the burn pattern (value noise in UV
// space; seams in the UV layout show as seams in the pattern).
static const char* const woundSkinFragmentHead = R"glsl(#version 130
uniform float burnLevel; // 0..1: the character's burn
uniform float burnSeed;
float markHash(float x) { return fract(sin(x * 12.9898) * 43758.5453); }
float burnNoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = markHash(i.x + i.y * 57.0), b = markHash(i.x + 1.0 + i.y * 57.0);
    float c = markHash(i.x + (i.y + 1.0) * 57.0), d = markHash(i.x + 1.0 + (i.y + 1.0) * 57.0);
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
// x: reddened, y: blistered, z: charred, w: ash speckle, each 0..1 at this texel.
vec4 burnAt(vec2 t) {
    vec2 o = vec2(burnSeed * 13.1, burnSeed * 7.7);
    float f = 0.55 * burnNoise(t * 18.0 + o) + 0.3 * burnNoise(t * 41.0 + o) + 0.15 * burnNoise(t * 97.0 + o);
    float red = smoothstep(f - 0.15, f + 0.15, burnLevel * 1.6);
    float blister = smoothstep(0.3, 0.6, burnLevel) * smoothstep(0.75, 0.85, burnNoise(t * 170.0 + o)) * red;
    float charred = smoothstep(f - 0.08, f + 0.08, (burnLevel - 0.5) * 1.8);
    return vec4(red, blister * (1.0 - charred), charred, step(0.85, burnNoise(t * 260.0 + o)));
}
)glsl";

static const char* const woundSkinFragment = R"glsl(
""")
sub("""float markHash(float x) { return fract(sin(x * 12.9898) * 43758.5453); }
void main() {
    vec4 base = textureLod(baseTex, texUv, 0.0);
    vec3 tint = vec3(1.0);
""", """void main() {
    vec4 base = textureLod(baseTex, texUv, 0.0);
    vec3 tint = vec3(1.0);
    if (burnLevel > 0.0) {
        vec4 b = burnAt(texUv);
        tint = mix(vec3(1.0), vec3(1.0, 0.62, 0.52), b.x * 0.8);
        tint = mix(tint, vec3(1.15, 1.02, 0.82), b.y * 0.7);
        tint = mix(tint, mix(vec3(0.1, 0.07, 0.05), vec3(0.35, 0.33, 0.3), b.w), b.z);
    }
""")
sub("""static const char* const woundSkinNormalFragment = R"glsl(#version 130
""", """static const char* const woundSkinNormalFragment = R"glsl(
""")
sub("""    vec2 slope = vec2(dFdx(h) * texSize.x, dFdy(h) * texSize.y) / max(cmPerUv, vec2(1e-4));""",
    """    vec2 slope = vec2(dFdx(h) * texSize.x, dFdy(h) * texSize.y) / max(cmPerUv, vec2(1e-4));
    if (burnLevel > 0.0) {
        // Blisters rise; charred skin cracks. About 150 cm of body to the texture's width.
        vec4 b = burnAt(texUv);
        float hb = 0.12 * b.y - 0.05 * b.z * step(0.6, burnNoise(texUv * 120.0));
        slope += vec2(dFdx(hb) * texSize.x, dFdy(hb) * texSize.y) / 150.0;
    }""")
sub("""static const char* const woundSkinSpecFragment = R"glsl(#version 130
""", """static const char* const woundSkinSpecFragment = R"glsl(
""")
sub("""    vec3 spec = vec3(mix(0.12, 0.75, wet), mix(0.25, 0.9, wet), 0.0); // strength, gloss, metal
    fragColor = vec4(mix(base.rgb, spec, blood), base.a);""", """    vec3 spec = vec3(mix(0.12, 0.75, wet), mix(0.25, 0.9, wet), 0.0); // strength, gloss, metal
    vec3 skin = base.rgb;
    if (burnLevel > 0.0) {
        vec4 b = burnAt(texUv);
        skin = mix(skin, vec3(0.5, 0.8, 0.0), b.y);   // blisters: wet and glossy
        skin = mix(skin, vec3(0.03, 0.08, 0.0), b.z); // char: dull
    }
    fragColor = vec4(mix(skin, spec, blood), base.a);""")
# Programs: head + body.
sub("""static GLuint woundSkinProgram(gl::Api& g, const char* fragmentText) {
    auto compile = [&](GLenum type, const char* text) -> GLuint {
        const GLuint shader = g.createShader(type);
        if (!shader) return 0;
        g.shaderSource(shader, 1, &text, nullptr);""", """static GLuint woundSkinProgram(gl::Api& g, const char* fragmentText) {
    auto compile = [&](GLenum type, const char* text) -> GLuint {
        const GLuint shader = g.createShader(type);
        if (!shader) return 0;
        const char* parts[2] = {woundSkinFragmentHead, text};
        if (type == glc::vertexShader) g.shaderSource(shader, 1, &text, nullptr);
        else g.shaderSource(shader, 2, parts, nullptr);""")

# Slots keyed by the scene node.
sub("""static void woundSkinAssign() {
    bool wanted[woundSkinLimit]{};
    for (const Wound& w : woundStore) {
        if (!w.part || !w.mapped) continue;
        unsigned k = 0;
        while (k < woundSkinLimit && woundSkinSlots[k].character != w.owner) ++k;
        if (k == woundSkinLimit) {
            k = 0;
            while (k < woundSkinLimit && woundSkinSlots[k].character) ++k;
            if (k == woundSkinLimit) continue;
            woundSkinSlots[k] = {};
            woundSkinSlots[k].character = w.owner;
            __try { woundSkinSlots[k].actor = *(const uintptr_t*)(w.owner + field::character::sceneNode); }
            __except (EXCEPTION_EXECUTE_HANDLER) { woundSkinSlots[k] = {}; continue; }
        }
        wanted[k] = true;
    }
    for (unsigned k = 0; k < woundSkinLimit; ++k)
        if (!wanted[k] && woundSkinSlots[k].character) woundSkinSlots[k] = {}; // its texture is kept for the next one
}""", """// The slots follow the characters (by scene node) with mapped marks or a burn; woundLock held.
static void woundSkinAssign() {
    bool wanted[woundSkinLimit]{};
    auto claim = [&](uintptr_t actor, uintptr_t character) {
        if (!actor) return;
        unsigned k = 0;
        while (k < woundSkinLimit && woundSkinSlots[k].actor != actor) ++k;
        if (k == woundSkinLimit) {
            k = 0;
            while (k < woundSkinLimit && woundSkinSlots[k].actor) ++k;
            if (k == woundSkinLimit) return;
            woundSkinSlots[k] = {};
            woundSkinSlots[k].actor = actor;
        }
        if (character) woundSkinSlots[k].character = character;
        wanted[k] = true;
    };
    for (const Wound& w : woundStore)
        if (w.part && w.mapped) claim(w.actor, w.owner);
    for (int b = 0; b < woundBurnCount; ++b)
        if (woundBurns[b].level) claim(woundBurns[b].actor, 0);
    for (unsigned k = 0; k < woundSkinLimit; ++k)
        if (!wanted[k] && woundSkinSlots[k].actor) woundSkinSlots[k] = {}; // its texture is kept for the next one
}""")
sub("""        w.skinNode = node;""", """        w.skinNode = node;
        w.actor = actor;""")
sub("""        if (woundSkinSlots[k].character && woundSkinSlots[k].actor == parent) return int(k);""",
    """        if (woundSkinSlots[k].actor && woundSkinSlots[k].actor == parent) return int(k);""")
# Bake: burn-only slots, the full-texture quad, the burn uniforms.
sub("""            if (!slot.character || !slot.diffuse.source || slot.diffuse.failed) continue;""",
    """            if (!slot.actor || !slot.diffuse.source || slot.diffuse.failed) continue;
            const float burn = woundBurnLevel(slot.actor);""")
sub("""            float P[woundSkinMarks][4], Q[woundSkinMarks][4], R[woundSkinMarks][4], corners[woundSkinMarks * 6][2];""",
    """            float P[woundSkinMarks][4], Q[woundSkinMarks][4], R[woundSkinMarks][4], corners[woundSkinMarks * 6 + 6][2];""")
sub("""                if (!w.part || !w.mapped || w.owner != slot.character || count == woundSkinMarks) continue;""",
    """                if (!w.part || !w.mapped || !slot.character || w.owner != slot.character || count == woundSkinMarks) continue;""")
sub("""            if (!count) continue;""", """            if (!count && burn <= 0.f) continue;
            // A burn covers the whole skin: one more quad over all of UV space.
            unsigned vertices = count * 6;
            if (burn > 0.f) {
                const float all[6][2] = {{0.f, 0.f}, {1.f, 0.f}, {0.f, 1.f}, {0.f, 1.f}, {1.f, 0.f}, {1.f, 1.f}};
                memcpy(corners[vertices], all, sizeof all);
                vertices += 6;
            }""")
sub("""                g.uniform2f(g.getUniformLocation(program, "texSize"), float(map.width), float(map.height));""",
    """                g.uniform2f(g.getUniformLocation(program, "texSize"), float(map.width), float(map.height));
                g.uniform1f(g.getUniformLocation(program, "burnLevel"), burn);
                g.uniform1f(g.getUniformLocation(program, "burnSeed"), float(slot.actor % 997) / 997.f);""")
sub("""                g.bufferData(glc::arrayBuffer, ptrdiff_t(count * 6 * 8), corners, glc::dynamicDraw);""",
    """                g.bufferData(glc::arrayBuffer, ptrdiff_t(vertices * 8), corners, glc::dynamicDraw);""")
sub("""                glDrawArrays(GL_TRIANGLES, 0, GLsizei(count * 6));""", """                glDrawArrays(GL_TRIANGLES, 0, GLsizei(vertices));""")
p.write_text(t, encoding="utf-8")
print("ok")
