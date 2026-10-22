# Runtime requests from the wounds thread

## 1. `character_hits` export (for ExCamera wound marks): shipped in 0.28.0

API.md 0.28.0 lists it; `kind` there is 0 or 3. A cut/crush split (1/2) from the weapon grip
would let ExCamera stop guessing; optional.


Requested 2026-10-22 by the wounds thread, for the Lua runtime thread (owner of E:\ExanimaLua).
ExCamera's wound marks (`excamera/wounds-01.patch`) read hits from this export. Without it,
ExCamera draws nothing and reports `wound_hits_linked: false`.

## Why the runtime

The runtime already owns the detours on the damage applier `0x159700` and the weapon impact
`0x159A60` (`src/combat_bridge.h`). A second hook on either from ExCamera would collide with them.
The native override slot `0x4F0900` is not an option either, because it replaces the native apply.

## What to record

Record inside `applied()` (the `0x159700` detour) when the hit came through the impact detour.
That means `striking.attacker != 0`, and the struck body `attacker+0xC20` is a character part
(index `+0x468` in 0..17). Copy these values with `copyWorldMemory`, then call the original or
read them before it. Record whether or not any Lua addon listens.

| Field | Source (static reading of `159a60.c`, 2026-10-22) |
|---|---|
| `victim` | `159700`'s first argument (it equals `*(attacker+0xC20)+0x420`) |
| `part` | `attacker+0xC20`, the struck rigid body |
| `point[3]` | `attacker+0xC28`, the contact point. `159A60` converts this same vector into the part's frame against `part+0x2A0` (`EXP_world_to_local_rigid`), so it is in the pose's space |
| `pose[12]` | `part+0x2A0`, three axes then the origin, at the hit |
| `direction[3]` | The weapon body's motion: the mean of `weapon+0xF0` (4×3 floats) minus the mean of `weapon+0x120` (the step before), with weapon = `attacker+0xC38`. Zeros if unreadable |
| `health`, `balance` | `159700`'s health and balance arguments |
| `kind` | 3 when the attacker's motion `+0x9B8` is `0xB` (thrust). Otherwise 1 (cut) or 2 (crush) if the runtime can tell from the weapon's cutting and crushing values; 0 if not, and ExCamera then guesses |

## Export (version 1)

```c
struct CharacterHitRecord {            // 0x70 bytes, natural alignment
    uint32_t size;                     // sizeof(CharacterHitRecord)
    uint32_t serial;                   // 1, 2, 3, ... per recorded hit
    uint64_t victim, part;
    float point[3], direction[3];
    float pose[12];
    float health, balance;
    uint32_t kind;                     // 0 unknown, 1 cut, 2 crush, 3 thrust
    uint32_t reserved;                 // 0
};
extern "C" __declspec(dllexport) uint32_t character_hits_version();  // returns 1
extern "C" __declspec(dllexport) int character_hits(uint32_t after, CharacterHitRecord* out, int capacity);
```

- `character_hits` copies up to `capacity` records with `serial > after`, oldest first, and
  returns the count. If a record was overwritten, it starts from the oldest one still kept.
- A 64-entry ring under its own SRW lock is enough. The game thread writes it, and ExCamera's
  render thread reads it once per frame, so a call must never block for long.
- Use the same loading pattern as `character_mark_nodes`. ExCamera pins `ScriptRuntime.dll` and
  checks the version before the first call.
- Static safety review: the reads are the same kind `strikeOf()` already does (copies only). No
  write is added and no new hook is added.

---

# 2. `characters.limb_strength`: per-limb muscle strength (for the Injuries addon)

Requested 2026-10-22 for the Lua thread. The addon (this folder: `manifest.toml`, `scripts/`)
lists it as optional and only warns once while it is missing. A load check passes:
`python test_injuries.py`, against a stubbed API.

```lua
characters.set_limb_strength(target, part, factor)   -- true when held
```

