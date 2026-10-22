"""Dismemberment stage 1 (visual) into an ExCamera copy with wounds-12 (CRLF files), plus the bake source
in tools/. Inert until Injuries sets the "injuries.severed" mark, which it does only after the runtime's
requested characters.sever cut the joint:
- the severed character's skin draws in three parts: the body, the limb (the faces weighted to the
  severed bones) and, left out, the band of faces that bridged the joint;
- a flesh-and-bone cap closes the stump and the severed end, drawn by the wound pass as a disc at the
  band's ring (the ring's bind positions carried by the parent bone, and by the severed bone).
Usage: python apply_sever1.py <excamera root>"""
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


# ---- stone_skin.inl: a face state that is left out ----
edit("mod/stone_skin.inl", [
    ("""                while (end < plan.count && stone[end] == stone[f]) ++end;
""", """                while (end < plan.count && stone[end] == stone[f]) ++end;
                if (stone[f] == 2) { // left out: a severed limb's torn band (wounds_bake.inl)
                    f = end;
                    continue;
                }
"""),
])

# ---- wounds.inl: the severed bits, the caps' uniforms ----
edit("mod/wounds.inl", [
    ("""    bool any() const { return count || drips || burning; }""",
     """    unsigned caps = 0;          // flesh caps on severed limbs: stump and end
    float capA[8][4], capB[8][4]; // centre (view space), radius (cm); facing (view space), 0 stump / 1 the severed end
    bool any() const { return count || drips || burning || caps; }"""),
    ("""static float woundBurnLevel(uintptr_t actor) { return woundLevelOf(woundBurns, woundBurnCount, actor); }""",
     """static float woundBurnLevel(uintptr_t actor) { return woundLevelOf(woundBurns, woundBurnCount, actor); }
// Injuries' "injuries.severed": one bit per limb bone cut off (the "injuries.broken" bits); woundLock.
static WoundBurn woundSevered[64];
static int woundSeveredCount = 0;
static uint32_t woundSeveredBits(uintptr_t actor) {
    for (int b = 0; b < woundSeveredCount; ++b)
        if (woundSevered[b].actor == actor) return woundSevered[b].level;
    return 0;
}
static void woundSeveredCaps(const float* view, WoundUniforms& out); // wounds_bake.inl"""),
    ("""        woundReadLevels(marks, "injuries.burnscar", woundBurnScars, woundBurnScarCount);""",
     """        woundReadLevels(marks, "injuries.burnscar", woundBurnScars, woundBurnScarCount);
        woundReadLevels(marks, "injuries.severed", woundSevered, woundSeveredCount);"""),
    ("""    out.drips = dripCount;""", """    out.drips = dripCount;
    woundSeveredCaps(view, out);"""),
])

