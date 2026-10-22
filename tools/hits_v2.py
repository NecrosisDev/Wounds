"""wounds.inl (CRLF): read character_hits version 2 (0x78 records: + weapon, kind 1 cut / 2 crush), still
accepting version 1 (0x70). Usage: hits_v2.py <wounds.inl>"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8")


def sub(old, new):
    global t
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert t.count(old) == 1, old[:70]
    t = t.replace(old, new)


sub("""// The runtime's record, shared with ScriptRuntime's character_hits (version 1).
struct CharacterHitRecord {""", """// The runtime's record, shared with ScriptRuntime's character_hits: version 2 (0x78 bytes); a version 1
// runtime writes the first 0x70 bytes only (no weapon, kind 0 or 3).
struct CharacterHitRecord {""")
sub("""    uint32_t reserved;
};
static_assert(sizeof(CharacterHitRecord) == 0x70, "character_hits record layout");""", """    uint32_t reserved;
    uint64_t weapon;       // version 2: the delivering weapon's rigid body; 0 from version 1
};
static_assert(sizeof(CharacterHitRecord) == 0x78, "character_hits record layout");
constexpr uint32_t characterHitsV1Size = 0x70;
static std::atomic<uint32_t> characterHitsVersion{0}; // 1 or 2 once the export is found""")
sub("""    const auto fn = reinterpret_cast<CharacterHits>(GetProcAddress(runtime, "character_hits"));
    if (!version || !fn || version() != 1) return nullptr;
    characterHits.store(fn, std::memory_order_release);""", """    const auto fn = reinterpret_cast<CharacterHits>(GetProcAddress(runtime, "character_hits"));
    const uint32_t found = version ? version() : 0;
    if (!fn || (found != 1 && found != 2)) return nullptr;
    characterHitsVersion.store(found, std::memory_order_relaxed);
    characterHits.store(fn, std::memory_order_release);""")
sub("""    CharacterHitRecord hits[16];
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
        }""", """    // Version 1 records are 0x70 bytes apart; they are read into raw space and widened.
    const bool v1 = characterHitsVersion.load(std::memory_order_relaxed) == 1;
    const uint32_t stride = v1 ? characterHitsV1Size : uint32_t(sizeof(CharacterHitRecord));
    alignas(8) unsigned char raw[16 * sizeof(CharacterHitRecord)];
    for (int round = 0; round < 4; ++round) { // at most 64 new hits a frame
        int count = 0;
        __try { count = fn(woundSerial, reinterpret_cast<CharacterHitRecord*>(raw), 16); }
        __except (EXCEPTION_EXECUTE_HANDLER) {
            woundFaults.fetch_add(1, std::memory_order_relaxed);
            return;
        }
        for (int k = 0; k < (std::min)(count, 16); ++k) {
            CharacterHitRecord hit{};
            memcpy(&hit, raw + size_t(k) * stride, stride);
            if (hit.size != stride) return;
            woundSerial = hit.serial; // oldest first
            addWound(hit);
            addWeaponBlood(hit);
        }""")
p.write_bytes(t.encode("utf-8"))
print("ok")