- `target` is a `record_id` from a snapshot or hit event (every live character with it), or `"player"`.
- `part` is 1..18, in the `character.hit` order. The addon only sends limb parts: 2-7 and 11-18.
- `factor` is 0.05..1. A factor of 1 clears the part.
- Held by the runtime and not staged. It is forgotten at a level change and when the addon
  unloads (the addon sends it again), and it is not saved. When several addons set a part, use
  the lowest factor.

## Where the strength lives (static, decompile `work/probes/decomp-all.c`, build af9033c7…)

- **Solver:** `15DA80` (`EXP_solve_connected_part_constraints(part, pass)`) drives each joint
  row of a part (rows `+0x320`, stride 0x68, count `+0x31C`). The drive weight is
  `row+0x3C × part+0x594 × sqrt(character+0x10B8) × character+0x58C`. `+10B8` is stamina, so
  exhaustion already weakens limbs this way. **`part+0x594` is the per-part muscle multiplier.**
- **Native writers:** `+0x594` is rewritten often, so a one-time write will not hold:
  - `EXP_update_arm_chain_control_weights` (`1688C0`) writes the `+E60`/`+E68` arm chains;
  - `163CC0` writes `+0x9E0` list parents;
  - `1726C0`, `14E980`, `14F250`, `14F9A0` and `1FED00` write it too.
- **Callers:** two vtables point at `15DA80` (absolute pointers at file offsets `0x319030` and
  `0x3191F0`). It recurses into child parts through vtable `+0x168`.
- **Entry bytes:** `55 48 89 E5 48 8D A4 24 A0 FE FF FF 48 89 9D D0 FE FF FF`
  (push rbp; mov rbp,rsp; lea rsp,[rsp-0x160]; mov [rbp-0x130],rbx). There is no RIP-relative
  operand in the first 12 bytes. Neither the runtime nor ExCamera hooks it today (grep of both
  `src/`).
- **Character link:** the part's character is `part+0x580`, as the solver reads it. A part's
  index is `part+0x468`, as `combat_bridge.h` already reads it.

## Proposed implementation (one new detour, scoped multiply)

1. **Detour `15DA80` at entry,** under the runtime's one-owner rule, refusing if its bytes are
   not the ones above.
2. **In the detour:** look up `part` in a published table (part pointer → factor). If there is
   no entry, call the original only.
   - Otherwise read `v = part+0x594`, write `v × factor`, and call the original.
   - Then, only if `+0x594` still holds `v × factor`, write `v` back. A native writer that ran
     meanwhile wins.
   - The native value stays the owner, and nothing persists past the call.
3. **Building the table:** at each session pulse, from the held `(target, part) → factor`, walk
   each matching live character's parts (`+918` list, index `+468`). Publish the table as an
   immutable array behind one atomic pointer, retiring old arrays after a pulse. `15DA80` may
   run on the physics worker, so it takes no lock.
4. **Clearing:** at a level change, an unload, or factor 1, the part leaves the table.
   Nothing needs restoring, because the multiply is scoped.

The rules need a static safety review (`work/verification/lua-limb-strength-review.md`) before
this ships. The points above are the evidence to start from, not a finished review.

Not covered (possible later): making a disabled arm drop its weapon. No native drop routine for
an NPC's held item has been traced.

---

# 3. `characters.drop_held`: a hand lets go (for the Injuries addon)

Requested 2026-10-22 for the Lua thread. Injuries calls this when an arm breaks at severity ≥ 0.6
(listed as optional; without it, nothing is dropped). The harness checks the call shape.

```lua
characters.drop_held(target, side)   -- true when staged; side "right" or "left"
```

- `target`: "player", a record_id, or a table with a `handle`, the same as `set_limb_strength`.
- The character lets go of whatever that hand holds (a weapon or a shield), as the game itself
  does when a grip breaks, and the item falls as a loose physical item. It is staged and runs on
  the game thread at the next pulse. Nothing happens if the hand is empty.
