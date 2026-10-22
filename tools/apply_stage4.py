"""Stage 4 into an ExCamera copy with wounds-09 (CRLF files): burns baked into the skin (wounds_bake.inl,
from tools/), blood drips on the floor under bleeding cuts (wounds.inl, the wound pass), burn levels
from Injuries' "injuries.burn" mark. Usage: python apply_stage4.py <excamera root>"""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"
here = Path(__file__).resolve().parent


def edit(rel, pairs):
    p = root / rel
    t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        assert t.count(old) == 1, (rel, old[:80], t.count(old))
        t = t.replace(old, new)
    p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))


bake = (here / "wounds_bake.inl").read_text(encoding="utf-8").replace("\r\n", "\n")
(root / "mod" / "wounds_bake.inl").write_bytes(bake.replace("\n", "\r\n").encode("utf-8"))

edit("mod/wounds.inl", [
    ("""    int8_t partIndex = -1; // the struck part's index (+0x468), 0..17
""", """    int8_t partIndex = -1; // the struck part's index (+0x468), 0..17
    uintptr_t actor = 0;   // the character's scene node, once mapped (wounds_bake.inl)
    float drip = 0.f;      // counts up to the next drop of blood falling from a bleeding cut
"""),
    ("""struct WoundUniforms {
    unsigned count = 0;""", """constexpr unsigned woundDripLimit = 96, woundDripShown = 24;
constexpr float woundDripSeconds = 120.f, woundDripDrySeconds = 30.f;
struct WoundUniforms {
    unsigned count = 0;
    unsigned drips = 0;      // blood drops on the floor, below
    bool burning = false;    // a character in view is burnt (the skin bake has work)
    float d[woundDripShown][4]; // a drop: view-space point it fell from; w: radius (cm) + 10 x dryness step (0..9)
    bool any() const { return count || drips || burning; }"""),
    ("""static unsigned woundSkinVersion = 1; // woundLock: bumped when a baked (mapped) mark changes or goes""",
     """static unsigned woundSkinVersion = 1; // woundLock: bumped when a baked (mapped) mark changes or goes
// Injuries' "injuries.burn" mark: a burn level (0..255) per character scene node, read each frame; woundLock.
struct WoundBurn { uintptr_t actor; uint32_t level; };
static WoundBurn woundBurns[64];
static int woundBurnCount = 0;
static float woundBurnLevel(uintptr_t actor) {
    for (int b = 0; b < woundBurnCount; ++b)
        if (woundBurns[b].actor == actor) return float(woundBurns[b].level) / 255.f;
    return 0.f;
}
// Drops of blood fallen from bleeding cuts: where they fell from (the cut, sector-local) and its sector's
// origin; the wound pass draws each on the first upward surface 20..200 cm below. woundLock.
struct WoundDrip { float from[3], sectorOrigin[3], radius; ULONGLONG born; };
static WoundDrip woundDrips[96];
static unsigned woundDripNext = 0;"""),
    # Burn marks read each frame.
    ("""    const float fadeDt = woundFadeTick ? (std::min)(float(now - woundFadeTick) / 1000.f, 0.5f) : 0.f;""",
     """    {
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
    }
    const float fadeDt = woundFadeTick ? (std::min)(float(now - woundFadeTick) / 1000.f, 0.5f) : 0.f;"""),
    # Drops: counted while bleeding, made once the cut's place is known.
    ("""            if (flow > 0.02f) w.run = (std::min)(w.run + fadeDt * (0.4f + 1.6f * flow), 4.f + 14.f * w.severity);""",
     """            if (flow > 0.02f) w.run = (std::min)(w.run + fadeDt * (0.4f + 1.6f * flow), 4.f + 14.f * w.severity);
            if (flow > 0.15f) w.drip += fadeDt * flow * 2.f; // up to two drops a second while it pours"""),
    ("""        float world[3], path[3];
        outOfPose(pose, w.local, true, world);
        outOfPose(pose, w.along, false, path);""", """        float world[3], path[3];
        outOfPose(pose, w.local, true, world);
        outOfPose(pose, w.along, false, path);
        if (w.drip >= 1.f) {
            w.drip -= 1.f;
            WoundDrip& d = woundDrips[woundDripNext];
            woundDripNext = (woundDripNext + 1) % woundDripLimit;
            const unsigned salt = unsigned(now) * 2654435761u + i * 40503u;
            d.from[0] = world[0] + float(int(salt % 9) - 4);
            d.from[1] = world[1];
            d.from[2] = world[2] + float(int((salt >> 8) % 9) - 4);
            memcpy(d.sectorOrigin, sectorOrigin, sizeof d.sectorOrigin);
            d.radius = 1.2f + float((salt >> 16) % 25) / 10.f;
            d.born = now;
        }"""),
    ("""    out.count = count;
    ReleaseSRWLockExclusive(&woundLock);""", """    out.count = count;
    // The drops, nearest first, as their point in view space (the nearer reading of the sector origin, as
    // for the wounds); gone after two minutes, dry after half of one.
    struct ShownDrip { float distanceSq, centre[3], w; };
    ShownDrip drops[woundDripLimit];
    unsigned dropCount = 0;
    for (WoundDrip& d : woundDrips) {
        if (!d.born) continue;
        const float age = float(now - d.born) / 1000.f;
        if (age > woundDripSeconds) { d = {}; continue; }
        ShownDrip s{woundReachCm * woundReachCm, {}, 0.f};
        bool found = false;
        for (int candidate = 0; candidate < 2; ++candidate) {
            float q[3], c[3];
            for (int k = 0; k < 3; ++k) q[k] = d.from[k] + (candidate ? d.sectorOrigin[k] : 0.f);
            for (int k = 0; k < 3; ++k) c[k] = q[0] * view[k] + q[1] * view[4 + k] + q[2] * view[8 + k] + view[12 + k];
            const float sq = c[0] * c[0] + c[1] * c[1] + c[2] * c[2];
            if (std::isfinite(sq) && sq < s.distanceSq) { s.distanceSq = sq; memcpy(s.centre, c, sizeof c); found = true; }
        }
        if (!found) continue;
        const float dry = (std::min)(age / woundDripDrySeconds, 1.f);
        s.w = d.radius + 10.f * std::floor(dry * 9.f);
        drops[dropCount++] = s;
    }
    const unsigned dripCount = (std::min)(dropCount, woundDripShown);
    std::partial_sort(drops, drops + dripCount, drops + dropCount,
                      [](const ShownDrip& l, const ShownDrip& r) { return l.distanceSq < r.distanceSq; });
    for (unsigned k = 0; k < dripCount; ++k) {
        const float v[4] = {drops[k].centre[0], drops[k].centre[1], drops[k].centre[2], drops[k].w};
        memcpy(out.d[k], v, sizeof v);
    }
    out.drips = dripCount;
    ReleaseSRWLockExclusive(&woundLock);"""),
])

