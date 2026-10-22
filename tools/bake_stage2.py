"""tools/wounds_bake.inl stage 2: gash depth baked into the skin's normal map, the player's own
first-person body through the headwear path's swap, and a re-made skin (same material, new texture)
re-baking. Edits the source in tools/ in place (LF)."""
from pathlib import Path

p = Path(__file__).resolve().parent / "wounds_bake.inl"
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, (old[:80], t.count(old))
    t = t.replace(old, new)


sub("""// (view_effects.inl woundMarks), which leaves out the skin part of a baked mark.""",
    """// (view_effects.inl woundMarks), which leaves out the skin part of a baked mark. Stage 2: the gash's depth,
// lips and a bruise's swelling go into a copy of the normal map too (unit 2), and the player's own
// body in first person takes both copies through the headwear path's swap (stone_skin.inl).""")
sub("""struct WoundSkinSlot {
    uintptr_t character = 0, actor = 0; // the character and its scene node (character +0x18)
    GLuint source = 0;                  // the body material's own diffuse, recorded at its draw
    GLint width = 0, height = 0, levels = 0;
    GLenum format = 0;
    unsigned bakedVersion = 0;
    ULONGLONG bakedAt = 0;
    bool ready = false, failed = false;
};""", """struct WoundSkinMap { // one of the body material's maps and its copy's shape
    GLuint source = 0;
    GLint width = 0, height = 0, levels = 0;
    GLenum format = 0;
    bool failed = false;
};
struct WoundSkinSlot {
    uintptr_t character = 0, actor = 0; // the character and its scene node (character +0x18)
    uintptr_t material = 0;             // the body material whose maps were recorded at its draw
    WoundSkinMap diffuse, normal;       // units 0 and 2
    unsigned bakedVersion = 0;
    ULONGLONG bakedAt = 0;
    bool ready = false, normalReady = false;
};""")

# The texture helper takes which map.
sub("""static bool woundSkinTexture(fp::CueResources& r, const WoundSkinGl& s, unsigned k) {
    WoundSkinSlot& slot = woundSkinSlots[k];
    if (r.woundSkinTex[k] && slot.width && slot.format) return true;
    GLint width = 0, height = 0, format = 0;
    s.level(slot.source, 0, 0x1000 /* WIDTH */, &width);
    s.level(slot.source, 0, 0x1001 /* HEIGHT */, &height);
    s.level(slot.source, 0, 0x1003 /* INTERNAL_FORMAT */, &format);
    const bool colour = format == 0x8058 /* RGBA8 */ || format == 0x8C43 /* SRGB8_ALPHA8 */ ||
                        format == 0x8051 /* RGB8 */ || format == 0x8C41 /* SRGB8 */;
    if (width < 16 || height < 16 || width > 8192 || height > 8192 || !colour) { slot.failed = true; return false; }
    if (r.woundSkinTex[k]) { glDeleteTextures(1, &r.woundSkinTex[k]); r.woundSkinTex[k] = 0; }
    s.stone.create(GL_TEXTURE_2D, 1, &r.woundSkinTex[k]);
    if (!r.woundSkinTex[k]) { slot.failed = true; return false; }
    GLint levels = 1;
    for (GLint size = (std::max)(width, height); size > 1; size /= 2) ++levels;
    s.stone.storage(r.woundSkinTex[k], levels, GLenum(format), width, height);
    s.stone.parameter(r.woundSkinTex[k], 0x2801, 0x2703); // LINEAR_MIPMAP_LINEAR
    s.stone.parameter(r.woundSkinTex[k], 0x2800, 0x2601); // LINEAR
    slot.width = width;
    slot.height = height;
    slot.levels = levels;
    slot.format = GLenum(format);
    return true;
}""", """// A map's copy: the original's size and format (uncompressed 8-bit only; the normal map may be
// two-channel), full mip chain. `copy` is the context's texture name for it.
static bool woundSkinTexture(const WoundSkinGl& s, WoundSkinMap& map, unsigned& copy) {
    if (copy && map.width && map.format) return true;
    GLint width = 0, height = 0, format = 0;
    s.level(map.source, 0, 0x1000 /* WIDTH */, &width);
    s.level(map.source, 0, 0x1001 /* HEIGHT */, &height);
    s.level(map.source, 0, 0x1003 /* INTERNAL_FORMAT */, &format);
    const bool plain = format == 0x8058 /* RGBA8 */ || format == 0x8C43 /* SRGB8_ALPHA8 */ || format == 0x8051 /* RGB8 */ ||
                       format == 0x8C41 /* SRGB8 */ || format == 0x822B /* RG8 */;
    if (width < 16 || height < 16 || width > 8192 || height > 8192 || !plain) { map.failed = true; return false; }
    if (copy) { glDeleteTextures(1, &copy); copy = 0; }
    s.stone.create(GL_TEXTURE_2D, 1, &copy);
    if (!copy) { map.failed = true; return false; }
    GLint levels = 1;
    for (GLint size = (std::max)(width, height); size > 1; size /= 2) ++levels;
    s.stone.storage(copy, levels, GLenum(format), width, height);
    s.stone.parameter(copy, 0x2801, 0x2703); // LINEAR_MIPMAP_LINEAR
    s.stone.parameter(copy, 0x2800, 0x2601); // LINEAR
    map.width = width;
    map.height = height;
    map.levels = levels;
    map.format = GLenum(format);
    return true;
}""")

