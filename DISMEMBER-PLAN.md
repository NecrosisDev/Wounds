# Dismemberment: what the game code says, and the plan

Static reading of the archived 0.9.5.2g decompile (`work/probes/decomp-all.c`) and ExCamera's own
mesh readers. Nothing has run in game. 2026-10-22.

## Findings

**Joints can be switched off natively, and the game does it at run time.**
- A body part's joint rows sit at `part+0x320` (stride 0x68, count `+0x31C`). `row+0x30` is the
  connected body and `row+0x38` the flags.
- The character joint solver `15DA80` skips a row whose flags have **0x100000**. The same loop drives
  that joint's muscle (`row+0x3C × part+0x594 × …`), so a skipped row has no constraint and no motor.
- The object solver `89D80` sets 0x100000 itself when a joint's strength `row+0x28` runs out, which
  makes breakable joints.
- `152A30` (weapon grip setup) sets and clears 0x100000 on the weapon's grip rows whenever the grip
  changes (`& 0xFFEFFFFF | 0x100` re-arms a row).
- So setting the flag on the row between a forearm and its upper arm should let the forearm, hand and
  anything held fall free as their own physics bodies. That is inferred: the flag's effect on a
  *character* limb has not been observed.

**What still assumes the limb is attached** (static; each is a risk to check in game):
- **Hits.** A severed limb still names its owner (`part+0x420`). Blows landing on it still damage
  the character, and so do Injuries and the wound marks.
- **Pose builder (`1760F0`).** It keeps building targets for the limb against its parent (`+0x428`).
  With the row skipped nothing applies them, so this should be harmless.
- **Grip.** A held weapon is jointed to the hand (rows on the weapon body). A severed forearm takes
  hand and weapon with it, while the AI may still "hold" it.
- **Balance and support.** Feet are support contacts (`part+0x338`). A severed leg would leave the
  pelvis balance code with a missing support. **Stage 1 is arms only.**
- **Saves.** Row flags are probably rebuilt from the model when a level loads, so a reload would
  re-attach. That is untraced.
- **Threads.** The solver may run on the physics worker. A single 32-bit OR on the flag word is what
  `152A30` does on the game thread, so the runtime would do the same at a pulse.

**Skin.** The body is one skinned `_SKIN` mesh (bones = part scene nodes; bind positions, inverse
binds, 4 weights per vertex; faces `+0x290`, tags `+0x2F8`).
- A face whose three corners are weighted mostly to the severed bones moves with the limb.
- A face mixing both sides is the band that would stretch between stump and limb.
- ExCamera already draws chosen faces of this mesh with the game's own program, buffers and skinning
  (the stone-skin and wound-skin face split, and the VR hands-only body). Skipping the band and
  drawing the rest is the same mechanism with a third "skip" state.

## Plan

**Stage 1, ExCamera (visual):**
- Read Injuries' mark `injuries.severed`: one bit per limb bone, the same bits as `injuries.broken`.
- On such a character's skin draw, give every face a weight on the severed side (the summed weights
  to the bone and every bone below it) and split:
  - mostly-severed faces draw with the limb;
  - the band is skipped;
  - body faces draw as now.
- Caps: a disc of raw flesh with a pale bone centre, drawn by ExCamera's own program at the joint
  (the bone node's frame) on the stump and on the severed end, each facing out. A disc is used
  because the hole's edge is skinned and stretches.
- Armour and clothes on the limb get the same face split by their own skinned bones (stage 1b).

**Stage 2, Lua runtime (physics, requested):** `characters.sever(target, part)`.
- Staged and run on the game thread: set 0x100000 on the joint row(s) between `part` and its parent.
  That means the child's row whose `+0x30` is the parent, or the parent's row whose `+0x30` is the child.
- It needs its own static review (`work/verification/lua-sever-review.md`) before it ships.
- It sits behind Injuries' "Severing" setting, **default on once that review says it's safe**.
- Until then, severing is visual only and the limb stays physically attached. That would look wrong
  (an invisible arm still swings), so the visual cut stays off too until stage 2 exists.

**Stage 3, Injuries (rules):**
- A cut of at least 0.35 health on a forearm, upper arm or hand severs there (configurable).
- Severing means heavy bleeding (the game's own `+10D4` inflow via `player.damage`/`character:damage`)
  and a dropped weapon.
- It sets the `injuries.severed` bits and saves the player's state.
