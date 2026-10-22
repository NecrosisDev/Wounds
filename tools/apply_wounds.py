"""Apply the wound-mark edits to an ExCamera source copy (CRLF files): python apply_wounds.py <excamera root>."""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"


def sub(rel, old, new, count=1):
    path = root / rel
    text = path.read_bytes().decode("utf-8")
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    found = text.count(old)
    if found != count:
        raise SystemExit(f"{rel}: expected {count} of {old[:70]!r}, found {found}")
    path.write_bytes(text.replace(old, new).encode("utf-8"))


wounds = root / "mod" / "wounds.inl"
wounds.write_bytes(wounds.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

# --- first_person.cpp: the store and its runtime link, before the effects that draw it.
sub("first_person.cpp", '#include "mod/overlay.inl"\n#include "mod/view_effects.inl"\n',
    '#include "mod/overlay.inl"\n#include "mod/wounds.inl"\n#include "mod/view_effects.inl"\n')

# --- overlay.inl: glUniform4fv for the wound arrays.
sub("mod/overlay.inl", "using UniformMatrix4fv = void(APIENTRY*)(GLint, GLsizei, GLboolean, const GLfloat*);\n",
    "using UniformMatrix4fv = void(APIENTRY*)(GLint, GLsizei, GLboolean, const GLfloat*);\n"
    "using Uniform4fv = void(APIENTRY*)(GLint, GLsizei, const GLfloat*);\n")
sub("mod/overlay.inl", "    UniformMatrix4fv uniformMatrix4fv = nullptr;\n",
    "    UniformMatrix4fv uniformMatrix4fv = nullptr;\n"
    "    Uniform4fv uniform4fv = nullptr; // view effects' wound arrays; null leaves the wounds undrawn\n")

# --- view_effects.inl
V = "mod/view_effects.inl"
sub(V, "uniform vec4 worldUp;      // world +Y in view space; w unused\n",
    r"""uniform vec4 worldUp;      // world +Y in view space; w unused
uniform vec4 woundA[12];   // a wound's view-space centre; w: half length, cm (a bruise's radius)
uniform vec4 woundB[12];   // the blade's path, view space; w: 1 cut, 2 crush, 3 thrust
uniform vec4 woundC[12];   // severity 0..1, seed, half width (cm), length of the blood runs (cm)
uniform float woundCount;

float woundHash(float x) {
    return fract(sin(x * 12.9898) * 43758.5453);
}

// Wounds (wounds.inl) on the surface where they landed. They multiply the light already there, so a
// wound in shadow stays in shadow; only wet blood adds a little shine, scaled by that same light.
vec3 woundMarks(vec3 color) {
    float raw = texture2D(depthTex, uv).r;
    if (raw >= skyDepth) return color;
    vec3 p = viewPosition(uv, raw);
    vec3 n = vec3(0.0, 0.0, 1.0);
    bool near = false;
    vec3 tint = vec3(1.0);
    float wet = 0.0;
    for (int i = 0; i < 12; ++i) {
        if (float(i) >= woundCount) break;
        vec4 A = woundA[i], B = woundB[i], C = woundC[i];
        vec3 d = p - A.xyz;
        float reach = A.w + C.w + 6.0;
        if (dot(d, d) > reach * reach) continue;
        if (!near) {
            n = viewNormal(uv, p);
            near = true;
        }
        // Only the surface at the wound: something a few cm off it (another limb, a wall behind) is left alone.
        float stick = 1.0 - smoothstep(2.0, 4.5, abs(dot(d, n)));
        if (stick <= 0.0) continue;
        vec3 t = B.xyz - n * dot(B.xyz, n);
        if (dot(t, t) < 1e-4) t = cross(n, abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0));
        t = normalize(t);
        vec3 s = cross(n, t);
        vec2 q = vec2(dot(d, t), dot(d, s)); // cm along the blade's path and across it, on the surface
        float severity = C.x, seed = C.y;
        if (B.w > 1.5 && B.w < 2.5) {
            // A bruise: mottled purple, red-brown where the blow landed hardest, torn there on a heavy one.
            float mottle = 0.78 + 0.22 * sin(q.x * 0.9 + seed * 31.0) * sin(q.y * 1.3 - seed * 17.0);
            float r = length(q) / (A.w * mottle);
            float w = (1.0 - smoothstep(0.3, 1.0, r)) * (0.5 + 0.4 * severity) * stick;
            vec3 bruise = mix(vec3(0.62, 0.45, 0.62), vec3(0.42, 0.17, 0.2), 1.0 - smoothstep(0.0, 0.7, r));
            float graze = severity > 0.6 ? step(0.8, woundHash(floor(q.x * 2.0) + floor(q.y * 2.0) * 57.0 + seed * 101.0)) *
                                               (1.0 - smoothstep(0.0, 0.45, r)) : 0.0;
            tint *= mix(vec3(1.0), mix(bruise, vec3(0.35, 0.05, 0.04), graze), w);
            continue;
        }
        // A cut, or a thrust's short deep hole: a lens-shaped gash darkest at its depth, swollen lips,
        // blood smeared around it, and fresh blood running down from it.
        float a = q.x / A.w;
        float taper = sqrt(max(1.0 - a * a, 0.0));
        float wobble = 0.22 * C.z * sin(a * 5.0 + seed * 40.0);
        float x = abs(q.y - wobble) / max(C.z * (0.25 + 0.75 * taper), 0.05);
        float inside = taper > 0.0 ? 1.0 - smoothstep(0.6, 1.0, x) : 0.0;
        float lip = taper * smoothstep(0.7, 1.1, x) * (1.0 - smoothstep(1.3, 2.4, x));
        float smear = (1.0 - smoothstep(1.2, 4.0, x)) * (1.0 - smoothstep(0.8, 1.25, abs(a))) *
                      (0.6 + 0.4 * woundHash(floor(q.x * 1.5 + seed * 13.0) + floor(q.y * 1.5) * 31.0));
        float facing = dot(worldUp.xyz, s) * sign(q.y - wobble); // the lip facing up catches the light
        vec3 cut = mix(vec3(1.0), vec3(0.7, 0.22, 0.2), smear * (0.55 + 0.35 * severity));
        cut = mix(cut, vec3(1.0, 0.5, 0.45) * (1.0 + 0.3 * facing), lip * 0.8);
        cut = mix(cut, mix(vec3(0.5, 0.035, 0.03), vec3(0.07, 0.003, 0.003), 1.0 - smoothstep(0.0, 0.8, x)), inside);
        float run = 0.0;
        vec3 down = n * dot(worldUp.xyz, n) - worldUp.xyz; // straight down, along the surface
        if (C.w > 0.0 && dot(down, down) > 0.04) {
            down = normalize(down);
            vec3 side = cross(n, down);
            float below = dot(d, down), across = dot(d, side);
            float ts = dot(t, side), td = dot(t, down);
            float thick = 0.2 + 0.25 * severity;
            for (int k = 0; k < 3; ++k) {
                float fk = float(k);
                float at = (woundHash(seed * 7.0 + fk) * 2.0 - 1.0) * (abs(ts) * A.w * 0.8 + C.z);
                // Each run leaves the cut where the cut crosses its line; a cut running downhill bleeds from its low end.
                float start = abs(ts) > 0.2 ? clamp(at / ts, -A.w, A.w) * td : A.w * abs(td);
                if (abs(ts) <= 0.2) at = 0.4 * (fk - 1.0) * C.z;
                float len = C.w * (0.45 + 0.55 * woundHash(seed * 3.0 + fk + 5.0));
                float along = below - start;
                float bead = 1.0 + 0.8 * smoothstep(len * 0.7, len, along);
                float line = 1.0 - smoothstep(thick * bead * 0.5, thick * bead, abs(across - at - 0.3 * sin(below * 0.4 + fk)));
                run = max(run, line * step(0.0, along) * (1.0 - smoothstep(len * 0.85, len, along)));
            }
            cut = mix(cut, vec3(0.32, 0.02, 0.018), run * 0.9);
        }
        tint *= mix(vec3(1.0), cut, stick);
        wet += (inside * (0.5 + 0.5 * severity) + 0.6 * run) * stick;
    }
    if (!near) return color;
    vec3 lit = toLight(color);
    float level = dot(lit, vec3(0.2126, 0.7152, 0.0722));
    lit *= tint;
    if (wet > 0.0) {
        vec3 lightDir = normalize(worldUp.xyz * 0.8 + vec3(0.0, 0.0, 0.6));
        float spec = pow(max(dot(n, normalize(lightDir + normalize(-p))), 0.0), 24.0);
        lit += vec3(0.9, 0.55, 0.5) * spec * min(wet, 1.0) * level * (0.4 + 2.5 * level);
    }
    return toStored(clamp(lit, 0.0, 1.0));
}
""")
sub(V, """    vec3 color = smoothEdges > 0.0 ? mix(c.rgb, smoothed(c.rgb), smoothEdges) : sharpen > 0.0 ? sharpened(c.rgb) : c.rgb;
""", """    vec3 color = smoothEdges > 0.0 ? mix(c.rgb, smoothed(c.rgb), smoothEdges) : sharpen > 0.0 ? sharpened(c.rgb) : c.rgb;
    if (woundCount > 0.0) color = woundMarks(color); // on the surface itself, before any blur
""")
sub(V, ", viewUniformCount\n", ",\n    uWoundA, uWoundB, uWoundC, uWoundCount, viewUniformCount\n")
# The names array: its last line names "heldFrame2" (and whatever came after it) and closes the list.
import re
_path = root / V
_text = _path.read_bytes().decode("utf-8")
_names = re.findall(r'\n([^\n]*"heldFrame2"[^\n]*)"\};\r\n', _text)
if len(_names) != 1:
    raise SystemExit(f"{V}: expected one names line ending the list, found {len(_names)}")
_text = _text.replace(_names[0] + '"};\r\n', _names[0] + '",\r\n    "woundA", "woundB", "woundC", "woundCount"};\r\n')
_path.write_bytes(_text.encode("utf-8"))
sub(V, """    HeldPose held[heldSlotLimit]{};
    bool finish() const {
        return smooth > 0.f || sharpen > 0.f || visor > 0.f || ghost || detail > 0.f || hurt > 0.f || winded > 0.f;
    }""", """    HeldPose held[heldSlotLimit]{};
    WoundUniforms wounds;                // wounds in view, already in this view's space
    bool finish() const {
        return smooth > 0.f || sharpen > 0.f || visor > 0.f || ghost || detail > 0.f || hurt > 0.f || winded > 0.f ||
               wounds.count;
    }""")
sub(V, """            g.uniform4f(u.at[uWorldUp], up[0], up[1], up[2], 0.f);
            if (held) heldDetailFrames.fetch_add(1, std::memory_order_relaxed);
""", """            g.uniform4f(u.at[uWorldUp], up[0], up[1], up[2], 0.f);
            if (held) heldDetailFrames.fetch_add(1, std::memory_order_relaxed);
            const WoundUniforms& wounds = request.wounds;
            const bool woundsOn = wounds.count && g.uniform4fv && projection.worldUpValid;
            g.uniform1f(u.at[uWoundCount], woundsOn ? float(wounds.count) : 0.f);
            if (woundsOn) {
                g.uniform4fv(u.at[uWoundA], GLsizei(wounds.count), &wounds.a[0][0]);
                g.uniform4fv(u.at[uWoundB], GLsizei(wounds.count), &wounds.b[0][0]);
                g.uniform4fv(u.at[uWoundC], GLsizei(wounds.count), &wounds.c[0][0]);
            }
""")
sub(V, """    if (!loadGl(g.getAttachmentParameter, "glGetFramebufferAttachmentParameteriv")) g.getAttachmentParameter = nullptr;
""", """    if (!loadGl(g.getAttachmentParameter, "glGetFramebufferAttachmentParameteriv")) g.getAttachmentParameter = nullptr;
    if (!loadGl(g.uniform4fv, "glUniform4fv")) g.uniform4fv = nullptr; // the wounds stay undrawn
""")
sub(V, """        memcpy(request.held, heldMaskPoses, sizeof request.held);
    }
""", """        memcpy(request.held, heldMaskPoses, sizeof request.held);
    }
    // Wounds: desktop and VR eyes alike, in the space of the matrices this view was drawn with.
    if (woundMarks.load(std::memory_order_relaxed) > 0.f) {
        ViewEffectProjectionSnapshot matrices;
        if (readViewMatrices(view, matrices)) woundViewUniforms(matrices.view, request.wounds);
    }
""")

# --- session.inl: counters in the status report.
sub("mod/session.inl", '    j.unum("held_detail_unanchored", heldDetailUnanchored.load());\n',
    '    j.unum("held_detail_unanchored", heldDetailUnanchored.load());\n'
    '    j.unum("wounds_taken", woundsTaken.load());\n'
    '    j.unum("wounds_retired", woundsRetired.load());\n'
    '    j.unum("wound_faults", woundFaults.load());\n'
    '    j.boolean("wound_hits_linked", characterHits.load() != nullptr);\n')

# --- settings: a Wounds row in Graphics, on by default.
M = "settings_model.h"
sub(M, "    heldDetail,\n    count\n", "    heldDetail,\n    woundMarks,\n    count\n")
sub(M, "    int heldDetail = 50; // procedural surface detail on held items, percent; half (the old Subtle) by default (owner's request)\n",
    "    int heldDetail = 50; // procedural surface detail on held items, percent; half (the old Subtle) by default (owner's request)\n"
    "    bool woundMarks = true; // cuts, bruises and running blood where weapons got through; on by default (owner's request)\n")
sub(M, "              setting::edgeSmoothing, setting::conditionEffects, setting::fingerPoses, setting::playerGhost}, 8},\n",
    "              setting::woundMarks, setting::edgeSmoothing, setting::conditionEffects, setting::fingerPoses,\n"
    "              setting::playerGhost}, 9},\n")
sub(M, """         L"with each breath, and the eyes take a moment to adjust between light and darkness. Uses the game's own "
         L"health and stamina."},
""", """         L"with each breath, and the eyes take a moment to adjust between light and darkness. Uses the game's own "
         L"health and stamina."},
        {setting::woundMarks, L"Wounds", RowInfo::toggle, nullptr, &ModSettings::woundMarks,
         L"View", L"Wounds", nullptr, nullptr,
         L"Where a weapon gets through, the character keeps the mark and it moves with the limb: a gash along the "
         L"blade's path for a cut, a deep hole for a thrust, a bruise for a blunt blow, with blood running down "
         L"from fresh cuts. Blows the armour stops leave nothing. Needs the Lua script runtime."},
""")
sub("settings_presentation.cpp", '    case setting::heldDetail: return L"Held item detail";\n',
    '    case setting::heldDetail: return L"Held item detail";\n    case setting::woundMarks: return L"Wounds";\n')
sub("mod/settings.inl", "    s.heldDetail = int(std::lround(heldDetail.load() * 100.f));\n",
    "    s.heldDetail = int(std::lround(heldDetail.load() * 100.f));\n    s.woundMarks = woundMarks.load() > 0.f;\n")
sub("mod/settings.inl", "    heldDetail = effectStrength(s.heldDetail);\n",
    "    heldDetail = effectStrength(s.heldDetail);\n    woundMarks = s.woundMarks ? 1.f : 0.f;\n")
print("applied")