# The normal pass's fragment shader.
sub("""static GLuint woundSkinProgram(gl::Api& g) {""", """// The normal map's copy: the marks' height (cm) as a slope on the map's tangent-space x/y, the way the
// game's skin shading reads it (shading.flb shadesss_f: xy * 2 - 1, x along the vertex tangent, y along
// normal x tangent times its sign; taken here as +u and +v, inferred). Screen derivatives of the UV-space
// render are per texel; each slope is scaled by the cm per UV of the mark nearest the texel.
static const char* const woundSkinNormalFragment = R"glsl(#version 130
uniform sampler2D baseTex;
uniform vec4 markP[16];
uniform vec4 markQ[16];
uniform vec4 markR[16];
uniform float markCount;
uniform vec2 texSize;
in vec2 texUv;
out vec4 fragColor;
void main() {
    vec4 base = textureLod(baseTex, texUv, 0.0);
    float h = 0.0, best = 1e9;
    vec2 cmPerUv = vec2(1.0);
    for (int i = 0; i < 16; ++i) {
        if (float(i) >= markCount) break;
        vec4 P = markP[i], Q = markQ[i], R = markR[i];
        vec2 o = texUv - P.xy;
        vec2 q = vec2(dot(P.zw, o), dot(Q.xy, o));
        float kind = floor(R.x + 0.01);
        float severity = R.y, seed = R.z, near;
        if (kind == 2.0) {
            float r = length(q) / Q.z;
            h += 0.15 * severity * (1.0 - smoothstep(0.0, 1.0, r)); // the swelling
            near = r;
        } else {
            float a = q.x / Q.z;
            float taper = sqrt(max(1.0 - a * a, 0.0));
            float wobble = 0.22 * Q.w * sin(a * 5.0 + seed * 40.0);
            float x = abs(q.y - wobble) / max(Q.w * (0.25 + 0.75 * taper), 0.05);
            float lip = taper * smoothstep(0.7, 1.1, x) * (1.0 - smoothstep(1.3, 2.4, x));
            h += -0.4 * severity * taper * (1.0 - smoothstep(0.0, 1.0, x)) + 0.12 * severity * lip; // the gash, its lips
            near = max(abs(a), x * 0.25);
        }
        if (near < best) {
            best = near;
            cmPerUv = vec2(length(vec2(P.z, Q.x)), length(vec2(P.w, Q.y)));
        }
    }
    vec2 slope = vec2(dFdx(h) * texSize.x, dFdy(h) * texSize.y) / max(cmPerUv, vec2(1e-4));
    vec2 n = clamp(base.xy * 2.0 - 1.0 - slope, vec2(-0.95), vec2(0.95));
    fragColor = vec4(n * 0.5 + 0.5, base.z, base.w);
}
)glsl";

static GLuint woundSkinProgram(gl::Api& g, const char* fragmentText) {""")
sub("""    const GLuint vertex = compile(glc::vertexShader, woundSkinVertex), fragment = compile(glc::fragmentShader, woundSkinFragment);""",
    """    const GLuint vertex = compile(glc::vertexShader, woundSkinVertex), fragment = compile(glc::fragmentShader, fragmentText);""")

# Slot assignment resets the maps.
sub("""            woundSkinSlots[k] = {};
            woundSkinSlots[k].character = w.owner;""", """            woundSkinSlots[k] = {};
            woundSkinSlots[k].character = w.owner;""")

# Bake: programs, both maps.
sub("""    if (!r.woundBakeProgram) {
        r.woundBakeProgram = woundSkinProgram(g);
        if (!r.woundBakeProgram) { woundSkinBroken = true; return; }""", """    if (!r.woundBakeProgram) {
        r.woundBakeProgram = woundSkinProgram(g, woundSkinFragment);
        r.woundBakeNormalProgram = woundSkinProgram(g, woundSkinNormalFragment); // none: colour only
        if (!r.woundBakeProgram) { woundSkinBroken = true; return; }""")
sub("""            if (!slot.character || !slot.source || slot.failed) continue;""",
    """            if (!slot.character || !slot.diffuse.source || slot.diffuse.failed) continue;""")