- It should use the game's own release path. ExCamera's notes on grip joints (`bodyPart +0x320` rows,
  `gripJoint` connected part `+0x30`, flags `+0x38`) and the drag-release code show a release exists for
  the player's held items. No NPC hand-release routine has been traced yet; that needs its own static
  review before it ships.

---

# 4. `characters.soil_worn`: soot and wear on what a character wears (Injuries' burns)

Requested 2026-10-22 for the Lua thread. Injuries calls this on every burn it receives (topic
"injuries.burn" from the Fire mod), so burning clothes darken and fray **with the game's own
procedural cloth, leather and padding materials**. textures.flb `cloth_d/_n/_s`, `leather_*` and `suede_*` take
`Dirt` and `Damage` uniforms, which come from the item's condition bytes (dirt `+0x0E`, wear `+0x0D`,
the same bytes `restore_condition` lowers). The call is optional; without it only the skin burns.

```lua
characters.soil_worn(target, {dirt = 0..1, wear = 0..1})   -- true when staged
```

- `target`: "player", a record_id, or a table with a `handle`.
- It raises each worn apparel piece's dirt and wear by the amounts (scaled to the 0..255 bytes and
  capped there). It is staged on the game thread and goes through the same item-condition path that
  `restore_condition` uses (0x119550 per the Grindstone request), followed by whatever re-bakes
  the item's material. Raising dirt and wear, rather than lowering them, is the new part and needs its
  own review. For NPCs' worn items the path is untraced (their inventories are not read today).

---

# 5. Cut scars that survive a reload (Hunter: "on living characters, wounds should fade to scars")

ExCamera (wounds-11) heals cuts on the living into scars that stay, but only until the level is left or
the game is reloaded: the marks live in ExCamera's memory, in the struck part's frame. Burn scar tissue
is a single level per character, and Injuries already saves the player's (in `save_data`). Keeping cut
scars needs two runtime additions, both additive:

