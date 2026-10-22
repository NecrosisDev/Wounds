// Wounds: where a weapon got through, the struck character keeps a mark that moves with the limb: a
// gash along the blade's path for a cut, a short deep hole for a thrust, a bruise for a crush, and
// blood running down from fresh cuts. The hits come from ScriptRuntime.dll's character_hits export
// (version 1), which records them inside the game's damage applier; ExCamera only reads them. Each
// mark is kept in its body part's own frame and the finishing pass (view_effects.inl) draws it on
// the surface at that spot, so a blow the armour stopped leaves nothing (it dealt no damage) and a
// cut through cloth shows on the cloth. No native memory is written.

static std::atomic<float> woundMarks{1.f}; // the Wounds row: 0 off

// The runtime's record, shared with ScriptRuntime's character_hits (version 1).
struct CharacterHitRecord {
    uint32_t size, serial;
    uint64_t victim, part; // the struck character and its struck body part (a rigid body)
    float point[3];        // contact point, in the space of the part's pose
    float direction[3];    // the weapon's motion at contact, same space; zero when unknown
    float pose[12];        // the part's achieved pose at the hit: three axes then the origin
    float health, balance; // what the damage applier received
    uint32_t kind;         // 0 unknown, 1 cut, 2 crush, 3 thrust
    uint32_t reserved;
};
static_assert(sizeof(CharacterHitRecord) == 0x70, "character_hits record layout");
using CharacterHits = int (*)(uint32_t after, CharacterHitRecord* out, int capacity);
using CharacterHitsVersion = uint32_t (*)();

constexpr unsigned woundLimit = 96, woundsPerPart = 4;
constexpr unsigned woundShownLimit = 12; // the finishing program's arrays
constexpr float woundReachCm = 3000.f, woundMergeCm = 2.5f;
enum WoundKind : uint8_t { woundCut = 1, woundCrush = 2, woundThrust = 3 };
// A struck body part's character, where the game's weapon impact (0x159A60) reads its victim; that impact
// hands the same pointer to the damage applier, so it equals the record's victim.
constexpr size_t woundPartCharacter = 0x420;

struct Wound {
    uintptr_t part = 0, owner = 0; // the part, and the character it named at the hit; a change retires the mark
    float local[3]{}, along[3]{};  // centre and the blade's path, in the part's own frame
    float halfLength = 0.f, halfWidth = 0.f, severity = 0.f, seed = 0.f;
    ULONGLONG born = 0;
    float fade = 1.f; // 1 as struck; closes towards 0 while the character is marked injuries.mend
    uint8_t kind = 0;
};

// What the finishing pass takes: view-space marks, nearest first.
struct WoundUniforms {
    unsigned count = 0;
    float a[woundShownLimit][4]; // centre; w: half length, cm (a bruise's radius)
    float b[woundShownLimit][4]; // the blade's path, unit; w: kind
    float c[woundShownLimit][4]; // severity 0..1, seed, half width (cm), blood run length (cm)
};

static Wound woundStore[woundLimit];
static unsigned woundNext = 0;
static uint32_t woundSerial = 0; // the newest record taken
static SRWLOCK woundLock = SRWLOCK_INIT;
static std::atomic<CharacterHits> characterHits{nullptr};
static std::atomic<ULONGLONG> characterHitsProbed{0};
static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0}, woundsMended{0};

// Regeneration (the Injuries addon's "injuries.mend" mark, value = seconds to close a wound
// fully): ScriptRuntime.dll's character_mark_nodes export (marks version 1).
using WoundMarkNodes = int (*)(const char*, uintptr_t*, uint32_t*, int);
using WoundMarksVersion = uint32_t (*)();
constexpr unsigned woundMendLimit = 64;
static std::atomic<WoundMarkNodes> woundMarkNodes{nullptr};
static std::atomic<ULONGLONG> woundMarksProbed{0};
static ULONGLONG woundFadeTick = 0; // woundLock

