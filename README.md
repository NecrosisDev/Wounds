# Wounds

Two Exanima mods in one repository:

- **Injuries** (`com.necrosis.injuries`): hard blows to arms and legs break bones or cut muscles, weakening the limb until it heals. Hard cuts can take an arm off, and a hard blunt blow to the head can break the neck.
- **Ground Fighters** (`com.necrosis.groundfighters`): undead knocked to the ground keep fighting from the floor, crawling toward you and grabbing or swiping at your legs.

Each mod has its own release and can be installed on its own.

## Injuries

### Features

- **Broken bones and cut muscles.** A blunt hit (and unarmed blows and falls) to an arm or leg that deals enough damage breaks the bone. An edge or point hit cuts the muscle. Smaller hits to the same limb part add up while the character has had no rest. Whether a weapon counts as blunt or cutting comes from its grip.
- **Weakened limbs.** An injured limb pulls weaker: a broken leg buckles and drags, a broken arm hangs, a cut limb swings weak. Parts further down the limb are weakened too.
- **Dropped weapons.** A badly broken arm drops what its hand holds.
- **Broken necks.** A hard enough blunt blow to the head breaks the neck and kills, whether it is you or anyone else. This can be switched off.
- **Severed arms.** A hard enough cut to an upper arm, forearm or hand takes the arm off at the shoulder or elbow. The hand drops what it held and the stump bleeds for a while.
- **Burns.** With the Fire mod installed, burn damage builds up a burn level on each character that catches fire (you get a message when your skin blisters). Burns heal slowly at rest and leave a scar that stays. They show on characters in ExCamera builds that draw them (see below).
- **Healing.** Injuries heal only after a character has gone a while without being hit. At default speed a bad break mends in about ten minutes of rest and a cut in about three.
- **Other characters too.** Everyone can be injured, not only you. This can be switched off.
- **Messages.** On-screen messages tell you when you are injured or healed. These can be switched off.

Some parts depend on what your runtime supports:

- Limbs weaken only if your runtime can change a limb's strength. Without that, injuries are still tracked but limbs keep their strength, and a note is logged once.
- Arms are severed only if your runtime can cut a limb off. Legs are severed only if it can also keep a legless character on the ground.
- A badly broken arm drops its weapon only if your runtime can make a character let go.
- If your runtime can soil worn clothing, burns also soot and wear what a burning character wears.
- Settings and messages need a runtime with the Mod Settings menu and on-screen notices.

### Settings

If your runtime has the Mod Settings menu, Injuries adds these rows, saved per profile:

| Setting | Default | What it does |
|---|---|---|
| Injuries | On | Turns the mod on or off. Turning it off clears all injuries. |
| Others | On | Other characters get injured too, not only you. |
| Bone | 12% | Blunt damage to one limb part in one hit, as % of health, that breaks the bone. |
| Muscle | 10% | Edge or point damage to one limb part in one hit, as % of health, that cuts the muscle. |
| Neck | 25% | Blunt damage to the head in one hit, as % of health, that breaks the neck. |
| Lethal neck | On | A hard enough blunt blow to the head breaks the neck and kills. |
| Severing | On | A hard cut can take a limb off. |
| Sever | 22% | Edge damage to a limb in one hit, as % of health, that takes it off. |
| Speed | 1 | Healing speed, 0 to 4. 0 never heals. |
| Delay | 20 | Seconds without being hit before healing starts. |
| Messages | On | On-screen messages when you are injured or healed. |

Other tuning, such as how much strength each injury takes away, how long burns take to heal and how long a stump bleeds, lives in `mods/com.necrosis.injuries/scripts/config.lua`.

### Optional companion mods

- **Fire**: sends Injuries the burn damage each character takes, which Injuries turns into burns and scars.
- **ExCamera**: Injuries marks broken bones, severed limbs, burns, burn scars and healing on each character so ExCamera builds that read those marks can draw them. This repository also carries optional ExCamera visual deltas (`excamera/*.patch`) that draw wounds, bruises, blood and burns, for ExCamera builds only.

### For other mods

Other mods can heal a character or report burn damage through the runtime's addon messages:

```lua
addons.send("com.necrosis.injuries", "injuries.heal", {target = "player", amount = 0.2})   -- or a record id, or {handle = h}; amount 0..1
addons.send("com.necrosis.injuries", "injuries.burn", {target = {handle = h}, amount = 0.05})  -- fire damage dealt this time, 0..1
```

`injuries.heal` heals that much severity across the character's injuries, worst first, with no rest needed, and also eases burns.

### Saves

With a runtime that supports per-save mod data, your own injuries, burn scars and severed limbs are kept in your save and come back when you load it. Other characters' injuries are not saved and reset when you change level.

## Ground Fighters

### Features

- Undead and corpses that are down on the ground fight on instead of lying still. One that has lost a leg to Injuries (where the runtime supports severing legs) stays down for good.
- Within about 9 metres of you they crawl toward you. Once within reach they attack every couple of seconds, alternating a grab that pulls at your balance and a swipe at your legs.
- The crawl, grab and swipe are three animations this mod adds. They are added to the game's character animations in memory as the game reads them, so no game file is replaced or shipped.

Ground Fighters needs runtime support to play an animation on a character and to drag the body along the ground. Without it, downed undead lie still and a note is logged once.

Ground Fighters has no settings menu. Its tuning (reach, sight range, crawl speed, attack timing and damage) lives in `mods/com.necrosis.groundfighters/scripts/config.lua`.

Ground Fighters stores nothing in your save.

## Requirements

- Exanima (Steam).
- EMTK with the script-runtime startup patch (the Exanima Lua Runtime's README explains how to get it).
- Exanima Lua Runtime 0.28.0 or later.

## Install

1. Download the release ZIP for the mod you want from the GitHub Releases page: `Injuries-<version>.zip` or `GroundFighters-<version>.zip`.
2. Close Exanima.
3. Copy the ZIP's `mods` folder into your Exanima game folder.
4. Enable the mod in your EMTK profile.
5. Launch the game through EMTK.

## Uninstalling

Disable the mod in your EMTK profile, or close the game and delete its folder (`mods/com.necrosis.injuries` or `mods/com.necrosis.groundfighters`) from the Exanima folder.

## Building from source

Needs Python 3.

```
python -X utf8 -B release.py
```

This builds both mods, each into its own folder, and packages each as a ZIP with a `.sha256` file beside it:

| Mod | Built folder | Release ZIP |
|---|---|---|
| Injuries | `dist/mods/com.necrosis.injuries/` | `dist/Injuries-<version>.zip` |
| Ground Fighters | `crawlers/dist/mods/com.necrosis.groundfighters/` | `crawlers/dist/GroundFighters-<version>.zip` |

Each ZIP holds `mods/<mod id>/` exactly as EMTK loads it from the game folder. A mod is its `manifest.toml` and `scripts/` folder; Injuries is built from the repository root and Ground Fighters from `crawlers/`. Any previous build folder is first moved to `previous/` inside that mod's `dist` folder. `--zip-only` packages the folders already built without rebuilding.

Releases are tagged per mod: `injuries-v<version>` releases Injuries and `groundfighters-v<version>` releases Ground Fighters. The version must match that mod's `manifest.toml`; pushing the tag makes the GitHub workflow build and publish that mod's release. A version with a hyphen (for example `injuries-v0.3.0-rc1`) publishes a prerelease. `release.py --tag <tag>` builds only the mod the tag names.

Ground Fighters' animations ship prebuilt in `crawlers/scripts/clips.bin`, authored by `crawlers/tools/make_clips.py` (which reads the installed game, so it is not part of the release build).