sub("""            if (!woundSkinTexture(r, s, k)) continue;
            // The original into the copy, then the marks over it.
            s.copy(slot.source, GL_TEXTURE_2D, 0, 0, 0, 0, r.woundSkinTex[k], GL_TEXTURE_2D, 0, 0, 0, 0, slot.width, slot.height, 1);
            g.bindFramebuffer(glc::framebuffer, r.woundBakeFbo);
            g.framebufferTexture2D(glc::framebuffer, glc::colorAttachment0, GL_TEXTURE_2D, r.woundSkinTex[k], 0);
            if (!slot.ready && g.checkFramebufferStatus(glc::framebuffer) != glc::framebufferComplete) { slot.failed = true; continue; }
            setViewport(g, 0, 0, slot.width, slot.height);
            glDisable(GL_BLEND);
            glDisable(GL_DEPTH_TEST);
            glDisable(GL_CULL_FACE);
            glDisable(GL_SCISSOR_TEST);
            glDisable(GL_STENCIL_TEST);
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
            const bool srgb = slot.format == 0x8C43 || slot.format == 0x8C41;
            (srgb ? glEnable : glDisable)(glc::framebufferSrgb);
            g.useProgram(r.woundBakeProgram);
            g.activeTexture(glc::texture0);
            g.bindTexture(GL_TEXTURE_2D, slot.source);
            if (g.bindSampler) g.bindSampler(0, 0);
            g.uniform1i(g.getUniformLocation(r.woundBakeProgram, "baseTex"), 0);
            g.uniform1f(g.getUniformLocation(r.woundBakeProgram, "markCount"), float(count));
            g.uniform4fv(g.getUniformLocation(r.woundBakeProgram, "markP"), GLsizei(count), &P[0][0]);
            g.uniform4fv(g.getUniformLocation(r.woundBakeProgram, "markQ"), GLsizei(count), &Q[0][0]);
            g.uniform4fv(g.getUniformLocation(r.woundBakeProgram, "markR"), GLsizei(count), &R[0][0]);
            g.bindVertexArray(r.woundBakeVao);
            g.bindBuffer(glc::arrayBuffer, r.woundBakeVbo);
            g.bufferData(glc::arrayBuffer, ptrdiff_t(count * 6 * 8), corners, glc::dynamicDraw);
            g.vertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 8, nullptr);
            g.enableVertexAttribArray(0);
            glDrawArrays(GL_TRIANGLES, 0, GLsizei(count * 6));
            s.mipmap(r.woundSkinTex[k]);
            slot.bakedVersion = woundSkinVersion;""", """            // Each map: the original into the copy, then the marks over it in UV space, then mipmaps.
            auto bakeMap = [&](WoundSkinMap& map, unsigned& copy, GLuint program, bool known) -> bool {
                if (!program || !map.source || map.failed || !woundSkinTexture(s, map, copy)) return false;
                s.copy(map.source, GL_TEXTURE_2D, 0, 0, 0, 0, copy, GL_TEXTURE_2D, 0, 0, 0, 0, map.width, map.height, 1);
                g.bindFramebuffer(glc::framebuffer, r.woundBakeFbo);
                g.framebufferTexture2D(glc::framebuffer, glc::colorAttachment0, GL_TEXTURE_2D, copy, 0);
                if (!known && g.checkFramebufferStatus(glc::framebuffer) != glc::framebufferComplete) { map.failed = true; return false; }
                setViewport(g, 0, 0, map.width, map.height);
                glDisable(GL_BLEND);
                glDisable(GL_DEPTH_TEST);
                glDisable(GL_CULL_FACE);
                glDisable(GL_SCISSOR_TEST);
                glDisable(GL_STENCIL_TEST);
                glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
                const bool srgb = map.format == 0x8C43 || map.format == 0x8C41;
                (srgb ? glEnable : glDisable)(glc::framebufferSrgb);
                g.useProgram(program);
                g.activeTexture(glc::texture0);
                g.bindTexture(GL_TEXTURE_2D, map.source);
                if (g.bindSampler) g.bindSampler(0, 0);
                g.uniform1i(g.getUniformLocation(program, "baseTex"), 0);
                g.uniform1f(g.getUniformLocation(program, "markCount"), float(count));
                g.uniform2f(g.getUniformLocation(program, "texSize"), float(map.width), float(map.height));
                g.uniform4fv(g.getUniformLocation(program, "markP"), GLsizei(count), &P[0][0]);
                g.uniform4fv(g.getUniformLocation(program, "markQ"), GLsizei(count), &Q[0][0]);
                g.uniform4fv(g.getUniformLocation(program, "markR"), GLsizei(count), &R[0][0]);
                g.bindVertexArray(r.woundBakeVao);
                g.bindBuffer(glc::arrayBuffer, r.woundBakeVbo);
                g.bufferData(glc::arrayBuffer, ptrdiff_t(count * 6 * 8), corners, glc::dynamicDraw);
                g.vertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 8, nullptr);
                g.enableVertexAttribArray(0);
                glDrawArrays(GL_TRIANGLES, 0, GLsizei(count * 6));
                s.mipmap(copy);
                return true;
            };
            if (!bakeMap(slot.diffuse, r.woundSkinTex[k], r.woundBakeProgram, slot.ready)) continue;
            slot.normalReady = bakeMap(slot.normal, r.woundSkinNrm[k], r.woundBakeNormalProgram, slot.normalReady);
            slot.bakedVersion = woundSkinVersion;""")