static WoundMarkNodes woundMarkExport() {
    if (auto fn = woundMarkNodes.load(std::memory_order_acquire)) return fn;
    const ULONGLONG now = GetTickCount64();
    if (now - woundMarksProbed.load(std::memory_order_relaxed) < 2000) return nullptr;
    woundMarksProbed.store(now, std::memory_order_relaxed);
    HMODULE runtime = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN, L"ScriptRuntime.dll", &runtime) || !runtime) return nullptr;
    const auto version = reinterpret_cast<WoundMarksVersion>(GetProcAddress(runtime, "character_marks_version"));
    const auto fn = reinterpret_cast<WoundMarkNodes>(GetProcAddress(runtime, "character_mark_nodes"));
    if (!version || !fn || version() != 1) return nullptr;
    woundMarkNodes.store(fn, std::memory_order_release);
    return fn;
}

// The runtime's export, looked up again at most every two seconds until found; the module is pinned
// once found, so the cached entry stays valid for the life of the process.
static CharacterHits characterHitsExport() {
    if (auto fn = characterHits.load(std::memory_order_acquire)) return fn;
    const ULONGLONG now = GetTickCount64();
    if (now - characterHitsProbed.load(std::memory_order_relaxed) < 2000) return nullptr;
    characterHitsProbed.store(now, std::memory_order_relaxed);
    HMODULE runtime = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN, L"ScriptRuntime.dll", &runtime) || !runtime) return nullptr;
    const auto version = reinterpret_cast<CharacterHitsVersion>(GetProcAddress(runtime, "character_hits_version"));
    const auto fn = reinterpret_cast<CharacterHits>(GetProcAddress(runtime, "character_hits"));
    if (!version || !fn || version() != 1) return nullptr;
    characterHits.store(fn, std::memory_order_release);
    return fn;
}

// A world point (or, with origin false, a direction) into the pose's own frame; false for a degenerate pose.
static bool intoPose(const float* pose, const float* v, bool origin, float* out) {
    float d[3];
    for (int i = 0; i < 3; ++i) d[i] = v[i] - (origin ? pose[9 + i] : 0.f);
    for (int a = 0; a < 3; ++a) {
        const float* axis = pose + a * 3;
        const float lengthSq = axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2];
        if (!std::isfinite(lengthSq) || lengthSq < 1e-8f) return false;
        out[a] = (d[0] * axis[0] + d[1] * axis[1] + d[2] * axis[2]) / lengthSq;
    }
    return std::isfinite(out[0] + out[1] + out[2]);
}

static void outOfPose(const float* pose, const float* local, bool origin, float* out) {
    for (int i = 0; i < 3; ++i)
        out[i] = (origin ? pose[9 + i] : 0.f) + local[0] * pose[i] + local[1] * pose[3 + i] + local[2] * pose[6 + i];
}