# ---- view_effects.inl: caps in the wound pass ----
edit("mod/view_effects.inl", [
    ("""uniform float dripCount;
""", """uniform float dripCount;
uniform vec4 capA[8];      // a flesh cap on a severed limb: view-space centre; w: radius (cm)
uniform vec4 capB[8];      // its facing (view space); w: 0 the stump, 1 the severed end
uniform float capCount;
"""),
    ("""vec3 woundMarks(vec3 color) {
    if (uv.x < woundRect.x || uv.y < woundRect.y || uv.x > woundRect.z || uv.y > woundRect.w) return color;
    float raw = texture2D(depthTex, uv).r;
    if (raw >= skyDepth) return color;
    vec3 p = viewPosition(uv, raw);""", """// A severed limb's cap where the view ray meets it in front of the scene: raw flesh around a pale bone
// with its marrow, a rim of skin and fat, lit from above and scaled by the skin's light around it.
// Opaque; 0 coverage elsewhere.
vec4 capAt(vec3 p) {
    vec3 ray = normalize(p);
    for (int k = 0; k < 8; ++k) {
        if (float(k) >= capCount) break;
        vec4 A = capA[k], B = capB[k];
        float facing = dot(ray, B.xyz);
        if (abs(facing) < 1e-3) continue;
        float t = dot(A.xyz, B.xyz) / facing;
        if (t <= 0.0 || t > length(p) + 2.0) continue; // behind the camera, or the scene stands in front
        vec3 hit = ray * t - A.xyz;
        float r = length(hit) / A.w;
        if (r > 1.0) continue;
        vec3 n = facing < 0.0 ? B.xyz : -B.xyz;
        vec3 flesh = mix(vec3(0.45, 0.06, 0.05), vec3(0.32, 0.03, 0.03), smoothstep(0.3, 0.8, sin(hit.x * 1.7) * sin(hit.y * 2.3) * 0.5 + 0.5));
        vec3 c = mix(flesh, vec3(0.78, 0.6, 0.45), smoothstep(0.82, 0.95, r));         // skin and fat at the rim
        c = mix(c, vec3(0.85, 0.8, 0.68), 1.0 - smoothstep(0.24, 0.3, r));             // the bone
        c = mix(c, vec3(0.35, 0.08, 0.06), 1.0 - smoothstep(0.09, 0.13, r));           // its marrow
        vec3 side = normalize(cross(B.xyz, abs(B.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
        float around = dot(toLight(texture2D(sceneTex, project(A.xyz + side * A.w * 1.4)).rgb), vec3(0.2126, 0.7152, 0.0722));
        vec3 lightDir = normalize(worldUp.xyz * 0.8 + vec3(0.0, 0.0, 0.6));
        float shade = 0.35 + 0.65 * max(dot(n, lightDir), 0.0);
        return vec4(toStored(clamp(c * shade * min(around * 2.5 + 0.02, 1.2), 0.0, 1.0)), 1.0);
    }
    return vec4(0.0);
}

vec3 woundMarks(vec3 color) {
    if (uv.x < woundRect.x || uv.y < woundRect.y || uv.x > woundRect.z || uv.y > woundRect.w) return color;
    float raw = texture2D(depthTex, uv).r;
    if (capCount > 0.0) {
        vec4 cap = capAt(viewPosition(uv, min(raw, skyDepth)));
        if (cap.a > 0.0) return cap.rgb;
    }
    if (raw >= skyDepth) return color;
    vec3 p = viewPosition(uv, raw);"""),
    (""", viewUniformCount
""", """, uCapA, uCapB, uCapCount, viewUniformCount
"""),
    ("""{float(finishMode && (request.wounds.count || request.wounds.drips)), &r.woundProgram,""",
     """{float(finishMode && (request.wounds.count || request.wounds.drips || request.wounds.caps)), &r.woundProgram,"""),
    ("""        if (finishMode && (request.wounds.count || request.wounds.drips) && r.woundProgram && g.uniform4fv && projection.worldUpValid &&""",
     """        if (finishMode && (request.wounds.count || request.wounds.drips || request.wounds.caps) && r.woundProgram && g.uniform4fv &&
            projection.worldUpValid &&"""),
    ("""        // Each drop's reach: from 20 to 200 cm below where it fell, three radii across.""",
     """        // Each cap's disc.
        for (unsigned k = 0; k < wounds.caps && box[2] - box[0] < 1.f; ++k) {
            const float* c = wounds.capA[k];
            const float reach = c[3] * 1.5f, depth = -c[2];
            if (!(depth - reach > 1.f)) { box[0] = box[1] = 0.f; box[2] = box[3] = 1.f; break; }
            const float sx = (projection.p0 * c[0] / depth - projection.p8) * 0.5f + 0.5f;
            const float sy = (projection.p5 * c[1] / depth - projection.p9) * 0.5f + 0.5f;
            const float rx = std::abs(projection.p0) * reach / (depth - reach) * 0.5f;
            const float ry = std::abs(projection.p5) * reach / (depth - reach) * 0.5f;
            box[0] = (std::min)(box[0], sx - rx); box[1] = (std::min)(box[1], sy - ry);
            box[2] = (std::max)(box[2], sx + rx); box[3] = (std::max)(box[3], sy + ry);
        }
        // Each drop's reach: from 20 to 200 cm below where it fell, three radii across."""),
    ("""                if (wounds.drips) g.uniform4fv(u.at[uDripA], GLsizei(wounds.drips), &wounds.d[0][0]);""",
     """                if (wounds.drips) g.uniform4fv(u.at[uDripA], GLsizei(wounds.drips), &wounds.d[0][0]);
                g.uniform1f(u.at[uCapCount], float(wounds.caps));
                if (wounds.caps) {
                    g.uniform4fv(u.at[uCapA], GLsizei(wounds.caps), &wounds.capA[0][0]);
                    g.uniform4fv(u.at[uCapB], GLsizei(wounds.caps), &wounds.capB[0][0]);
                }"""),
])

