"""Wound marks get their own program and pass, run only over the wounds' screen box, so the finishing
program loses them (an ExCamera copy with wounds-07; CRLF files): python apply_split.py <excamera root>."""
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "src"


def read(rel):
    return (root / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def write(rel, text):
    (root / rel).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def sub(text, old, new, rel):
    assert text.count(old) == 1, (rel, old[:80], text.count(old))
    return text.replace(old, new)


V = "mod/view_effects.inl"
t = read(V)
start = t.index("uniform vec4 woundA[12];")
fn = t.index("vec3 woundMarks(vec3 color) {", start)
end = t.index("\n}\n", fn) + 3
wound_code = t[start:end]
t = t[:start] + t[end:]
t = sub(t, "    if (woundCount > 0.0) color = woundMarks(color); // on the surface itself, before any blur\n", "", V)
# The wounds' own program: the prelude plus the marks; it reads and rewrites the image it lies on.
t = sub(t, "// Uniform names shared by all programs;", """// Wound marks (wounds.inl), their own pass before the finishing pass: drawn only over the wounds'
// screen box onto the image the finishing pass will read, each pixel reading and rewriting itself
// (a texture barrier on either side). Kept out of the finishing program, which every frame runs.
static const char* const woundShader = R\"glsl(
uniform vec4 worldUp;      // world +Y in view space; w unused
""" + wound_code + """
void main() {
    vec4 c = texture2D(sceneTex, uv);
    gl_FragColor = vec4(woundMarks(c.rgb), c.a);
}
)glsl";

// Uniform names shared by all programs;""", V)
t = sub(t, "    programMeter, programDistance, programCount", "    programMeter, programDistance, programWounds, programCount", V)
t = sub(t, "    viewDistanceFailed = 4096\n", "    viewDistanceFailed = 4096, viewWoundsFailed = 8192\n", V)
t = sub(t, """        {float(aoMode || ssrMode), &r.distanceProgram, &owner->distanceAttempted, nullptr, distanceShader,
         viewDistanceFailed, "half-resolution distances"}};""", """        {float(aoMode || ssrMode), &r.distanceProgram, &owner->distanceAttempted, nullptr, distanceShader,
         viewDistanceFailed, "half-resolution distances"},
        {float(finishMode && request.wounds.count), &r.woundProgram, &owner->woundAttempted, nullptr, woundShader,
         viewWoundsFailed, "wound marks"}};""", V)
t = sub(t, """            owner->meterAttempted = owner->distanceAttempted = false;""",
        """            owner->meterAttempted = owner->distanceAttempted = owner->woundAttempted = false;""", V)
# The uniform uploads leave the finishing pass for the wound pass.
up_start = t.index("            const WoundUniforms& wounds = request.wounds;")
up_end = t.index("                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);\n            }\n", up_start)
up_end += len("                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);\n            }\n")
upload = t[up_start:up_end]
t = t[:up_start] + t[up_end:]
box_start = upload.index("                // The screen box")
box_code = upload[box_start:upload.index("                g.uniform4f(u.at[uWoundRect]")]
box_code = "\n".join(line[8:] if line.startswith("        ") else line for line in box_code.split("\n"))
t = sub(t, "        if (finishMode) {\n            beginPass(true);", """        // Wound marks first, on the image the finishing pass reads, only inside their screen box.
        if (finishMode && request.wounds.count && r.woundProgram && g.uniform4fv && projection.worldUpValid &&
            (source == r.viewColor || source == r.chainTex) && woundPassReady(g, r)) {
            const WoundUniforms& wounds = request.wounds;
""" + box_code + """        box[0] = std::clamp(box[0], 0.f, 1.f); box[1] = std::clamp(box[1], 0.f, 1.f);
            box[2] = std::clamp(box[2], 0.f, 1.f); box[3] = std::clamp(box[3], 0.f, 1.f);
            if (box[2] > box[0] && box[3] > box[1]) {
                const auto& u = viewUniforms[contextIndex][programWounds];
                g.activeTexture(glc::texture1);
                g.bindTexture(GL_TEXTURE_2D, r.viewDepth);
                g.activeTexture(glc::texture0);
                g.bindTexture(GL_TEXTURE_2D, source);
                g.bindFramebuffer(glc::framebuffer, r.woundFbo);
                g.framebufferTexture2D(glc::framebuffer, glc::colorAttachment0, GL_TEXTURE_2D, source, 0);
                setViewport(g, 0, 0, viewport[2], viewport[3]);
                glDisable(GL_BLEND);
                g.useProgram(r.woundProgram);
                setViewUniforms(g, u, frame);
                g.uniform1f(u.at[uWoundCount], float(wounds.count));
                g.uniform4fv(u.at[uWoundA], GLsizei(wounds.count), &wounds.a[0][0]);
                g.uniform4fv(u.at[uWoundB], GLsizei(wounds.count), &wounds.b[0][0]);
                g.uniform4fv(u.at[uWoundC], GLsizei(wounds.count), &wounds.c[0][0]);
                g.uniform4f(u.at[uWoundRect], box[0], box[1], box[2], box[3]);
                g.uniform4f(u.at[uWorldUp], projection.worldUpX, projection.worldUpY, projection.worldUpZ, 0.f);
                // The box as a quad, in the vertex shader's -1..1 position (uv = position * 0.5 + 0.5).
                const float quad[8] = {box[0] * 2.f - 1.f, box[1] * 2.f - 1.f, box[2] * 2.f - 1.f, box[1] * 2.f - 1.f,
                                       box[0] * 2.f - 1.f, box[3] * 2.f - 1.f, box[2] * 2.f - 1.f, box[3] * 2.f - 1.f};
                g.bindVertexArray(r.woundQuadVao);
                g.bindBuffer(glc::arrayBuffer, r.woundQuadVbo);
                g.bufferData(glc::arrayBuffer, ptrdiff_t(sizeof quad), quad, glc::dynamicDraw);
                g.vertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 8, nullptr);
                g.enableVertexAttribArray(0);
                woundTextureBarrier();
                glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
                woundTextureBarrier(); // the finishing pass reads what was just written
                g.bindVertexArray(r.viewVao);
            }
        }
        if (finishMode) {
            beginPass(true);""", V)
# Helpers: the barrier, the framebuffer and quad of the pass.
t = sub(t, "static void setViewUniforms(gl::Api& g, const ViewProgramUniforms& u, const ViewFrame& f) {",
        """using WoundBarrier = void(APIENTRY*)();
static WoundBarrier woundBarrier = nullptr;
static void woundTextureBarrier() {
    if (woundBarrier) woundBarrier();
}
// The wound pass's framebuffer and quad, and the barrier that lets a pixel read and rewrite itself
// (GL 4.5 or NV_texture_barrier); without it the pass stays off.
static bool woundPassReady(gl::Api& g, fp::CueResources& r) {
    if (!woundBarrier && !loadGl(woundBarrier, "glTextureBarrier") && !loadGl(woundBarrier, "glTextureBarrierNV")) {
        woundBarrier = nullptr;
        return false;
    }
    if (!r.woundFbo && g.genFramebuffers) g.genFramebuffers(1, &r.woundFbo);
    if (!r.woundQuadVao) g.genVertexArrays(1, &r.woundQuadVao);
    if (!r.woundQuadVbo) g.genBuffers(1, &r.woundQuadVbo);
    return r.woundFbo && r.woundQuadVao && r.woundQuadVbo;
}

static void setViewUniforms(gl::Api& g, const ViewProgramUniforms& u, const ViewFrame& f) {""", V)
write(V, t)

C = "cue_resources.h"
t = read(C)
t = sub(t, "             resolveProgram = 0, dofCompositeProgram = 0, meterProgram = 0, distanceProgram = 0;",
        "             resolveProgram = 0, dofCompositeProgram = 0, meterProgram = 0, distanceProgram = 0;\n"
        "    // Wound marks' own pass (view_effects.inl): program, framebuffer over the image, the box's quad.\n"
        "    unsigned woundProgram = 0, woundFbo = 0, woundQuadVao = 0, woundQuadVbo = 0;", C)
t = sub(t, "aoProgram || ssrProgram || dofProgram || finishProgram ||",
        "aoProgram || ssrProgram || dofProgram || finishProgram || woundProgram || woundFbo || woundQuadVao || woundQuadVbo ||", C)
t = sub(t, "        retireProgram(g, distanceProgram);\n", """        retireProgram(g, distanceProgram);
        retireProgram(g, woundProgram);
        if (woundFbo && g.deleteFramebuffers) g.deleteFramebuffers(1, &woundFbo);
        if (woundQuadVao) g.deleteVertexArrays(1, &woundQuadVao);
        if (woundQuadVbo) g.deleteBuffers(1, &woundQuadVbo);
        woundFbo = woundQuadVao = woundQuadVbo = 0;
""", C)
write(C, t)

O = "mod/overlay.inl"
t = read(O)
t = sub(t, "         meterAttempted = false, distanceAttempted = false;",
        "         meterAttempted = false, distanceAttempted = false, woundAttempted = false;", O)
write(O, t)
print("ok")