edit("mod/view_effects.inl", [
    ("""               wounds.count;
    }""", """               wounds.any();
    }"""),
    ("""uniform vec4 woundRect;    // screen box (uv min xy, max zw) that holds every wound's reach; outside it nothing to do
""", """uniform vec4 woundRect;    // screen box (uv min xy, max zw) that holds every wound's reach; outside it nothing to do
uniform vec4 dripA[24];    // a drop of blood: view-space point it fell from; w: radius (cm) + 10 x dryness step (0..9)
uniform float dripCount;
"""),
    ("""    if (!near) return color;
    vec3 lit = toLight(color);""", """    // Drops of blood on the first upward surface 20..200 cm below where they fell from: a round drop
    // with a ragged rim and a few specks, bright and wet at first, dark brown once dry.
    for (int j = 0; j < 24; ++j) {
        if (float(j) >= dripCount) break;
        vec4 D = dripA[j];
        float dryStep = floor(D.w / 10.0), radius = D.w - 10.0 * dryStep, dry = dryStep / 9.0;
        vec3 d = p - D.xyz;
        float h = dot(d, worldUp.xyz);
        if (h > -20.0 || h < -200.0) continue;
        vec3 spread = d - worldUp.xyz * h;
        float r = length(spread);
        if (r > radius * 3.0) continue;
        if (!near) {
            n = viewNormal(uv, p);
            near = true;
            vec3 base = toLight(color);
            float brightest = max(base.r, max(base.g, base.b)), darkest = min(base.r, min(base.g, base.b));
            grey = 1.0 - smoothstep(0.08, 0.2, (brightest - darkest) / max(brightest, 1e-4));
        }
        if (dot(n, worldUp.xyz) < 0.6) continue;
        float rim = 0.85 + 0.3 * woundHash(floor(atan(spread.z, spread.x) * 3.0) + D.x * 0.37);
        float drop = 1.0 - smoothstep(0.8, 1.0, r / (radius * rim));
        vec2 cell = floor(vec2(dot(spread, normalize(cross(worldUp.xyz, vec3(0.0, 0.0, 1.0)))), r) * 0.9);
        float speck = step(0.93, woundHash(cell.x * 17.0 + cell.y * 59.0 + D.y * 0.71)) * (1.0 - smoothstep(radius, radius * 3.0, r));
        float m = max(drop, speck * 0.8);
        tint *= mix(vec3(1.0), mix(vec3(0.33, 0.025, 0.02), vec3(0.28, 0.1, 0.06), dry), m);
        wet += m * (1.0 - dry) * 0.8;
    }
    if (!near) return color;
    vec3 lit = toLight(color);"""),
    (""", uWoundRect, viewUniformCount""", """, uWoundRect, uDripA, uDripCount, viewUniformCount"""),
    (""""woundRect"};""", """"woundRect", "dripA", "dripCount"};"""),
    ("""        {float(finishMode && request.wounds.count), &r.woundProgram,""",
     """        {float(finishMode && (request.wounds.count || request.wounds.drips)), &r.woundProgram,"""),
    ("""        if (finishMode && request.wounds.count && r.woundProgram && g.uniform4fv && projection.worldUpValid &&""",
     """        if (finishMode && (request.wounds.count || request.wounds.drips) && r.woundProgram && g.uniform4fv && projection.worldUpValid &&"""),
    ("""            box[0] = (std::min)(box[0], sx - rx); box[1] = (std::min)(box[1], sy - ry);
            box[2] = (std::max)(box[2], sx + rx); box[3] = (std::max)(box[3], sy + ry);
        }""", """            box[0] = (std::min)(box[0], sx - rx); box[1] = (std::min)(box[1], sy - ry);
            box[2] = (std::max)(box[2], sx + rx); box[3] = (std::max)(box[3], sy + ry);
        }
        // Each drop's reach: from 20 to 200 cm below where it fell, three radii across.
        for (unsigned k = 0; k < wounds.drips && box[2] - box[0] < 1.f; ++k) {
            const float* d = wounds.d[k];
            const float radius = d[3] - 10.f * std::floor(d[3] / 10.f);
            const float c[3] = {d[0] - projection.worldUpX * 110.f, d[1] - projection.worldUpY * 110.f,
                                d[2] - projection.worldUpZ * 110.f};
            const float reach = 90.f + radius * 3.f, depth = -c[2];
            if (!(depth - reach > 1.f)) { box[0] = box[1] = 0.f; box[2] = box[3] = 1.f; break; }
            const float sx = (projection.p0 * c[0] / depth - projection.p8) * 0.5f + 0.5f;
            const float sy = (projection.p5 * c[1] / depth - projection.p9) * 0.5f + 0.5f;
            const float rx = std::abs(projection.p0) * reach / (depth - reach) * 0.5f;
            const float ry = std::abs(projection.p5) * reach / (depth - reach) * 0.5f;
            box[0] = (std::min)(box[0], sx - rx); box[1] = (std::min)(box[1], sy - ry);
            box[2] = (std::max)(box[2], sx + rx); box[3] = (std::max)(box[3], sy + ry);
        }"""),
    ("""                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);""",
     """                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);
                g.uniform1f(u.at[uDripCount], float(wounds.drips));
                if (wounds.drips) g.uniform4fv(u.at[uDripA], GLsizei(wounds.drips), &wounds.d[0][0]);"""),
    ("""            if (request.wounds.count) bakeWoundSkins(g, r);""", """            if (request.wounds.any()) bakeWoundSkins(g, r);"""),
])
print("ok")
