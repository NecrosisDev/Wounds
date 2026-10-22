-- Defaults. The Mod Settings rows (main.lua) use these as their defaults and
-- override them per profile.
return {
    enabled = true,
    npcs = true,           -- other characters get injuries too, not only the player
    -- Health damage (a full pool is about 1) one hit must deal to a limb part, after
    -- armour. Smaller hits add up on that part while it has no rest.
    break_at = 0.12,       -- blunt hits (and unarmed, falls): the bone breaks
    disable_at = 0.10,     -- edges and points: the muscle is cut
    -- How much of a limb's muscle strength an injury at full severity takes away.
    broken_loss = 0.85,      -- a leg: it buckles and drags but still bears a little
    broken_arm_loss = 0.95,  -- an arm: it hangs from the break
    disabled_loss = 0.6,
    -- Healing: only after this many seconds with no hit on the character (at rest),
    -- then a full-severity injury takes heal_broken / heal_disabled seconds at speed 1.
    rest_seconds = 20,
    heal_speed = 1,
    heal_broken = 600,
    heal_disabled = 180,
    -- A blunt blow to the head this hard (one hit, after armour) breaks the neck: death.
    neck_kills = true,
    -- A broken arm this bad (severity 0.5..1) drops what its hand holds.
    drop_at = 0.6,
    neck_break_at = 0.25,
    -- While another mod regenerates a character, ExCamera closes its painted wounds over
    -- this many seconds (the "injuries.mend" mark's value).
    mend_fade_seconds = 8,
    -- Burns (the Fire mod sends "injuries.burn"): each unit of fire damage raises the burn level by
    -- burn_gain (1 = charred); a full burn heals in burn_heal seconds of rest at speed 1, and every
    -- unit of injuries.heal takes off burn_mend of it.
    burn_gain = 4,
    burn_heal = 900,
    burn_mend = 0.5,
    -- Severing (arms): a cut this hard to an upper arm, forearm or hand takes the limb off at the
    -- shoulder or elbow, if the runtime can cut the joint; the stump then bleeds for sever_bleed seconds.
    sever = true,
    sever_at = 0.35,
    sever_bleed = 40,
    notices = true,
    tick_seconds = 1.0,
}
