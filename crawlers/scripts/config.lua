-- Defaults. The Mod Settings rows (main.lua) use these as their defaults.
return {
    enabled = true,
    -- Downed undead who hold one of these roles fight on from the ground.
    roles = {"Undead", "Corpse"},
    reach = 110,         -- cm: closer than this they attack, farther they crawl toward the foe
    sight = 900,         -- cm: farther than this they lie still
    crawl_speed = 35,    -- cm a second the crawl drags the body (requested characters.drift)
    attack_every = 1.8,  -- seconds between attacks
    grab_health = 0.03, grab_balance = 0.12,   -- a grab that lands: the game's own damage applier
    swipe_health = 0.05, swipe_balance = 0.05,
    tick_seconds = 0.25,
}