# The names array: its closing line gets the caps' names (the enum's order).
CRLF, LF = chr(13) + chr(10), chr(10)
_p = root / "mod" / "view_effects.inl"
_t = _p.read_bytes().decode("utf-8").replace(CRLF, LF)
_start = _t.index("static const char* const viewUniformNames[viewUniformCount] = {")
_end = _t.index("};", _start)
_t = _t[:_end] + ', "capA", "capB", "capCount"' + _t[_end:]
_p.write_bytes(_t.replace(LF, CRLF).encode("utf-8"))

# ---- wounds_bake.inl (source): the cut, the band, the caps ----
bake_path = here / "wounds_bake.inl"
b = bake_path.read_text(encoding="utf-8").replace("\r\n", "\n")
b = subs(b, [
    ("""// ---- 3. draw ---""", """// ---- severed limbs (DISMEMBER-PLAN.md, stage 1) ------------------------------------------------

// The game's part indices (+0x468) each "injuries.severed" bit cuts off, top first; the top part's parent.
struct WoundCut { int parts[3]; int parent; };
static constexpr WoundCut woundCuts[8] = {
    {{1, 2, 3}, 0}, {{2, 3, -1}, 1}, {{4, 5, 6}, 0}, {{5, 6, -1}, 4},          // thighs (at the hip), shins (at the knee)
    {{11, 12, 16}, 10}, {{12, 16, -1}, 11}, {{14, 15, 17}, 13}, {{15, 17, -1}, 14}, // upper arms (shoulder), forearms (elbow)
};
constexpr unsigned woundBandSamples = 96;

// One severed mesh: per face 0 body, 1 limb, 2 the band (left out); per cut, the band ring's bind
// positions and the bones each side follows. Rebuilt when the mesh or its bits change.
struct WoundSeverMesh {
    uintptr_t node = 0, actor = 0;
    uint32_t bits = 0;
    std::vector<unsigned char> faces; // by face index (+0x290)
    struct Ring {
        int bit = -1, parentBone = -1, topBone = -1, farBone = -1; // far: the hand or foot, to face the end away from
        unsigned count = 0;
        float bind[woundBandSamples][3];
    } rings[8];
    unsigned ringCount = 0;
};
static WoundSeverMesh woundSeverMeshes[4]; // render thread

static int woundBonePart(const WoundSkinMesh& m, int k) {
    const uintptr_t transform = *(const uintptr_t*)(m.boneNodes + size_t(k) * 8);
    if (transform < field::sceneNode::transform) return -1;
    const uintptr_t node = transform - field::sceneNode::transform;
    const uintptr_t part = *(const uintptr_t*)(node + field::sceneNode::bodyPart);
    if (!part) return -1;
    const int index = *(const int*)(part + woundPartIndex);
    return index >= 0 && index < 18 ? index : -1;
}

static bool woundSeverBuild(uintptr_t node, uintptr_t actor, uint32_t bits, WoundSeverMesh& out) {
    WoundSkinMesh m;
    if (!woundSkinMesh(node, m)) return false;
    out = {};
    out.node = node;
    out.actor = actor;
    out.bits = bits;
    bool severedBone[fp::wear::maxBones]{};
    int boneOfPart[18];
    for (int& v : boneOfPart) v = -1;
    for (int k = 0; k < m.bones; ++k) {
        const int part = woundBonePart(m, k);
        if (part < 0) continue;
        if (boneOfPart[part] < 0) boneOfPart[part] = k;
        for (unsigned bit = 0; bit < 8; ++bit)
            if (bits & (1u << bit))
                for (int p : woundCuts[bit].parts)
                    if (p == part) severedBone[k] = true;
    }
    const auto* weights = (const fp::wear::Weights*)m.weights.data;
    auto share = [&](unsigned p) {
        float s = 0.f;
        for (int k = 0; k < 4; ++k)
            if (weights[p].bone[k] >= 1 && weights[p].bone[k] <= m.bones && severedBone[weights[p].bone[k] - 1] &&
                weights[p].weight[k] > 0.f)
                s += weights[p].weight[k];
        return s;
    };
    out.faces.assign(size_t(m.lastFace) + 1, 0);
    for (unsigned bit = 0; bit < 8; ++bit) {
        if (!(bits & (1u << bit)) || out.ringCount == 8) continue;
        auto& ring = out.rings[out.ringCount++];
        ring.bit = int(bit);
        ring.topBone = boneOfPart[woundCuts[bit].parts[0]];
        ring.parentBone = boneOfPart[woundCuts[bit].parent];
        for (int p : woundCuts[bit].parts)
            if (p >= 0 && boneOfPart[p] >= 0) ring.farBone = boneOfPart[p];
    }
    for (int f = 0; f <= m.lastFace; ++f) {
        const unsigned* tri = (const unsigned*)(m.triangles + size_t(f) * 12);
        int limb = 0;
        unsigned p[3];
        for (int c = 0; c < 3; ++c) {
            if (tri[c] > unsigned(m.lastVertex)) return false;
            p[c] = *(const unsigned*)(m.posIndices + size_t(tri[c]) * 4);
            if (p[c] >= m.positions.count) return false;
            limb += share(p[c]) >= 0.5f ? 1 : 0;
        }
        out.faces[size_t(f)] = limb == 3 ? 1 : limb == 0 ? 0 : 2;
        if (limb != 0 && limb != 3) // the band: its corners make the ring (to the nearest cut's sample list)
            for (unsigned r = 0; r < out.ringCount; ++r) {
                auto& ring = out.rings[r];
                for (int c = 0; c < 3 && ring.count < woundBandSamples; ++c)
                    memcpy(ring.bind[ring.count++], (const float*)(m.source + size_t(p[c]) * 12), 12);
                break; // one ring per mesh is enough for a single cut; several cuts share the first (stage 1)
            }
    }
    return true;
}

// The mesh's split for this draw, cached; null when the character has nothing severed.
static const WoundSeverMesh* woundSeverOf(uintptr_t node, uintptr_t actor) {
    const uint32_t bits = woundSeveredBits(actor) & 0xFF;
    if (!bits) return nullptr;
    for (const WoundSeverMesh& s : woundSeverMeshes)
        if (s.node == node && s.bits == bits) return &s;
    static unsigned next = 0;
    WoundSeverMesh& slot = woundSeverMeshes[next];
    next = (next + 1) % 4;
    if (!woundSeverBuild(node, actor, bits, slot)) { slot = {}; return nullptr; }
    return &slot;
}

// The caps: each ring carried by the parent bone (the stump) and by the severed bone (the end), as a
// disc through the ring's centre facing away from the bone's own centre. woundLock held.
static void woundSeveredCaps(const float* view, WoundUniforms& out) {
    out.caps = 0;
    for (const WoundSeverMesh& s : woundSeverMeshes) {
        if (!s.node || !(woundSeveredBits(s.actor) & s.bits)) continue;
        __try {
            WoundSkinMesh m;
            if (!woundSkinMesh(s.node, m)) continue;
            float sectorOrigin[3]{};
            const uintptr_t sector = *(const uintptr_t*)(s.node + field::sceneNode::sector);
            if (sector && readable(sector, field::sector::origin + 12))
                memcpy(sectorOrigin, (const void*)(sector + field::sector::origin), sizeof sectorOrigin);
            for (unsigned r = 0; r < s.ringCount && out.caps + 2 <= 8; ++r) {
                const auto& ring = s.rings[r];
                if (ring.count < 3 || ring.parentBone < 0 || ring.topBone < 0) continue;
                for (int side = 0; side < 2; ++side) {
                    const int bone = side ? ring.topBone : ring.parentBone;
                    float now[16], bind[16];
                    if (!fp::wear::affine((const float*)(*(const uintptr_t*)(m.boneNodes + size_t(bone) * 8)), now) ||
                        !fp::wear::affine((const float*)(m.inverseBind + size_t(bone) * 48), bind))
                        break;
                    float skin[16];
                    fp::wear::product(bind, now, skin); // bind position -> where this bone carries it now
                    float centre[3]{}, q[3];
                    for (unsigned v = 0; v < ring.count; ++v) {
                        if (!fp::wear::point(skin, ring.bind[v], q)) break;
                        for (int i = 0; i < 3; ++i) centre[i] += q[i] / float(ring.count);
                    }
                    float radius = 0.f;
                    for (unsigned v = 0; v < ring.count; ++v) {
                        fp::wear::point(skin, ring.bind[v], q);
                        radius += std::sqrt((q[0] - centre[0]) * (q[0] - centre[0]) + (q[1] - centre[1]) * (q[1] - centre[1]) +
                                            (q[2] - centre[2]) * (q[2] - centre[2])) / float(ring.count);
                    }
                    // Facing: the ring's own plane (its centre, a first point and the point making the widest
                    // angle with it), turned away from that side's flesh: the parent bone's origin for the
                    // stump, the hand's or foot's for the severed end.
                    float first[3], wide[3]{}, n[3]{};
                    fp::wear::point(skin, ring.bind[0], q);
                    for (int i = 0; i < 3; ++i) first[i] = q[i] - centre[i];
                    float widest = 0.f;
                    for (unsigned v = 1; v < ring.count; ++v) {
                        fp::wear::point(skin, ring.bind[v], q);
                        const float d[3] = {q[0] - centre[0], q[1] - centre[1], q[2] - centre[2]};
                        const float x[3] = {first[1] * d[2] - first[2] * d[1], first[2] * d[0] - first[0] * d[2],
                                            first[0] * d[1] - first[1] * d[0]};
                        const float sq = x[0] * x[0] + x[1] * x[1] + x[2] * x[2];
                        if (sq > widest) { widest = sq; memcpy(wide, x, sizeof wide); }
                    }
                    if (!(widest > 1e-6f) || !(radius > 0.5f) || radius > 30.f) break;
                    const float wl = 1.f / std::sqrt(widest);
                    for (int i = 0; i < 3; ++i) n[i] = wide[i] * wl;
                    const int refBone = side ? ring.farBone : ring.parentBone;
                    float ref[16];
                    if (refBone < 0 || !fp::wear::affine((const float*)(*(const uintptr_t*)(m.boneNodes + size_t(refBone) * 8)), ref)) break;
                    if (n[0] * (centre[0] - ref[12]) + n[1] * (centre[1] - ref[13]) + n[2] * (centre[2] - ref[14]) < 0.f)
                        for (float& v : n) v = -v;
                    const float* facing = n;
                    // The nearer reading of the sector origin, as for the marks.
                    float best[3]{}, bestSq = woundReachCm * woundReachCm;
                    bool found = false;
                    for (int candidate = 0; candidate < 2; ++candidate) {
                        float c[3];
                        for (int k = 0; k < 3; ++k) q[k] = centre[k] + (candidate ? sectorOrigin[k] : 0.f);
                        for (int k = 0; k < 3; ++k) c[k] = q[0] * view[k] + q[1] * view[4 + k] + q[2] * view[8 + k] + view[12 + k];
                        const float sq = c[0] * c[0] + c[1] * c[1] + c[2] * c[2];
                        if (std::isfinite(sq) && sq < bestSq) { bestSq = sq; memcpy(best, c, sizeof c); found = true; }
                    }
                    if (!found) break;
                    float dir[3];
                    for (int k = 0; k < 3; ++k) dir[k] = facing[0] * view[k] + facing[1] * view[4 + k] + facing[2] * view[8 + k];
                    const float a[4] = {best[0], best[1], best[2], radius * 1.1f};
                    const float bb[4] = {dir[0], dir[1], dir[2], float(side)};
                    memcpy(out.capA[out.caps], a, sizeof a);
                    memcpy(out.capB[out.caps], bb, sizeof bb);
                    ++out.caps;
                }
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            woundSkinFaults.fetch_add(1, std::memory_order_relaxed);
        }
    }
}

// ---- 3. draw ---"""),
    # The draw: severed characters split their faces; the copies are used when ready, else the originals.
    ("""struct WoundSkinSwap { unsigned slot; GLuint textures[3]; };
static const GLuint* woundSkinReplacement(fp::CueResources& r, const StoneGl&, const void* context) {
    auto* swap = (WoundSkinSwap*)const_cast<void*>(context);
    const unsigned k = swap->slot;
    if (!r.woundSkinTex[k]) return nullptr;""", """struct WoundSkinSwap { unsigned slot; GLuint textures[3]; bool ready; };
static const GLuint* woundSkinReplacement(fp::CueResources& r, const StoneGl&, const void* context) {
    auto* swap = (WoundSkinSwap*)const_cast<void*>(context);
    const unsigned k = swap->slot;
    if (!swap->ready) return swap->textures; // a severed character before its bake: its own maps
    if (!r.woundSkinTex[k]) return nullptr;"""),
    ("""    if (!woundSkinCurrent(slot, material, originals)) return false;
    WoundSkinSwap swap{unsigned(found), {originals[0], originals[1], originals[2]}};
    return skinFacesEmit(plan, bind, body.data(), originals, 3, woundSkinReplacement, &swap);""",
     """    const bool ready = woundSkinCurrent(slot, material, originals);
    // A severed limb: its faces draw with the limb, the band that bridged the joint is left out.
    const WoundSeverMesh* cut = woundSeverOf(node, slot.actor);
    if (!ready && !cut) return false;
    if (cut) {
        for (unsigned f = 0; f < plan.count; ++f) {
            const size_t face = size_t(plan.first) + f;
            if (face < cut->faces.size() && cut->faces[face] == 2) body[f] = 2;
        }
    }
    WoundSkinSwap swap{unsigned(found), {originals[0], originals[1], originals[2]}, ready};
    return skinFacesEmit(plan, bind, body.data(), originals, 3, woundSkinReplacement, &swap);"""),
    # Severed characters claim a slot too.
    ("""    for (int b = 0; b < woundBurnScarCount; ++b)
        if (woundBurnScars[b].level) claim(woundBurnScars[b].actor, 0);""", """    for (int b = 0; b < woundBurnScarCount; ++b)
        if (woundBurnScars[b].level) claim(woundBurnScars[b].actor, 0);
    for (int b = 0; b < woundSeveredCount; ++b)
        if (woundSevered[b].level) claim(woundSevered[b].actor, 0);"""),
], "wounds_bake.inl")
bake_path.write_text(b, encoding="utf-8")
(root / "mod" / "wounds_bake.inl").write_bytes(b.replace("\n", "\r\n").encode("utf-8"))
print("ok")
