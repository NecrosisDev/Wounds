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
static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0};

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
        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength};
        const float b[4] = {s.path[0], s.path[1], s.path[2], float(w.kind)};
        const float c[4] = {w.severity, w.seed, w.halfWidth, run};
        memcpy(out.a[k], a, sizeof a);
        memcpy(out.b[k], b, sizeof b);
        memcpy(out.c[k], c, sizeof c);
    }
    out.count = count;
    ReleaseSRWLockExclusive(&woundLock);
}