static void addWound(const CharacterHitRecord& h) {
    const float health = std::isfinite(h.health) ? h.health : 0.f;
    const float balance = std::isfinite(h.balance) ? h.balance : 0.f;
    // PROVISIONAL(2026-10-22, until the runtime reports the weapon's cut/crush split a cut is told
    // from a blow by moving more health per balance, ratify-by: 2026-11-05)
    const uint8_t kind = h.kind >= woundCut && h.kind <= woundThrust ? uint8_t(h.kind)
                         : health > 0.4f * balance                  ? woundCut
                                                                    : woundCrush;
    if (kind == woundCrush ? balance < 0.05f && health < 1e-3f : health < 1e-3f) return; // nothing got through
    Wound w;
    w.part = uintptr_t(h.part);
    float healthMax = 1.f;
    __try {
        if (!w.part || !readable(w.part, woundPartCharacter + 8)) return;
        w.owner = *(const uintptr_t*)(w.part + woundPartCharacter);
        if (h.victim && readable(uintptr_t(h.victim), field::character::healthMax + 4))
            healthMax = *(const float*)(uintptr_t(h.victim) + field::character::healthMax);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        woundFaults.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    if (!w.owner || w.owner != uintptr_t(h.victim) || !intoPose(h.pose, h.point, true, w.local)) return;
    if (!intoPose(h.pose, h.direction, false, w.along)) memset(w.along, 0, sizeof w.along);
    if (!std::isfinite(healthMax) || healthMax < 0.05f) healthMax = 1.f;
    // PROVISIONAL(2026-10-22, size from damage: a third of full health fills the scale; tune after
    // Hunter's first look, ratify-by: 2026-11-05)
    w.severity = kind == woundCrush ? std::clamp(0.35f + 0.8f * balance, 0.35f, 1.f)
                                    : std::clamp(0.35f + 2.f * health / healthMax, 0.35f, 1.f);
    w.kind = kind;
    w.born = GetTickCount64();
    w.seed = float((h.serial * 2654435761u) >> 8) / float(1u << 24);
    switch (kind) {
    case woundCut: w.halfLength = 4.f + 7.f * w.severity; w.halfWidth = 0.35f + 0.5f * w.severity; break;
    case woundThrust: w.halfLength = 1.f + 0.8f * w.severity; w.halfWidth = 0.6f + 0.4f * w.severity; break;
    default: w.halfLength = 3.f + 4.f * w.severity; w.halfWidth = 0.f; break;
    }
    // A blow landing on a mark of the same kind deepens it; a part keeps its newest few marks.
    unsigned onPart = 0, oldest = woundLimit;
    for (unsigned i = 0; i < woundLimit; ++i) {
        Wound& e = woundStore[i];
        if (e.part != w.part || e.owner != w.owner) continue;
        const float dx = e.local[0] - w.local[0], dy = e.local[1] - w.local[1], dz = e.local[2] - w.local[2];
        if (e.kind == w.kind && dx * dx + dy * dy + dz * dz < woundMergeCm * woundMergeCm) {
            e.severity = (std::min)(e.severity + 0.5f * w.severity, 1.f);
            e.halfLength = (std::max)(e.halfLength, w.halfLength);
            e.halfWidth = (std::max)(e.halfWidth, w.halfWidth);
            e.born = w.born;
            return;
        }
        ++onPart;
        if (oldest == woundLimit || e.born < woundStore[oldest].born) oldest = i;
    }
    if (onPart >= woundsPerPart) {
        woundStore[oldest] = w;
    } else {
        woundStore[woundNext] = w;
        woundNext = (woundNext + 1) % woundLimit;
    }
    woundsTaken.fetch_add(1, std::memory_order_relaxed);
}

// Blood on the weapon that dealt a cut or a thrust. The record names the victim, not the weapon, so
// the striker's weapon is found read-only: first the game's own impact bookkeeping (a character whose
// +C18 impact kind is set and whose +C20 target is the struck part names its weapon at +C38), and
// failing that the carried weapon whose length passes nearest the contact point (within 20 cm). The
// spot is kept in that weapon mesh's own frame (its sampled pose, +A0), the frame the held-item
// surface paints in; the held-item pass looks it up by mesh node.
constexpr unsigned bloodWeaponLimit = 16, bloodSpotsPerWeapon = 4;
struct WeaponBlood {
    uintptr_t node = 0;
    float local[bloodSpotsPerWeapon][3]{};
    float amount[bloodSpotsPerWeapon]{};
    ULONGLONG born[bloodSpotsPerWeapon]{};
};
static WeaponBlood weaponBlood[bloodWeaponLimit];
static unsigned weaponBloodNext = 0;
static std::atomic<unsigned> weaponBloodTaken{0};

static bool meshPose(uintptr_t node, float* pose) {
    if (!readable(node, field::sceneNode::renderTransform + 64)) return false;
    const float* sampled = (const float*)(node + field::sceneNode::renderTransform);
    for (int row = 0; row < 4; ++row)
        for (int axis = 0; axis < 3; ++axis) pose[row * 3 + axis] = sampled[row * 4 + axis];
    return std::isfinite(pose[9] + pose[10] + pose[11]);
}

static uintptr_t strikingWeaponNode(const CharacterHitRecord& h) {
    const uintptr_t world = *(const uintptr_t*)gameAt(fp::sig::world);
    if (!readable(world, field::worldObject::characters + 8)) return 0;
    const uintptr_t roster = *(const uintptr_t*)(world + field::worldObject::characters);
    if (!readable(roster, field::list::items + 8)) return 0;
    const int characters = *(const int*)(roster + field::list::count);
    const uintptr_t entries = *(const uintptr_t*)(roster + field::list::items);
    if (characters <= 0 || characters > 4096 || !readable(entries, size_t(characters) * 8)) return 0;
    uintptr_t best = 0;
    float bestDistance = 20.f;
    for (int i = 0; i < characters; ++i) {
        const uintptr_t character = *(const uintptr_t*)(entries + size_t(i) * 8);
        if (!character || character == uintptr_t(h.victim) || !readable(character, field::character::impactWeapon + 8) ||
            !readable(character, field::character::weapons + 16))
            continue;
        if (*(const int*)(character + field::character::impactKind) &&
            *(const uintptr_t*)(character + field::character::impactTarget) == uintptr_t(h.part)) {
            const uintptr_t weapon = *(const uintptr_t*)(character + field::character::impactWeapon);
            if (readable(weapon, field::bodyPart::meshNode + 8)) return *(const uintptr_t*)(weapon + field::bodyPart::meshNode);
        }
        const int count = std::clamp(*(const int*)(character + field::character::weaponCount), 0, 2);
        for (int k = 0; k < count; ++k) {
            const uintptr_t weapon = *(const uintptr_t*)(character + field::character::weapons + size_t(k) * 8);
            if (!readable(weapon, field::bodyPart::meshNode + 8)) continue;
            const uintptr_t node = *(const uintptr_t*)(weapon + field::bodyPart::meshNode);
            float pose[12], local[3];
            if (!meshPose(node, pose) || !intoPose(pose, h.point, true, local)) continue;
            // Along its own length (z), from just behind the grip to past any blade's tip.
            if (local[2] < -30.f || local[2] > 160.f) continue;
            const float off = std::sqrt(local[0] * local[0] + local[1] * local[1]);
            if (off < bestDistance) {
                bestDistance = off;
                best = node;
            }
        }
    }
    return best;
}

static void addWeaponBlood(const CharacterHitRecord& h) {
    const float health = std::isfinite(h.health) ? h.health : 0.f;
    if (h.kind == woundCrush || health < 1e-3f) return; // only what drew blood
    uintptr_t node = 0;
    float pose[12], local[3];
    __try {
        node = strikingWeaponNode(h);
        if (!node || !meshPose(node, pose) || !intoPose(pose, h.point, true, local)) return;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        woundFaults.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    WeaponBlood* entry = nullptr;
    for (WeaponBlood& w : weaponBlood)
        if (w.node == node) entry = &w;
    if (!entry) {
        entry = &weaponBlood[weaponBloodNext];
        weaponBloodNext = (weaponBloodNext + 1) % bloodWeaponLimit;
        *entry = {};
        entry->node = node;
    }
    const ULONGLONG now = GetTickCount64();
    // A new spot near an old one adds to it; else it takes the weakest slot.
    unsigned slot = 0;
    for (unsigned k = 0; k < bloodSpotsPerWeapon; ++k) {
        const float dx = entry->local[k][0] - local[0], dy = entry->local[k][1] - local[1], dz = entry->local[k][2] - local[2];
        if (entry->amount[k] > 0.f && dx * dx + dy * dy + dz * dz < 9.f) {
            slot = k;
            break;
        }
        if (entry->amount[k] < entry->amount[slot]) slot = k;
    }
    memcpy(entry->local[slot], local, sizeof local);
    entry->amount[slot] = (std::min)(entry->amount[slot] + 0.4f + 0.6f * (std::min)(health * 4.f, 1.f), 1.f);
    entry->born[slot] = now;
    weaponBloodTaken.fetch_add(1, std::memory_order_relaxed);
}

// A held mesh's blood for the held-item pass: item-space centre, and in w the amount (the fraction)
// plus how wet it still is, drying over two minutes, as tenths in the whole part (0 for none).
static void weaponBloodFor(uintptr_t node, float (*out)[4]) {
    for (unsigned k = 0; k < bloodSpotsPerWeapon; ++k) out[k][0] = out[k][1] = out[k][2] = out[k][3] = 0.f;
    if (!TryAcquireSRWLockShared(&woundLock)) return;
    const ULONGLONG now = GetTickCount64();
    for (const WeaponBlood& w : weaponBlood) {
        if (w.node != node) continue;
        for (unsigned k = 0; k < bloodSpotsPerWeapon; ++k) {
            if (!(w.amount[k] > 0.f)) continue;
            const float wet = 1.f - (std::min)(float(now - w.born[k]) / 120000.f, 1.f);
            out[k][0] = w.local[k][0];
            out[k][1] = w.local[k][1];
            out[k][2] = w.local[k][2];
            out[k][3] = std::clamp(w.amount[k], 0.01f, 0.99f) + std::round(wet * 10.f);
        }
    }
    ReleaseSRWLockShared(&woundLock);
}

static void takeHits() {
    const CharacterHits fn = characterHitsExport();
    if (!fn) return;
    CharacterHitRecord hits[16];
    for (int round = 0; round < 4; ++round) { // at most 64 new hits a frame
        int count = 0;
        __try { count = fn(woundSerial, hits, 16); }
        __except (EXCEPTION_EXECUTE_HANDLER) {
            woundFaults.fetch_add(1, std::memory_order_relaxed);
            return;
        }
        for (int k = 0; k < (std::min)(count, 16); ++k) {
            if (hits[k].size != sizeof(CharacterHitRecord)) return;
            woundSerial = hits[k].serial; // oldest first
            addWound(hits[k]);
            addWeaponBlood(hits[k]);
        }
        if (count < 16) return;
    }
}

// The marks for one view: each live mark's centre and path from its part's pose now, in the native view
// space (row-major view matrix), nearest first. Whether the view takes sector-local or global points
// is not established here, so both readings are tried as for the held items and the nearer wins.
static void woundViewUniforms(const float* view, WoundUniforms& out) {
    out.count = 0;
    if (woundMarks.load(std::memory_order_relaxed) <= 0.f) return;
    struct Shown { float distanceSq; float centre[3], path[3]; unsigned index; };
    Shown shown[woundLimit];
    unsigned visible = 0;
    const ULONGLONG now = GetTickCount64();
    AcquireSRWLockExclusive(&woundLock);
    takeHits();
    // Marked characters' scene nodes (character +0x18), and the seconds since the last call.
    uintptr_t mendNodes[woundMendLimit]{};
    uint32_t mendSeconds[woundMendLimit]{};
    int mendCount = 0;
    if (const WoundMarkNodes marks = woundMarkExport()) {
        __try { mendCount = marks("injuries.mend", mendNodes, mendSeconds, int(woundMendLimit)); }
        __except (EXCEPTION_EXECUTE_HANDLER) { mendCount = 0; woundFaults.fetch_add(1, std::memory_order_relaxed); }
        mendCount = std::clamp(mendCount, 0, int(woundMendLimit));
    }
    const float fadeDt = woundFadeTick ? (std::min)(float(now - woundFadeTick) / 1000.f, 0.5f) : 0.f;
    woundFadeTick = now;
    for (unsigned i = 0; i < woundLimit; ++i) {
        Wound& w = woundStore[i];
        if (!w.part) continue;
        float pose[12], sectorOrigin[3]{};
        uintptr_t owner = 0;
        bool read = false;
        __try {
            if (readable(w.part, woundPartCharacter + 8)) {
                owner = *(const uintptr_t*)(w.part + woundPartCharacter);
                memcpy(pose, (const void*)(w.part + field::bodyPart::pose), sizeof pose);
                const uintptr_t node = *(const uintptr_t*)(w.part + field::bodyPart::meshNode);
                const uintptr_t sector = node && readable(node, field::sceneNode::sector + 8)
                                             ? *(const uintptr_t*)(node + field::sceneNode::sector) : 0;
                if (sector && readable(sector, field::sector::origin + 12))
                    memcpy(sectorOrigin, (const void*)(sector + field::sector::origin), sizeof sectorOrigin);
                read = true;
            }
        } __except (EXCEPTION_EXECUTE_HANDLER) {
            woundFaults.fetch_add(1, std::memory_order_relaxed);
        }
        if (!read || owner != w.owner) { // the character is gone, or the part was freed or reused
            w = {};
            woundsRetired.fetch_add(1, std::memory_order_relaxed);
            continue;
        }
        if (mendCount && fadeDt > 0.f) {
            uintptr_t ownerNode = 0;
            __try { ownerNode = *(const uintptr_t*)(owner + field::character::sceneNode); }
            __except (EXCEPTION_EXECUTE_HANDLER) { ownerNode = 0; }
            for (int k = 0; ownerNode && k < mendCount; ++k) {
                if (mendNodes[k] != ownerNode || !mendSeconds[k]) continue;
                w.fade -= fadeDt / float(mendSeconds[k]);
                break;
            }
            if (w.fade <= 0.02f) { // closed
                w = {};
                woundsMended.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
        }
        float world[3], path[3];
        outOfPose(pose, w.local, true, world);
        outOfPose(pose, w.along, false, path);
        Shown s{};
        s.distanceSq = woundReachCm * woundReachCm;
        bool found = false;
        for (int candidate = 0; candidate < 2; ++candidate) {
            float p[3], c[3];
            for (int k = 0; k < 3; ++k) p[k] = world[k] + (candidate ? sectorOrigin[k] : 0.f);
            for (int k = 0; k < 3; ++k) c[k] = p[0] * view[k] + p[1] * view[4 + k] + p[2] * view[8 + k] + view[12 + k];
            const float sq = c[0] * c[0] + c[1] * c[1] + c[2] * c[2];
            if (std::isfinite(sq) && sq < s.distanceSq && c[2] < 20.f) { // not behind the camera (it looks down -z)
                s.distanceSq = sq;
                memcpy(s.centre, c, sizeof c);
                found = true;
            }
            if (!candidate && !(sectorOrigin[0] || sectorOrigin[1] || sectorOrigin[2])) break;
        }
        if (!found) continue;
        for (int k = 0; k < 3; ++k) s.path[k] = path[0] * view[k] + path[1] * view[4 + k] + path[2] * view[8 + k];
        const float pathSq = s.path[0] * s.path[0] + s.path[1] * s.path[1] + s.path[2] * s.path[2];
        if (std::isfinite(pathSq) && pathSq > 1e-8f) {
            const float inverse = 1.f / std::sqrt(pathSq);
            for (float& v : s.path) v *= inverse;
        } else {
            memset(s.path, 0, sizeof s.path); // the shader picks a direction on the surface
        }
        s.index = i;
        shown[visible++] = s;
    }
    const unsigned count = (std::min)(visible, woundShownLimit);
    std::partial_sort(shown, shown + count, shown + visible,
                      [](const Shown& l, const Shown& r) { return l.distanceSq < r.distanceSq; });
    for (unsigned k = 0; k < count; ++k) {
        const Shown& s = shown[k];
        const Wound& w = woundStore[s.index];
        // Fresh cuts bleed: the runs lengthen over the first half minute.
        const float age = float(now - w.born) / 1000.f;
        const float run = w.kind == woundCrush ? 0.f : (std::min)(age / 30.f, 1.f) * (4.f + 14.f * w.severity);
        // A closing wound shrinks towards its middle and pales.
        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade};
        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind)};
        const float c[4] = {w.severity * w.fade, w.seed, w.halfWidth * w.fade, run * w.fade};
        memcpy(out.a[k], a, sizeof a);
        memcpy(out.b[k], b, sizeof b);
        memcpy(out.c[k], c, sizeof c);
    }
    out.count = count;
    ReleaseSRWLockExclusive(&woundLock);
}