1. **`character.hit` gains where it landed**: `local_point = {x, y, z}` (the contact point in the struck
   part's frame, the `point` and `pose` the `character_hits` record already holds, converted) and
   `local_direction`. Injuries then records each cut and thrust on the player (and optionally on named
   NPCs by record_id) as a scar entry `{part, point, direction, size}` in `save_data` (about 30 bytes
   each, so a hundred scars fit the 4 KB).
2. **`characters.set_scars(target, list)` and an export for ExCamera**:
   `int character_scars(uint32_t after, CharacterHitRecord* out, int capacity)` (version 1), which hands
   ExCamera the held scars as hit-shaped records (the live part pointer and its current pose, the
   part-frame point turned to that pose's space, `kind` 4 meaning "a scar"). ExCamera adds them as
   finished scars, mapping and baking them like any wound. Injuries sends the list after every session
   start and level change.

Until then, scars stay for the rest of the level and are gone after a reload.

---

# 6. `characters.sever(target, part)`: cut a limb's joint (dismemberment, DISMEMBER-PLAN.md)

Requested 2026-10-22 for the Lua thread. Injuries calls it when a cut of `sever_at` health or more lands
on an arm (its "Severing" setting, on by default). Only a `true` return makes the limb count as severed:
then Injuries marks it for ExCamera, which splits the skin and draws flesh caps (wounds-13).

```lua
characters.sever(target, part)   -- true when the joint was cut; part 12/15 (shoulder), 13/16 (elbow)
```

- `target`: "player", a record_id or a table with a `handle`. `part`: 1..18 in `character.hit` order.
  The cut is the joint between that part and its parent (`+0x428`).
- Staged, run on the game thread at the next pulse. It sets flag **0x100000** on the joint row(s) linking
  the part to its parent: on the part's rows (`+0x320`, stride 0x68, count `+0x31C`) the row whose
  `+0x30` is the parent, and on the parent's rows the row whose `+0x30` is the part. 0x100000 is the
  flag the character solver `15DA80` skips (no constraint, no muscle), which the object solver `89D80`
  sets when a joint breaks and `152A30` toggles on weapon grip rows.
- Legs are allowed together with `characters.keep_down` (section 7). Injuries cuts a leg only when that
  call exists, so the character stays on the ground instead of the balance code standing on a severed foot.
- **The quirk fix (Hunter 2026-10-22):** once a part is cut, blows on it or anything hanging from it
  (the severed forearm and hand) must not hurt the owner. In the `159700` detour, when the struck body
  (attacker `+C20`) is a severed part, return without calling the original apply. No damage, no stagger
  and no `character.hit`; the contact's sound still plays (`159A60` plays it before the apply). Falls of
  the severed limb itself arrive through `157FF0`, so skip it there too when its body is severed.
- **Needs its own static review** before it ships (`work/verification/lua-sever-review.md`). It should
  cover the solver loop, the pose builder `1760F0` (still targets the cut part against its parent), and
  the hit path (a severed part still names its owner via `+0x420`, so blows on the fallen arm hurt its
  owner). It should also cover weapon grips (a held weapon's rows tie it to the hand), contacts, and
  what a save or level reload does to the flag (probably rebuilt, so Injuries cuts again for the player
  at session start).

---

# 7. `characters.keep_down(target, on)`: a character who cannot stand stays on the ground

Requested 2026-10-22 for the Lua thread (Hunter: "characters with a dismembered leg should be
ground-ridden"). Injuries turns it on for a character who lost a leg, and re-applies it at session start
for the player.

```lua
characters.keep_down(target, true|false)   -- true when held
```

The facts (static, `work/probes/decomp-all.c`):
- Character state is `+DF4`: 0x800 means down (knocked over), 0x300 getting up. The character update
  `169200` decides to stand. When `+DF4 & 0x800` and its recovery conditions hold, it plays Get up
  (motion 0xF or 0xE through `179EE0`, blend 0x32) and sets `+DF4` = 0x300.
- The same block plays Fall forward/backward (0x10/0x11) when the character goes over.
- A held character should take that block's no-get-up path. The cleanest gate is a detour of the
  motion player `179EE0` that refuses motions 0xE/0xF for a held character. The caller then sets
  `+DF4` = 0x300 regardless, which would leave it "getting up" with no motion, so the gate must sit on
  the caller's decision instead. That is untraced: it needs the exact branch in `169200` (around RVA
  of the `0xf,0x32` call) and its own static review.
- On the ground the native brain still runs. With no crawl or ground-attack clips in `humanoid.rsq`, a
  downed character can only lie, turn and flail through physics. Crawling and attacks from the ground
  (Hunter wishes the undead could) would need new clips, authorable in ExaniMate's pose studio, plus an
  AI hook. That is a later project.

---

# 8. Ground fighters: play a clip on a character, and drag a downed body (E:\Wounds\crawlers)

Requested 2026-10-22 for the Lua thread (Hunter wished undead could still attack from the ground). The
addon `com.necrosis.groundfighters` splices three clips of its own ("Ground Crawl", "Ground Grab",
"Ground Swipe", from its `scripts/clips.bin`) into the installed `humanoid.rsq` via `levels.read` and
`levels.serve`. They become motions 48, 49 and 50 after the file's 48 clips. The addon then drives downed
undead itself. It needs:

1. **`characters.play_motion(row, clip)`** (capability `characters.motion`). `row` is a
   `characters.read` row or a hit event (a handle); `clip` is a clip name from `humanoid.rsq`, resolved
   to its index in the file the game loaded. It is staged and calls the game's own motion player
   `179EE0(character, motion, 0x1E, 0)`. The static review must cover:
   - whether `179EE0` plays on a character in the down state (`+DF4 & 0x800`);
   - what the character update `169200` does to a motion started there, since its down branch may play
     idle or get up over it (with keep_down from section 7 holding them on the ground);
   - that the character's motion table `+9B0` (built by `2589D0` from the RSQ sets) reaches index 48+.
2. **`characters.drift(row, {x, z}, speed)`** (capability `characters.drift`). A held, gentle push of a
   downed body along the floor at `speed` cm a second, until 0 or a level change. It should go through
   the game's own part movement the way `player.push` does for the player. It is a live write and needs
   its own review.
3. **The serve must come before the game reads `humanoid.rsq`.** The addon serves in its `loading`
   phase. If the game reads the file before that, the clips need the startup-override path with
   computed bytes (`[script.overrides]` takes a file, and shipping a copy of the game's file is what this
   avoids).

Not traced: what the native brain does with a downed character. It is inferred to wait to stand up,
since no native attack starts from the down state. The addon's own loop (every 0.25 s) does the deciding:
crawl toward the player beyond 110 cm, grab or swipe within it, and land the blow with `player.damage`
if the player is still in reach at the strike.

# 9. Ground fighters use the native attack brain (Hunter 13:11: "undead should use their grabs/swipes just as intelligently as their standing attacks work")

Replaces the addon's own timer (alternate grab and swipe every 1.8 s inside 110 cm) with the game's own
decision. Static reading of the archived decode docs only (tools/exanimate/docs/AI.md, AI_BRAIN.md,
COMBAT.md via `tools/workspace.py read`; KNOWLEDGEBASE.md); nothing run in game.

**What the game does standing.** Think loop `B4570` (AI.md:55-62) runs the handler at `ai+8E8`; engaged,
that is `B8440`. It scores 17 stand-points (`AD420`), then moves, attacks or holds guard. The request goes
to `ai+9C` (0 swing, 8 overhead, 0x10 thrust) and side to `ai+1BC` (AI_BRAIN.md:233-241): a downed or busy
target gets an overhead, beyond 0.8 x reach a thrust or overhead by `char+1204`, and the side is
`0.2*F68 + rand(0..6) + (5*skill+5)*angle - 3` with skill `ai+1D8`. Dispatcher `AE9D0` gates on stamina
>= 0.8 x max, a cooldown of `lastEnd + 300 + 300*[0x11]` (400 unarmed), and the `+EA4` lock (COMBAT.md
2.2), then picks the motion (`157240`/`157700` 5-10, `157DC0` Stab, `157BF0` Overhead; KB 3044-3050) and
plays it with `179EE0` (no state gate, KB 3061-3083).

**Why it does nothing downed.** `B4570` returns at once while `char+DF4 & 0x800` (AI.md:55-57), so engage
never runs for a knocked-down NPC. Open conflict for the reviewer: AI_BRAIN.md:208 calls 0x200 down;
AI.md:57 and KB 3168 use 0x800. Confirm which bit a knockdown (and keep_down, section 7) sets.

**Ask.** For a character the addon marks as a ground fighter (`characters.ground_fighter(row, on)`,
capability `characters.ground_brain`), and only while it is down and kept down (section 7):
1. Let the think loop run engage for it despite the down bit (a detour on `B4570`'s early return,
   scoped to marked characters).
2. In the dispatcher, after the native gates pass, swap the chosen motion for a served ground clip:
   a side swing becomes "Ground Swipe" (mirrored by `ai+1BC`; a left-hand clip will be added), a thrust
   or overhead becomes "Ground Grab". Everything else stays native: when, stamina, cooldown, skill, side,
   range, and the hit itself (the game's own contact damage, so `player.damage` in the addon goes).
3. Engage's steering for a downed body becomes the drift of section 8 (toward its chosen stand-point,
   at the crawl speed), playing "Ground Crawl" while it moves.
4. Report per character in the snapshot which ground motion it is playing, for the addon and tests.

Unknowns the review must settle: whether `AE9D0` or the attack motion refuses under the down bit; whether
the contact/damage path runs for a body lying down; what engage's stand-point scoring makes of a body
that cannot stand (it may want to back off or circle). Each is a live write and needs its own
static decompile review (`work\verification\*-review.md`).

Until this lands the addon keeps its own timer.
