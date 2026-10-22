"""wounds.inl (CRLF): close the painted wounds of characters marked "injuries.mend". Usage: add_mend.py <wounds.inl>"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8")


def sub(old, new):
    global t
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert t.count(old) == 1, old[:70]
    t = t.replace(old, new)


sub("""    ULONGLONG born = 0;
""", """    ULONGLONG born = 0;
    float fade = 1.f; // 1 as struck; closes towards 0 while the character is marked injuries.mend
""")
sub("""static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0};
""", """static std::atomic<unsigned> woundsTaken{0}, woundsRetired{0}, woundFaults{0}, woundsMended{0};

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
""")
sub("""    AcquireSRWLockExclusive(&woundLock);
    takeHits();
""", """    AcquireSRWLockExclusive(&woundLock);
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
""")
sub("""        if (!read || owner != w.owner) { // the character is gone, or the part was freed or reused
            w = {};
            woundsRetired.fetch_add(1, std::memory_order_relaxed);
            continue;
        }
""", """        if (!read || owner != w.owner) { // the character is gone, or the part was freed or reused
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
""")
sub("""        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength};
""", """        // A closing wound shrinks towards its middle and pales.
        const float a[4] = {s.centre[0], s.centre[1], s.centre[2], w.halfLength * w.fade};
""")
sub("""        const float c[4] = {w.severity, w.seed, w.halfWidth, run};
""", """        const float c[4] = {w.severity * w.fade, w.seed, w.halfWidth * w.fade, run * w.fade};
""")
p.write_bytes(t.encode("utf-8"))
print("ok")