# Draw: three units (diffuse copy, the material's own specular, normal copy or the original).
sub("""static const GLuint* woundSkinReplacement(fp::CueResources& r, const StoneGl&, const void* slot) {
    const unsigned k = *(const unsigned*)slot;
    return r.woundSkinTex[k] ? &r.woundSkinTex[k] : nullptr;
}""", """struct WoundSkinSwap { unsigned slot; GLuint textures[3]; };
static const GLuint* woundSkinReplacement(fp::CueResources& r, const StoneGl&, const void* context) {
    auto* swap = (WoundSkinSwap*)const_cast<void*>(context);
    const unsigned k = swap->slot;
    if (!r.woundSkinTex[k]) return nullptr;
    swap->textures[0] = r.woundSkinTex[k];
    if (woundSkinSlots[k].normalReady && r.woundSkinNrm[k]) swap->textures[2] = r.woundSkinNrm[k];
    return swap->textures;
}

// Records the body material's maps on its first draw (or when the game re-made that material's
// textures); true when the slot's copies stand for exactly these originals.
static bool woundSkinCurrent(WoundSkinSlot& slot, uintptr_t material, const GLuint* originals) {
    if (slot.material && slot.material != material) return false; // another part of the mesh keeps its own maps
    if (slot.material == material && slot.diffuse.source == originals[0] && slot.normal.source == originals[2]) return slot.ready;
    slot.material = material;
    slot.diffuse = {};
    slot.normal = {};
    slot.diffuse.source = originals[0];
    slot.normal.source = originals[2];
    slot.ready = slot.normalReady = false;
    slot.bakedVersion = 0;
    return false;
}""")
sub("""    // The first body material drawn gives the diffuse the bake copies; another material of the same
    // mesh (a second skin part) keeps its own texture and draws natively.
    if (!slot.source) {
        slot.source = originals[0];
        slot.ready = slot.failed = false;
        slot.width = 0;
        return false;
    }
    if (slot.source != originals[0]) return false;
    if (!slot.ready) return false;
    const unsigned k = unsigned(found);
    return skinFacesEmit(plan, bind, body.data(), originals, 1, woundSkinReplacement, &k);""",
    """    if (!woundSkinCurrent(slot, material, originals)) return false;
    WoundSkinSwap swap{unsigned(found), {originals[0], originals[1], originals[2]}};
    return skinFacesEmit(plan, bind, body.data(), originals, 3, woundSkinReplacement, &swap);""")

# The player's own body in first person: the headwear path's swap.
t += """
// The player's own skinned mesh in first person stays with the headwear path, which swaps maps for the
// body's runs through StoneSwap (stone_skin.inl falls back to this when the player is not stone).
static bool woundSkinWearBegin(uintptr_t node, uintptr_t material, StoneSwap& swap) {
    swap = {};
    if (woundSkinBroken || !wearScope.colourPass) return false;
    __try {
        const int found = woundSkinSlotOf(node);
        if (found < 0 || !stoneSkinOriginals(material, swap.originals)) return false;
        WoundSkinSlot& slot = woundSkinSlots[found];
        if (!woundSkinCurrent(slot, material, swap.originals)) return false;
        StoneGl s{};
        if (!loadStoneGl(s)) return false;
        auto* owner = prepareCue();
        if (!owner || !owner->resources.woundSkinTex[found]) return false;
        swap.stone[0] = owner->resources.woundSkinTex[found];
        swap.stone[1] = swap.originals[1];
        swap.stone[2] = slot.normalReady && owner->resources.woundSkinNrm[found] ? owner->resources.woundSkinNrm[found]
                                                                                   : swap.originals[2];
        swap.bind = s.bind;
        swap.on = true;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        woundSkinFaults.fetch_add(1, std::memory_order_relaxed);
        swap = {};
    }
    if (swap.on) woundSkinDraws.fetch_add(1, std::memory_order_relaxed);
    return swap.on;
}
"""
p.write_text(t, encoding="utf-8")
print("ok")
