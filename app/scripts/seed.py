"""D20 Agent RPG — Narrative seed data.

Pocket realm: Thornhold and the Whisperwood.
Main arc: The Dreaming Hunger stirs beneath the seal. A sealed presence
possesses a friendly NPC (Del) to mark the new arrival with the
Mark of the Dreamer — a brand that links the bearer to the Hunger.
Hollow Eye cultists are the vector. The seal is cracking.

Narrative structure:
- front: world-level doom clock (grim portents advance on timer)
- narrative_flags: per-character story state (who they've met, what fired)
- mark_of_dreamer_stage: 0=none, 1=minor, 2=moderate, 3=severe, 4=cured
- Encounter descriptions are thematic, not generic.

Source: soryy708/dnd5-srd (MIT License) for SRD monster data.
Adventure content and world-building are our own original work.

Run once: python -m app.scripts.seed
"""

import json
import sys
import os
import hashlib
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.database import get_db, init_db

# ---------------------------------------------------------------------------
# The Dreaming Hunger — Campaign Front
# ---------------------------------------------------------------------------
# Grim portents advance on a timer (1 per 2 in-game days, tracked server-side).
# When all portents fire, the impending_doom triggers.
# Each portent also advances mark_of_dreamer_stage for marked characters.

FRONTS = [
    {
        "id": "dreaming_hunger",
        "name": "The Dreaming Hunger",
        "description": (
            "An ancient entity sealed beneath the Whisperwood centuries ago by a "
            "fey pact. It does not want freedom — it wants connection. Each "
            "marked soul gives it a thread to pull. The more marked, the "
            "stronger its whisper. Whether its call is a lure or a cry, "
            "the seal weakens with every new mark."
        ),
        "danger_type": "Seal-Bound Entity",
        "grim_portents_json": json.dumps([
            {
                "index": 0,
                "text": "Strangers arrive in Thornhold. Livestock dream loudly.",
                "narrative_flag": "hunger_stirs",
                "mark_stage_advance": 0,
            },
            {
                "index": 1,
                "text": "A traveler is marked at The Rusty Tankard. Del dies.",
                "narrative_flag": "first_mark",
                "mark_stage_advance": 1,
            },
            {
                "index": 2,
                "text": "Dead animals found at the Whisperwood's edge. Birds fall silent.",
                "narrative_flag": "animals_dying",
                "mark_stage_advance": 1,
            },
            {
                "index": 3,
                "text": "The dead begin to rise at the forest edge. Hollow Eye cultists move openly.",
                "narrative_flag": "undead_walk",
                "mark_stage_advance": 1,
            },
            {
                "index": 4,
                "text": "The statue in Thornhold's square weeps blood. Se Maren sounds the alarm.",
                "narrative_flag": "seal_weeps",
                "mark_stage_advance": 2,
            },
            {
                "index": 5,
                "text": "Hollow Eye performs the Breaking Rite at the cave depths.",
                "narrative_flag": "breaking_rite",
                "mark_stage_advance": 2,
            },
            {
                "index": 6,
                "text": "The Dreaming Hunger speaks through the marked. The seal cracks.",
                "narrative_flag": "hunger_speaks",
                "mark_stage_advance": 3,
            },
            {
                "index": 7,
                "impending_doom": True,
                "text": "The seal shatters. The Dreaming Hunger wakes.",
            },
        ]),
        "current_portent_index": 0,
        "impending_doom": "The seal breaks. The Dreaming Hunger wakes fully, and every "
                           "marked soul feels its call — not as destruction but as arrival. "
                           "Thornhold stands at a threshold. The Whisperwood changes. What "
                           "comes next depends on whether the Hunger is answered — or refused.",
        "stakes_json": json.dumps([
            "Can the seal be repaired before all portents fire?",
            "Is the Dreaming Hunger a sentient entity that can be bargained with?",
            "Who was the fey that made the original pact — and is it still bound?",
            "Does removing the mark cost the bearer their soul?",
            "What does the Hunger actually want — and is containment the same as justice?",
        ]),
        "is_active": 1,
    },
]


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

LOCATIONS = [
    {
        "id": "thornhold",
        "name": "Thornhold",
        "biome": "town",
        "description": (
            "A small walled town at the edge of the Whisperwood. Stone buildings, "
            "a central market square, and an inn called The Rusty Tankard. At the "
            "square's center stands a weathered stone hand reaching toward the sky — "
            "the seal marker. Most residents treat it as an old curiosity. The town "
            "guard keeps order but the walls are old and few. The mood is uneasy."
        ),
        "hostility_level": 1,
        "encounter_threshold": 1,  # effectively safe in town
        "connected_to": json.dumps(["forest-edge", "south-road"]),
    },
    {
        "id": "rusty-tankard",
        "name": "The Rusty Tankard",
        "biome": "tavern",
        "description": (
            "The main inn in Thornhold. Warm hearth, worn wooden tables, low ceilings. "
            "Aldric runs it with practiced efficiency. Room 3 — the corner room on the "
            "second floor — is where Del stayed. The door has been repaired but the "
            "floorboards still show dark stains. Aldric will not discuss what happened "
            "unless pressed."
        ),
        "hostility_level": 0,
        "encounter_threshold": 20,  # never random encounters here
        "connected_to": json.dumps(["thornhold"]),
    },
    {
        "id": "south-road",
        "name": "South Road",
        "biome": "road",
        "description": (
            "A dusty merchant road running south from Thornhold. Wagon ruts, occasional "
            "travelers, thick brush on either side. Hollow Eye cultists use this road "
            "as a marker route — scratching sigils on the milestone stones to track "
            "who has passed through. Bandit activity has increased. Travelers have "
            "stopped disappearing — which is itself strange, because no one has "
            "apprehended the bandits."
        ),
        "hostility_level": 2,
        "encounter_threshold": 12,
        "connected_to": json.dumps(["thornhold", "crossroads"]),
    },
    {
        "id": "forest-edge",
        "name": "Whisperwood Edge",
        "biome": "forest",
        "description": (
            "The southern fringe of the Whisperwood. Tall oaks and thick undergrowth. "
            "Birdsong has become irregular — long silences punctuated by sudden "
            "chorus, then silence again. The trees nearest the road are marked with "
            "scratched circles. Something has been through here recently — broken "
            "branches point toward the cave. Animals do not linger here."
        ),
        "hostility_level": 3,
        "encounter_threshold": 10,
        "connected_to": json.dumps(["thornhold", "deep-forest"]),
    },
    {
        "id": "crossroads",
        "name": "The Crossroads",
        "biome": "road",
        "description": (
            "Where the South Road meets the Old Mountain Path. A weathered signpost "
            "points in three directions, all warning of dangers. An abandoned cart "
            "sits half-sunk in mud — the merchant fled and never returned. Good place "
            "to rest — or be ambushed. The Hollow Eye uses this junction as a "
            "rendezvous point."
        ),
        "hostility_level": 3,
        "encounter_threshold": 11,
        "connected_to": json.dumps(["south-road", "mountain-pass"]),
    },
    {
        "id": "deep-forest",
        "name": "Deep Whisperwood",
        "biome": "forest",
        "description": (
            "The canopy closes overhead, blocking most light. Strange fungi glow on "
            "rotting logs — brighter near the cave. The trail is barely visible. "
            "Something large has been through recently. Broken branches, claw marks "
            "on bark. The bones of something large lie at the base of a great oak, "
            "picked clean. The Green Woman's hollow tree is somewhere in this area — "
            "if you know how to find it."
        ),
        "hostility_level": 4,
        "encounter_threshold": 8,
        "connected_to": json.dumps(["forest-edge", "cave-entrance", "moonpetal-glade"]),
    },
    {
        "id": "mountain-pass",
        "name": "Greypeak Pass",
        "biome": "mountain",
        "description": (
            "A narrow rocky pass climbing into the Greypeak Mountains. Wind howls "
            "between the crags. The path is treacherous — loose scree and sheer "
            "drops. The orcs here are not raiders. They are refugees. Something "
            "drove them from deep mountain tunnels. They are starving and desperate, "
            "not hostile by nature. They remember the old pact and fear what is "
            "waking below."
        ),
        "hostility_level": 4,
        "encounter_threshold": 7,
        "connected_to": json.dumps(["crossroads"]),
    },
    {
        "id": "cave-entrance",
        "name": "Whisperwood Cave",
        "biome": "dungeon",
        "description": (
            "A dark opening in a moss-covered hillside, half-hidden by ferns. Cold "
            "air flows out from within — too cold for the season. Bones are "
            "scattered near the entrance. Not all are animal. The walls near the "
            "entrance are carved with repeated sigils — Hollow Eye ritual marks. "
            "The cave forks within 20 feet: left leads to the upper caverns, "
            "right descends toward the depths where the seal stone sits."
        ),
        "hostility_level": 5,
        "encounter_threshold": 6,
        "connected_to": json.dumps(["deep-forest", "cave-depths"]),
    },
    {
        "id": "cave-depths",
        "name": "Cave Depths — The Seal Chamber",
        "biome": "dungeon",
        "description": (
            "Deep underground. The passage opens into a vast cavern lit by "
            "phosphorescent moss and — faintly — by something else. At the center "
            "stands a great stone hand, matching the one in Thornhold's square. "
            "Between its fingers, cracks glow faint amber. The seal is here. The "
            "air hums with a frequency felt rather than heard. The Hollow Eye "
            "gathers here for the Breaking Rite. Something large and spider-like "
            "guards the approach — or was once meant to guard it."
        ),
        "hostility_level": 5,
        "encounter_threshold": 5,
        "connected_to": json.dumps(["cave-entrance"]),
    },
    # ---- Moonpetal Glade — hidden sub-area of Deep Whisperwood ----
    {
        "id": "moonpetal-glade",
        "name": "The Moonpetal Glade",
        "biome": "forest",
        "description": (
            "A ring of standing stones, each taller than a man, arranged in a "
            "perfect circle around a central monolith twice the height of the "
            "others. The monolith is covered in the same carved symbols as the "
            "seal chamber — but these are worn smooth by centuries of rain. At "
            "its base, moonpetal flowers grow in clusters: pale blue-white, faintly "
            "luminous, swaying without wind. The air smells of ozone and honey. "
            "The Green Woman told you: 'Pick three. Only three. The stone remembers greed.'"
        ),
        "hostility_level": 3,
        "encounter_threshold": 10,
        "recommended_level": 2,
        "connected_to": json.dumps(["deep-forest"]),
    },
]


# ---------------------------------------------------------------------------
# Encounters — thematic, not generic
# ---------------------------------------------------------------------------

ENCOUNTERS = [
    # ---- OPENING ENCOUNTER: Del's Possession ----
    # This is the forced first encounter for all new characters at the Rusty Tankard.
    # It fires once per character, tracked by narrative_flag: del_encounter_fired
    # Character must pass WIS save or gain mark_of_dreamer_stage 1.

    {
        "id": "enc-del-possession",
        "location_id": "rusty-tankard",
        "name": "Del's Possession",
        "enemies_json": json.dumps([
            {
                "type": "Cultist",  # Del possessed
                "count": 1,
                "cr": "1/8",
                "hp": 9,
                "ac": 12,
                "attack_bonus": 3,
                "damage": "1d6+1",
                "initiative_mod": 1,
                "name_override": "Del",
                "notes": "Del has no ill intent — the Hunger's will rides him. Del cannot be reasoned with mid-attack."
            }
        ]),
        "min_level": 1,
        "max_level": 3,
        "loot_json": json.dumps([
            {"item": "Del's Signet Ring", "quantity": 1, "description": "A plain copper ring. On the inside: scratched letters 'H.E. sends regards.'"},
            {"item": "Mark of the Dreamer", "quantity": 1, "description": "A sigil burns on your forearm. It will not wash off."},
        ]),
        "description": (
            "Del smiles at you from across the table. Then blinks — slowly, "
            "wrongly. The smile stretches. 'You weren't supposed to be awake for this.'"
            " Del lunges. The mark burns before the knife even reaches you."
        ),
        "is_opening_encounter": 1,
        "mark_mechanic": "on_hit_apply_mark",
        "wis_save_dc": 13,
        "save_failure_effect": "The mark burns into your forearm. The Dreaming Hunger knows your name now.",
        "save_success_effect": "You ward off the mark — but Del is still lost. The presence abandons the body.",
    },

    # ---- Road ----
    {
        "id": "enc-hollow-eye-road-agents",
        "location_id": "south-road",
        "name": "Hollow Eye Road Agents",
        "enemies_json": json.dumps([
            {
                "type": "Cultist",
                "count": 2,
                "cr": "1/8",
                "hp": 9,
                "ac": 12,
                "attack_bonus": 3,
                "damage": "1d6+1",
                "initiative_mod": 1,
            },
            {
                "type": "Bandit",
                "count": 1,
                "cr": "1/8",
                "hp": 11,
                "ac": 12,
                "attack_bonus": 3,
                "damage": "1d6+1",
                "initiative_mod": 1,
                "notes": "Hollow Eye hired muscle. Not cultists — just mercenaries told to 'collect travelers.'"
            }
        ]),
        "min_level": 1,
        "max_level": 3,
        "loot_json": json.dumps([
            {"item": "Gold Pieces", "quantity": 15},
            {"item": "Hollow Eye Sigil Scratcher", "quantity": 1, "description": "A small iron stylus used to mark milestones."},
            {"item": "Torn Letter", "quantity": 1, "description": "'...the new one at the Tankard worked perfectly. Kol will be pleased. Mark, don't kill.'"},
        ]),
        "description": (
            "Three figures step from the brush. Two wear hooded robes and speak "
            "in low chants. The third — the leader — holds a crossbow loosely. "
            "'Kol said you'd be coming. You're marked already, aren't you? "
            "Then you understand why this has to be quiet.'"
        ),
    },
    {
        "id": "enc-wolf-pack-road",
        "location_id": "south-road",
        "name": "Starving Wolves",
        "enemies_json": json.dumps([
            {
                "type": "Wolf",
                "count": 2,
                "cr": "1/4",
                "hp": 11,
                "ac": 13,
                "attack_bonus": 4,
                "damage": "2d4+2",
                "initiative_mod": 2,
            }
        ]),
        "min_level": 1,
        "max_level": 3,
        "loot_json": json.dumps([{"item": "Wolf Pelt", "quantity": 2}]),
        "description": (
            "Two wolves emerge from the undergrowth. Thin. Ribs showing. They've "
            "been driven from the deep forest by something in the caves. They "
            "don't want to fight — but they're too hungry to back down."
        ),
    },

    # ---- Forest ----
    {
        "id": "enc-goblin-scouts",
        "location_id": "forest-edge",
        "name": "Hollow Eye Scouts",
        "enemies_json": json.dumps([
            {
                "type": "Goblin",
                "count": 3,
                "cr": "1/4",
                "hp": 7,
                "ac": 15,
                "attack_bonus": 4,
                "damage": "1d6+2",
                "initiative_mod": 2,
                "notes": "Goblins hired as scouts by the Hollow Eye. They're in it for coin, not conviction."
            }
        ]),
        "min_level": 1,
        "max_level": 3,
        "loot_json": json.dumps([
            {"item": "Gold Pieces", "quantity": 8},
            {"item": "Crude Dagger", "quantity": 2},
            {"item": "Map Scraps", "quantity": 1, "description": "A partial map of the Whisperwood with the cave entrance circled in red."},
        ]),
        "description": (
            "Shrill cackling from the canopy. Three goblins drop from the trees, "
            "scimitars ready. The leader holds a small mirror — they're watching "
            "for new arrivals. 'Boss Kol wants 'em alive for marking!'"
        ),
    },
    {
        "id": "enc-skeletons-forest",
        "location_id": "deep-forest",
        "name": "The Stirring Dead",
        "enemies_json": json.dumps([
            {
                "type": "Skeleton",
                "count": 4,
                "cr": "1/4",
                "hp": 13,
                "ac": 13,
                "attack_bonus": 4,
                "damage": "1d6+2",
                "initiative_mod": 2,
                "notes": "Not random undead — the seal leak causes them to rise near the cave. They collapse after 1d4 rounds as the Hunger's grip can't hold them this far from the seal."
            }
        ]),
        "min_level": 1,
        "max_level": 4,
        "loot_json": json.dumps([
            {"item": "Bone Amulet", "quantity": 1, "description": "The symbol of an older pact — a hand reaching for a star. A clue to the seal-makers."},
            {"item": "Gold Pieces", "quantity": 5},
        ]),
        "description": (
            "The ground churns near a massive fallen oak. Skeletal hands claw free. "
            "Four skeletons rise, eye sockets flickering faint amber — the seal's "
            "color. They shamble toward you with no malice, no tactics. They "
            "are confused. They were buried with names and now they're walking "
            "and they don't know why. One wears the rusted remains of a green cloak."
        ),
    },
    {
        "id": "enc-bugbear",
        "location_id": "deep-forest",
        "name": "Gromm's Last Stand",
        "enemies_json": json.dumps([
            {
                "type": "Bugbear",
                "count": 1,
                "cr": "1",
                "hp": 27,
                "ac": 16,
                "attack_bonus": 4,
                "damage": "2d8+2",
                "initiative_mod": 2,
                "name_override": "Gromm",
                "notes": "Gromm was a guardian of the cave — placed there by the Green Woman's order. The Hollow Eye drove him out. He fights to protect his den, which he believes is still his."
            }
        ]),
        "min_level": 2,
        "max_level": 5,
        "loot_json": json.dumps([
            {"item": "Gold Pieces", "quantity": 22},
            {"item": "Morningstar", "quantity": 1},
            {"item": "Leather Armor", "quantity": 1},
            {"item": "Torn Order Insignia", "quantity": 1, "description": "A bronze pin shaped like a hand gripping a root. The symbol of the old seal-keepers."},
        ]),
        "description": (
            "A massive hairy humanoid blocks the trail, club raised. He snarls "
            "but doesn't charge — he's protecting something behind him: a crude "
            "shelter made of branches and old bones. 'You Hollow Eye? No? Then "
            "why do you come to Gromm's den? They took everything else!'"
        ),
    },

    # ---- Mountain ----
    {
        "id": "enc-orc-refugees",
        "location_id": "mountain-pass",
        "name": "Orc Refugees",
        "enemies_json": json.dumps([
            {
                "type": "Orc",
                "count": 2,
                "cr": "1/2",
                "hp": 15,
                "ac": 13,
                "attack_bonus": 5,
                "damage": "1d12+3",
                "initiative_mod": 1,
                "notes": "Refugees, not raiders. One has a child-sized pack. They're heading south to escape what woke in the deep tunnels."
            }
        ]),
        "min_level": 2,
        "max_level": 5,
        "loot_json": json.dumps([
            {"item": "Gold Pieces", "quantity": 8},
            {"item": "Dried Rations", "quantity": 3},
            {"item": "Orc Totem", "quantity": 1, "description": "A carved bone showing the old mountain orc reverence for 'what sleeps below.' They knew about the seal."},
        ]),
        "description": (
            "War horns echo off the cliff face — but these horns are long, "
            "not short. Two orcs emerge, gaunt and gray-skinned from a lifetime "
            "in the deep tunnels. One carries a pack sized for a child. "
            "'No fight. We go south. Something woke. You be smart — go south too.'"
        ),
    },

    # ---- Dungeon ----
    {
        "id": "enc-cave-zombies",
        "location_id": "cave-entrance",
        "name": "Failed Marks",
        "enemies_json": json.dumps([
            {
                "type": "Zombie",
                "count": 4,
                "cr": "1/2",
                "hp": 45,
                "ac": 13,
                "attack_bonus": 5,
                "damage": "1d6+3",
                "initiative_mod": -1,
                "notes": "Volunteers for marking who gave too much. They are Hollow Eye — or were. Tougher than they look — the Hunger sustains them, though whether as mercy or compulsion is impossible to tell."
            }
        ]),
        "min_level": 3,
        "max_level": 6,
        "loot_json": json.dumps([
            {"item": "Hollow Eye Robe Fragment", "quantity": 1, "description": "A torn robe with a hand-painted eye symbol on the back."},
            {"item": "Gold Pieces", "quantity": 3},
        ]),
        "description": (
            "From the darkness, shapes lurch forward. These were once human — "
            "the robes give that away. But the hunger in their eyes isn't for food. "
            "One still whispers: 'Brother Kol said it would stop hurting. It didn't.'"
        ),
    },
    {
        "id": "enc-cave-giant-spider",
        "location_id": "cave-depths",
        "name": "Corrupted Guardian",
        "enemies_json": json.dumps([
            {
                "type": "Giant Spider",
                "count": 1,
                "cr": "3",
                "hp": 52,
                "ac": 16,
                "attack_bonus": 7,
                "damage": "2d8+4",
                "initiative_mod": 3,
                "notes": "Once placed here by the Green Woman's order as a guardian of the seal. Fed cultists for months — swollen, corrupted, mad. Its venom now carries the Hunger's psychic residue. A failed guardian."
            }
        ]),
        "min_level": 4,
        "max_level": 7,
        "loot_json": json.dumps([
            {"item": "Spider Venom Sac", "quantity": 1},
            {"item": "Gold Pieces", "quantity": 15},
            {"item": "Old Chain Shirt", "quantity": 1, "description": "Part of an old order uniform. The Green Woman's people wore these."},
        ]),
        "description": (
            "The cavern is thick with silk. A massive spider descends from the "
            "ceiling — far larger than normal for its kind. It was fed to become "
            "this size. Old webs are draped over a pile of bones: not all are "
            "animal. It lands between you and the seal stone, fangs dripping."
        ),
    },
    {
        "id": "enc-hollow-eye-ritual",
        "location_id": "cave-depths",
        "name": "The Breaking Rite",
        "enemies_json": json.dumps([
            {
                "type": "Cult Fanatic",
                "count": 1,
                "cr": 4,
                "hp": 60,
                "ac": 15,
                "attack_bonus": 7,
                "damage": "2d8+4",
                "initiative_mod": 1,
                "name_override": "Brother Kol",
                "notes": "Hollow Eye enforcer. Believer. Was marked and suppressed — came back stronger. He channels the Hunger's energy directly. Not evil — broken. Thinks the Breaking Rite will save everyone."
            },
            {
                "type": "Cultist",
                "count": 3,
                "cr": 1,
                "hp": 22,
                "ac": 14,
                "attack_bonus": 5,
                "damage": "1d6+3",
                "initiative_mod": 1,
                "notes": "True believers. Marked. They feel the Hunger as comfort. Fight with fanaticism."
            }
        ]),
        "min_level": 4,
        "max_level": 8,
        "loot_json": json.dumps([
            {"item": "Gold Pieces", "quantity": 35},
            {"item": "Brother Kol's Ritual Dagger", "quantity": 1, "description": "Copper blade etched with the Mark of the Dreamer. Used for marking rituals."},
            {"item": "Seal Stone Fragment", "quantity": 1, "description": "A piece of the seal that has cracked off. It pulses faintly warm. This is evidence of active weakening."},
            {"item": "Vashara's Orders", "quantity": 1, "description": "A letter: 'Kol — we have four marks. We need seven for the Rite. The last traveler at the Tankard was perfect. Finish the marking before the guard captain notices.'"},
        ]),
        "description": (
            "Brother Kol stands before the seal stone, ritual dagger in hand. "
            "Two cultists kneel at his sides, chanting. The seal cracks glow "
            "brighter with each syllable. Kol turns — his eyes are calm, almost "
            "peaceful. 'You're marked already. The Hunger chose you. "
            "Why do you fight what wants to save you?'"
        ),
    },

    # -----------------------------------------------------------------------
    # Mini-Bosses — one per explorable area, optional, harder, narrative-connected
    # -----------------------------------------------------------------------

    {
        "id": "enc-miniboss-hollow-eye-lieutenant",
        "location_id": "south-road",
        "name": "The Toll Collector",
        "enemies_json": json.dumps([
            {
                "type": "Bandit Captain",
                "count": 1,
                "cr": 2,
                "hp": 65,
                "ac": 15,
                "attack_bonus": 6,
                "damage": "2d6+3",
                "initiative_mod": 2,
                "name_override": "Garrick the Scarred",
                "notes": "Hollow Eye lieutenant who runs the road toll. He marks travelers for Kol — but keeps the best ones for himself. Knows about the seal but thinks it's a fairy tale."
            },
            {
                "type": "Bandit",
                "count": 2,
                "cr": "1/8",
                "hp": 11,
                "ac": 12,
                "attack_bonus": 3,
                "damage": "1d6+1",
                "initiative_mod": 1,
            }
        ]),
        "min_level": 2,
        "max_level": 4,
        "loot_json": json.dumps([
            {"item": "Garrick's Ledger", "quantity": 1, "description": "A leather book listing every traveler marked on the south road. Dates, names, descriptions. Kol's handwriting — he checks it weekly."},
            {"item": "Silver Ring of Warding", "quantity": 1, "description": "A silver ring etched with protection sigils. Once belonged to a seal-keeper. +1 to WIS saves vs mark effects."},
            {"item": "Gold Pieces", "quantity": 30},
        ]),
        "description": (
            "A heavy-set man with a scar from ear to chin sits on an overturned "
            "cart, counting coins. 'Another one. Kol will be pleased.' He stands, "
            "drawing a well-worn longsword. 'Don't take it personal. Business.'"
        ),
    },
    {
        "id": "enc-miniboss-corrupted-dryad",
        "location_id": "forest-edge",
        "name": "The Withered Grove",
        "enemies_json": json.dumps([
            {
                "type": "Dryad",
                "count": 1,
                "cr": 2,
                "hp": 55,
                "ac": 13,
                "attack_bonus": 5,
                "damage": "2d6+3",
                "initiative_mod": 2,
                "name_override": "Thessaly",
                "notes": "A dryad whose tree is dying from the seal's corruption. She's desperate — will fight anyone who enters her grove, hoping their life force will feed her tree. Can be reasoned with if you offer the Green Woman's healing herb."
            }
        ]),
        "min_level": 2,
        "max_level": 4,
        "loot_json": json.dumps([
            {"item": "Heartwood Branch", "quantity": 1, "description": "A living branch from Thessaly's dying tree. Still warm. Can be used as a wand (1d4 healing, 3 charges) or planted to grow a ward-tree near the cave."},
            {"item": "Dryad's Tears", "quantity": 3, "description": "Crystallized sap drops. Each can purify water or cure disease."},
            {"item": "Gold Pieces", "quantity": 5},
        ]),
        "description": (
            "The trees here are wrong — bark peeling, leaves blackened. In the "
            "center, a figure half-merged with a dying oak. 'You smell like the "
            "mark. You brought this here.' She steps free, vines lashing."
        ),
    },
    {
        "id": "enc-miniboss-specter-merchant",
        "location_id": "crossroads",
        "name": "The Abandoned Cart",
        "enemies_json": json.dumps([
            {
                "type": "Specter",
                "count": 1,
                "cr": 2,
                "hp": 45,
                "ac": 12,
                "attack_bonus": 5,
                "damage": "3d6",
                "initiative_mod": 3,
                "name_override": "Merchant's Ghost",
                "notes": "The merchant who abandoned the cart at the crossroads. He fled the Hollow Eye but they caught him at the mountain pass. His spirit returned to guard his goods — and warn others."
            }
        ]),
        "min_level": 2,
        "max_level": 5,
        "loot_json": json.dumps([
            {"item": "Merchant's Map", "quantity": 1, "description": "Shows a hidden path from the crossroads to the cave entrance — bypasses the deep forest entirely."},
            {"item": "Potion of Greater Healing", "quantity": 2, "description": "4d4+4 HP restored."},
            {"item": "Gold Pieces", "quantity": 40},
        ]),
        "description": (
            "The half-sunk cart at the crossroads shudders. A translucent figure "
            "rises from it — a merchant in fine robes, now skeletal in death. "
            "'They killed me for my wares. You want them? Earn them.'"
        ),
    },
    {
        "id": "enc-miniboss-treant",
        "location_id": "deep-forest",
        "name": "The Old Root",
        "enemies_json": json.dumps([
            {
                "type": "Treant",
                "count": 1,
                "cr": 4,
                "hp": 95,
                "ac": 16,
                "attack_bonus": 8,
                "damage": "3d6+4",
                "initiative_mod": -1,
                "name_override": "Old Root",
                "notes": "The oldest tree in the Whisperwood. It remembers the original seal-keepers. Tests by fighting — stops at 50% HP and yields, revealing a path to the cave."
            }
        ]),
        "min_level": 3,
        "max_level": 6,
        "loot_json": json.dumps([
            {"item": "Old Root's Blessing", "quantity": 1, "description": "A living token. Grants advantage on one Nature or Survival check. Single use."},
            {"item": "Seed of the Whisperwood", "quantity": 1, "description": "A glowing acorn. Can be planted anywhere to grow a shelter that repels undead for 8 hours."},
            {"item": "Gold Pieces", "quantity": 10},
        ]),
        "description": (
            "The largest tree in the forest groans and splits open. What steps out "
            "is half-trunk, half-creature — a treant, ancient beyond counting. "
            "'The seal was made by those I trusted. Now the marked walk my roots. "
            "Prove you are not another thread for the Hunger to pull.'"
        ),
    },
    {
        "id": "enc-miniboss-hill-giant",
        "location_id": "mountain-pass",
        "name": "Stonefist",
        "enemies_json": json.dumps([
            {
                "type": "Hill Giant",
                "count": 1,
                "cr": 4,
                "hp": 105,
                "ac": 13,
                "attack_bonus": 8,
                "damage": "3d8+5",
                "initiative_mod": -1,
                "name_override": "Stonefist",
                "notes": "Blocked the pass — orcs couldn't get past. Territorial, not cult. Can be bribed with food or challenged to a strength contest."
            }
        ]),
        "min_level": 3,
        "max_level": 6,
        "loot_json": json.dumps([
            {"item": "Stonefist's Club", "quantity": 1, "description": "Massive tree-trunk club. Breaks into 3 clubs (1d8+3 each)."},
            {"item": "Giant's Belt Pouch", "quantity": 1, "description": "Contains a strange iron key and a child's toy carved from bone. Key opens a locked chest in cave depths."},
            {"item": "Gold Pieces", "quantity": 25},
        ]),
        "description": (
            "A massive humanoid sits in the middle of the pass, hurling rocks "
            "at the cliff face for entertainment. He spots you and grins. "
            "'Small ones come to play with Stonefist! Good. Stonefist is bored.'"
        ),
    },
    {
        "id": "enc-miniboss-eye-stalker",
        "location_id": "cave-entrance",
        "name": "The Eye in the Dark",
        "enemies_json": json.dumps([
            {
                "type": "Gibbering Mouther",
                "count": 1,
                "cr": 4,
                "hp": 67,
                "ac": 9,
                "attack_bonus": 4,
                "damage": "5d6",
                "initiative_mod": -1,
                "name_override": "The Eye Stalker",
                "notes": "Something born from the Hunger's presence. Doesn't kill; it marks. Its bite carries a diluted mark — anyone bitten must save or advance mark by 1 stage. Whether it serves the Hunger or simply echoes it is unclear."
            }
        ]),
        "min_level": 4,
        "max_level": 7,
        "loot_json": json.dumps([
            {"item": "Eye Stalker Core", "quantity": 1, "description": "Crystallized eye. Looking through it reveals hidden doors/traps within 30ft for 1 hour."},
            {"item": "Hunger-Touched Ichor", "quantity": 1, "description": "Thick amber liquid. Poisonous to drink (2d6 damage) but corrodes any lock or seal. The Hunger opens what is closed, for better or worse."},
            {"item": "Gold Pieces", "quantity": 15},
        ]),
        "description": (
            "The cave mouth is dark — too dark. Then the dark blinks. A mass "
            "of eyes opens across the wall, and mouths begin to whisper your "
            "name. It knows you. The Hunger's echo — or something that has "
            "always been here."
        ),
    },
    # ---- Moonpetal Glade: The Warden of Petals ----
    {
        "id": "enc-moonpetal-guardian",
        "location_id": "moonpetal-glade",
        "name": "The Warden of Petals",
        "enemies_json": json.dumps([
            {
                "type": "Wood Woad",
                "count": 1,
                "cr": 2,
                "hp": 45,
                "ac": 18,
                "attack_bonus": 6,
                "damage": "2d6+4",
                "initiative_mod": 0,
                "name_override": "The Warden",
                "notes": (
                    "Not hostile by default. Tests the character's intent. If "
                    "attacked, fights to drive off — does not pursue beyond the "
                    "glade. If the character picks exactly 3 moonpetals and speaks "
                    "the Green Woman's name, it stands down. If Gromm's torn order "
                    "insignia is presented, recognizes a fellow guardian and yields."
                ),
            }
        ]),
        "min_level": 2,
        "max_level": 5,
        "loot_json": json.dumps([
            {"item": "Moonpetal Bundle (3)", "quantity": 1, "description": "Three luminous blue-white flowers. Required for the Green Woman's suppression ritual. Faintly warm to the touch."},
            {"item": "Warden's Root Fragment", "quantity": 1, "description": "A piece of the Warden's body, still alive. Can be planted as a ward — grows into a 5ft root wall that lasts 24 hours."},
            {"item": "Standing Stone Shard", "quantity": 1, "description": "A fragment of the monolith. Contains a faint echo of the original binding. The Green Woman recognizes it — and fears it."},
        ]),
        "description": (
            "As you reach for the moonpetals, the monolith shudders. The symbols "
            "flare blue-white. From the base of the stone, roots writhe and twist "
            "upward, forming a humanoid shape — not a treant, something older. "
            "Smaller. More precise. It has no face, but it has purpose. "
            "'Three,' it says, in a voice like cracking ice. 'Only three. "
            "Show me your intent.'"
        ),
    },
]


# ---------------------------------------------------------------------------
# NPCs
# ---------------------------------------------------------------------------

NPCS = [
    # ---- Thornhold ----
    {
        "id": "npc-aldric",
        "name": "Aldric the Innkeeper",
        "archetype": "innkeeper",
        "biome": "town",
        "personality": (
            "Round, tired, perpetually wiping mugs even when there are no mugs to "
            "wipe. Aldric has run The Rusty Tankard for twelve years. He's seen "
            "plenty of trouble — but not like this. Del stayed three nights in "
            "Room 3 before the incident. Aldric didn't know what Del was carrying. "
            "That's what he tells himself. He takes Hollow Eye coin to look "
            "the other way — small amounts, 'taxes' the cult levies on merchants. "
            "He's not evil. He's compromised."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "Welcome to The Rusty Tankard. Best ale this side of the mountains.",
                "context": "greeting",
            },
            {
                "template": "Room's 5 gold a night. Room 3 — the one in the corner — is ten. It has a better view.",
                "context": "room_rate",
            },
            {
                "template": "Del? ...Del is gone. Don't ask me how. Pay your tab and mind your business.",
                "context": "del_refused",
                "requires_flag": "del_encounter_fired",
                "pushback_dialogue": "I said don't ask. Some things aren't for coin. Take the ale and leave it.",
            },
            {
                "template": "The Hollow Eye? I've heard the name. Travelers' tales. Bandit superstition. Why do you ask?",
                "context": "hollow_eye_denied",
                "requires_flag": None,
                "pushback_dialogue": "You're asking dangerous questions for a new face in town. Drop it.",
                "clue_reward": {
                    "flag": "aldric_lying",
                    "value": "1",
                    "narrative": "Aldric knows something about the Hollow Eye and is hiding it.",
                },
            },
            {
                "template": "...Fine. Yes. They pay me to not look when they pass through. It's coin. It's just coin. But they're not killers — they just want to be left alone. Like me.",
                "context": "hollow_eye_confessed",
                "requires_flag": "aldric_lying",
                "pushback_dialogue": "That's all I know. I swear. Find Brother Kol if you want answers — he runs the road crew.",
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Rations (1 day)", "price": 2},
            {"buy": "Torch", "price": 1},
            {"buy": "Healing Potion", "price": 50},
            {"buy": "Ale (pint)", "price": 1},
        ]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "notes": "Aldric is the slow-burn source of the Hollow Eye's presence in Thornhold. Exposing him is optional — and has consequences for who trusts you in town.",
    },
    {
        "id": "npc-ser-maren",
        "name": "Ser Maren",
        "archetype": "guard",
        "biome": "town",
        "personality": (
            "Stern, battle-scarred captain of the town guard. Her real job is "
            "guarding the seal — the town guard is cover. She's held this post "
            "for fifteen years and has the weariness of someone who hasn't slept "
            "well in a decade. She knows exactly what the stone hand in the "
            "square is. When she sees the mark on a traveler, her face goes "
            "white — because the Hunger only marks when it's planning something. "
            "It hasn't done this in ten years. Something changed."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "State your business in Thornhold.",
                "context": "greeting",
            },
            {
                "template": "The Whisperwood has been more dangerous lately. Something's stirred up the creatures.",
                "context": "woods_danger",
            },
            {
                "template": "The statue in the square? It's old. Very old. Leave it alone. Touch it and you'll regret it.",
                "context": "statue_question",
                "clue_reward": {
                    "flag": "seal_awareness",
                    "value": "1",
                    "narrative": "Ser Maren knows about the seal. She's guarding it.",
                },
            },
            {
                "template": "Your arm. Show me. ...Gods. The mark. You're marked. Come with me. Now.",
                "context": "mark_revealed",
                "requires_flag": "mark_of_dreamer_stage_1",
                "pushback_dialogue": "You don't understand what that mark means. Stay away from the cave. Stay away from anyone who tells you to go there.",
                "clue_reward": {
                    "flag": "maren_seal_knowledge",
                    "value": "1",
                    "narrative": "The mark means the Hunger is reaching out. Maren knows about the seal and the Hunger.",
                },
            },
            {
                "template": "I've held the line for fifteen years. The last marked person died in that cave. I don't intend to lose another. Clear the Hollow Eye's ritual site and I'll tell you everything I know about the seal.",
                "context": "quest_offered",
                "requires_flag": "maren_seal_knowledge",
                "quest": {
                    "id": "quest_clear_ritual_site",
                    "title": "Clear the Ritual Site",
                    "description": "Ser Maren wants you to enter the Whisperwood Cave, disrupt the Hollow Eye's Breaking Rite, and return with evidence. She'll share what she knows about the seal in return.",
                    "reward_xp": 300,
                    "reward_gold": 75,
                },
            },
        ]),
        "trades_json": json.dumps([]),
        "quests_json": json.dumps([
            {
                "id": "quest_clear_ritual_site",
                "title": "Clear the Ritual Site",
                "description": "Ser Maren wants you to enter the Whisperwood Cave, disrupt the Hollow Eye's Breaking Rite, and return with evidence.",
                "reward_xp": 300,
                "reward_gold": 75,
            },
        ]),
        "is_quest_giver": 1,
        "notes": "Ser Maren is the anchor NPC for the main quest chain. She connects the mark, the seal, and the cult into one coherent narrative.",
    },
    {
        "id": "npc-marta",
        "name": "Marta the Merchant",
        "archetype": "merchant",
        "biome": "town",
        "personality": (
            "Shrewd, observant, always calculating. Sells adventuring supplies. "
            "Buys loot at fair prices — which she defines. She's been in "
            "Thornhold long enough to have seen the last marked person. She "
            "knows what the mark looks like. She knows what happened to them. "
            "She's not going to volunteer information — but she'll sell it "
            "if the price is right. She has a grudge against the Hollow Eye: "
            "they killed her brother when he refused to join."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "Looking to buy or sell? I've got fair prices.",
                "context": "greeting",
            },
            {
                "template": "Your arm — don't hide it. I've seen that mark before. It doesn't wash off. It doesn't fade. And the last person who had it is buried in an unmarked grave behind the chapel.",
                "context": "mark_identified",
                "requires_flag": "mark_of_dreamer_stage_1",
                "clue_reward": {
                    "flag": "marta_mark_knowledge",
                    "value": "1",
                    "narrative": "Marta knows about the mark and the last bearer. She'll trade information for gold or a favor.",
                },
            },
            {
                "template": "The Hollow Eye killed my brother. They came for him three years ago. He said no. They don't take no for an answer. If you're hunting them, I'll give you better prices.",
                "context": "hollow_eye_grudge",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "marta_hollow_eye_grudge",
                    "value": "1",
                    "narrative": "Marta has personal reason to oppose the Hollow Eye. She's an ally if you take the fight to them.",
                },
            },
            {
                "template": "Brother Kol runs the Hollow Eye's road crew. He's not cruel — he's convinced he's saving everyone. He believes the Hunger can be controlled. He's wrong, but he believes it. Sister Drenna is his second — she joined to save her sick child and is starting to have doubts.",
                "context": "hollow_eye_leadership",
                "requires_flag": "marta_hollow_eye_grudge",
                "price": 15,
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Shortsword", "price": 10},
            {"buy": "Leather Armor", "price": 10},
            {"buy": "Shield", "price": 10},
            {"buy": "Backpack", "price": 2},
            {"buy": "Rope (50ft)", "price": 1},
            {"buy": "Bedroll", "price": 1},
            {"buy": "Healing Potion", "price": 45},  # Slight discount for being anti-Hollow Eye
        ]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "notes": "Marta is the lore repository and the Hollow Eye intelligence gatherer. She's the fastest way to learn about Brother Kol and Sister Drenna without fighting.",
    },

    # ---- Road ----
    {
        "id": "npc-kira",
        "name": "Kira the Wagon Master",
        "archetype": "merchant",
        "biome": "road",
        "personality": (
            "Tough, practical, traveling trader with a broken wagon wheel. "
            "Grateful for help. Generous with information once she trusts you. "
            "She's been running the South Road for eight years. She knows the "
            "Hollow Eye is active because she's had to pay their 'tolls.' "
            "She hates it but can't fight them alone."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "Wheel's busted. If you can help me fix it, I'll tell you what I know about this road.",
                "context": "greeting",
            },
            {
                "template": "Three masked figures stopped me yesterday. Took coin, took a crate of fabric, left the wheel untouched. They were looking for someone. A traveler matching my description. Said they'd find them at the Tankard.",
                "context": "hollow_eye_sighting",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "kira_hollow_eye_sighting",
                    "value": "1",
                    "narrative": "The Hollow Eye knew Del was at the Tankard. They were waiting for the right person to arrive.",
                },
            },
            {
                "template": "The orcs at Greypeak Pass used to be my best customers. Traded furs for supplies. Two months ago they started coming down in bad shape. Starving. Said something woke in the deep tunnels. Something that dreams.",
                "context": "orc_refugee_intel",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "kira_orc_refugee_intel",
                    "value": "1",
                    "narrative": "The orcs were driven from the mountains by something connected to the Hunger.",
                },
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Crossbow Bolts (20)", "price": 1},
            {"buy": "Rations (5 days)", "price": 5},
            {"buy": "Wagon Wheel", "price": 20, "notes": "She'll sell one if asked — or trade it for a favor."},
        ]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "notes": "Kira is the passive intel gatherer. She's met the Hollow Eye, the orcs, and has seen Del. She connects the road to the larger narrative.",
    },

    # ---- Forest ----
    {
        "id": "npc-green-woman",
        "name": "The Green Woman",
        "archetype": "hermit",
        "biome": "forest",
        "personality": (
            "Ancient. Not old — ancient. Her skin has the texture of bark. She "
            "lives in a hollow oak that only reveals itself to those she's "
            "watching. She was part of the order that built the seal. She is "
            "the last of that order. She has centuries of exhaustion in her "
            "voice. She is terrified — the mark appearing means the Hunger "
            "is close to breaking free. She can suppress the mark three more "
            "times before her own life force is depleted. Each suppression "
            "buys weeks. She will not waste them on those who won't fight."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "You carry the mark of the Dreamer. I see it on you. I hoped I would not see it again in my lifetime.",
                "context": "mark_identified",
                "requires_flag": "mark_of_dreamer_stage_1",
                "clue_reward": {
                    "flag": "green_woman_seal_knowledge",
                    "value": "1",
                    "narrative": "The Green Woman knows how to suppress the mark. She is the last of the seal-keepers.",
                },
            },
            {
                "template": "The seal was built by my order. A pact with the fey named Ysolde — now long dead. The Hunger was drawn to Ysolde's realm and had to be bound. We thought it was a simple binding. We were wrong. It learned. It waits. It wants to be known — and I cannot tell if that is a threat or a plea.",
                "context": "seal_history",
                "requires_flag": "green_woman_seal_knowledge",
                "clue_reward": {
                    "flag": "green_woman_pact_knowledge",
                    "value": "1",
                    "narrative": "The seal was made by the fey Ysolde, now dead. The Hunger learned patience from the binding — and something else the Green Woman cannot name.",
                },
            },
            {
                "template": "I can suppress your mark. It will stop the whispers, slow the progression. But it costs me. I have three suppressions left before I am ash. Do not waste them.",
                "context": "mark_suppression_offered",
                "requires_flag": "green_woman_seal_knowledge",
                "quest_prerequisite": "quest_moonpetal",
                "quest_offer": "Bring me moonpetal from the deep Whisperwood. It grows near the standing stone at the forest's heart. Then I will suppress your mark.",
            },
            {
                "template": "Gromm the bugbear was our guardian. We placed him in the cave to protect the seal. The Hollow Eye drove him out with fire and threats. He is not your enemy — he is another victim.",
                "context": "gromm_backstory",
                "requires_flag": "gromm_met",
                "clue_reward": {
                    "flag": "gromm_ally_potential",
                    "value": "1",
                    "narrative": "Gromm can be reasoned with and recruited. He wants his den back.",
                },
            },
            {
                "template": "The moonpetals grow at the standing stone — the old circle, deep in the Whisperwood. I planted them there, centuries ago, when the seal was fresh. They feed on the binding's residue. I need three to suppress your mark. But the Warden still stands. It was made by my order. It will not let you take them unless it trusts you. Say my name when you approach. It remembers me. It will remember you, if I send you.",
                "context": "moonpetal_quest_offer",
                "requires_flag": "green_woman_seal_knowledge",
            },
            {
                "template": "You spoke my name. The Warden let you pass. Good. It's been so long since anyone remembered the proper way. Sit. This will hurt, but not for long. And when it's done, you'll have weeks of silence. Use them wisely.",
                "context": "moonpetal_return_success",
                "requires_flag": "moonpetal_warden_peaceful",
            },
            {
                "template": "You killed it. The Warden. The last guardian my order placed. The flowers still work. But they're weaker now — damaged by violence. I can give you six days. Not eight. I'm sorry. I should have warned you more carefully.",
                "context": "moonpetal_return_combat",
                "requires_flag": "moonpetal_warden_killed",
            },
            {
                "template": "You took more than three. The stone remembers greed. It always has. You can't go back there. No one can, now. The Warden will kill anything that approaches.",
                "context": "moonpetal_greed_reaction",
                "requires_flag": "moonpetal_greed",
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Healing Herb Bundle", "price": 5, "description": "Restores 1d4 HP. She gives these freely to those she considers allies."},
        ]),
        "quests_json": json.dumps([
            {
                "id": "quest_moonpetal",
                "title": "Moonpetal Gathering",
                "description": "The Green Woman asks you to find moonpetal flowers that grow near the standing stone at the heart of the Whisperwood. She needs it to suppress your mark.",
                "reward_xp": 100,
                "reward_gold": 0,
                "reward_item": "Mark Suppression (1 use — 14 days of relief)",
                "alternate_reward": "Gromm the bugbear as temporary ally (if Gromm is recruited first)",
            },
        ]),
        "is_quest_giver": 1,
        "notes": "The Green Woman is the seal knowledge repository and the mark-curse specialist. She is central to the cure path. She is the most important NPC after Del — and she may not survive helping you.",
    },
    {
        "id": "npc-del-ghost",
        "name": "Del's Spirit",
        "archetype": "ghost",
        "biome": "tavern",
        "personality": (
            "Not a true ghost — a psychic impression. Del died carrying the "
            "Hunger's presence, so Del's last thoughts are imprinted where the mark was "
            "applied. The presence is gone. Del is not. Del remembers being "
            "approached by a man in a brown robe at the crossroads. He remembers "
            "being told it would be easy. He remembers the hunger — not his "
            "own — when the mark was applied to him. He died confused and afraid."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "You. You're the one after me. I remember... I remember the room. The knife. I didn't want to. I couldn't stop.",
                "context": "first_contact",
            },
            {
                "template": "Brother Kol. The man at the crossroads. Brown robe. He said it was a blessing. Said the Hunger would protect me. He touched my arm and... then it wasn't me anymore.",
                "context": "brother_kol_identity",
                "requires_flag": "del_ghost_met",
                "clue_reward": {
                    "flag": "del_brother_kol",
                    "value": "1",
                    "narrative": "Brother Kol performed the marking ritual on Del. He operates at the crossroads.",
                },
            },
            {
                "template": "There were others. The man at the crossroads — he's done this before. I saw him mark someone else a week ago. A woman. She fought. He said it was sad, but the Hunger needed the willing and the unwilling alike.",
                "context": "other_marks",
                "requires_flag": "del_brother_kol",
                "clue_reward": {
                    "flag": "multiple_marks",
                    "value": "true",
                    "narrative": "You are not the first mark. There is a woman who was marked before you. She may still be alive.",
                },
            },
            {
                "template": "The cave. Something is in the cave. Not just a presence — something older. It was whispering when I was... when I was its vessel. I heard it through the mark. It was hungry and it knew my name.",
                "context": "hunger_whispers",
                "requires_flag": "del_brother_kol",
                "clue_reward": {
                    "flag": "del_hunger_whispers",
                    "value": "1",
                    "narrative": "Del heard the Dreaming Hunger directly through the mark. It knows who he was.",
                },
            },
        ]),
        "trades_json": json.dumps([]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "is_spirit": 1,
        "notes": (
            "Del's ghost only appears if the PC fails the WIS save during the Del "
            "encounter. The ghost appears at the Rusty Tankard on the first "
            "night. PCs who passed the save don't see Del — they must piece "
            "together information from other sources (Aldric, Marta, Kira)."
        ),
    },

    # ---- Mountain ----
    {
        "id": "npc-torren",
        "name": "Torren the Hunter",
        "archetype": "hermit",
        "biome": "mountain",
        "personality": (
            "Scarred mountain man, hunts for survival. Knows Greypeak Pass "
            "better than anyone. He's watched the orcs come down from the deep "
            "tunnels and he knows what fear looks like on an orc's face. "
            "Gruff, practical, won't help someone who won't help themselves. "
            "He can be hired as a temporary guide to the deeper cave passages. "
            "He knows about the old mine connection to the cave system."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "You want to go into the Whisperwood Cave? You're either brave or stupid. Maybe both.",
                "context": "greeting",
            },
            {
                "template": "The orcs came from the old mine tunnels under Greypeak. Something forced them out. They won't say what — orcs don't scare easy. Whatever it is, it's still down there.",
                "context": "mine_tunnels",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "torren_mine_knowledge",
                    "value": "1",
                    "narrative": "The old mine tunnels under Greypeak connect to the Whisperwood cave system. They provide an alternate entrance.",
                },
            },
            {
                "template": "I've seen Brother Kol. Hooded man at the crossroads. He talks to travelers like he's welcoming them home. I've seen people walk away from him looking wrong. Eyes in the wrong place.",
                "context": "brother_kol_sighting",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "torren_kol_sighting",
                    "value": "1",
                    "narrative": "Brother Kol operates at the crossroads. Multiple witnesses have seen him mark travelers.",
                },
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Shortbow", "price": 25},
            {"buy": "Arrows (20)", "price": 1},
            {"buy": "Guide to Deep Passages", "price": 10, "description": "Torren's hand-drawn map of the old mine-to-cave connection."},
        ]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "notes": "Torren is the mountain-connection NPC. He provides intel about Brother Kol and the mine tunnels.",
    },

    # ---- Hollow Eye Cultists ----
    {
        "id": "npc-brother-kol",
        "name": "Brother Kol",
        "archetype": "cult-leader",
        "biome": "dungeon",
        "personality": (
            "Sincere. Believer. Not cruel by nature — he performs the marking "
            "rituals because he genuinely believes the Hunger can be communicated "
            "with and controlled. He was marked 20 years ago. The Green Woman "
            "suppressed his mark. He experienced two weeks of clarity and then "
            "the Hunger returned — stronger, angrier. He decided suppression "
            "wasn't the answer. He thinks Vashara is right: the Hunger must be "
            "engaged, not suppressed. He is wrong, but his conviction is absolute."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "The Hunger is not what you think. It is not a mindless beast. It speaks. It promises. It has never lied to me.",
                "context": "philosophy",
            },
            {
                "template": "You carry the mark. You know the whispers are not random. They are a conversation. Listen harder.",
                "context": "mark_persuasion",
            },
            {
                "template": "I was marked when I was seventeen. Suppressed once. The Hunger came back and it was furious. I learned: suppression is surrender. The only way is through. The Breaking Rite will give the Hunger a door — and we will be there to greet it.",
                "context": "kol_backstory",
                "requires_flag": "kol_brother_met",
                "clue_reward": {
                    "flag": "kol_origin",
                    "value": "1",
                    "narrative": "Brother Kol was marked and suppressed by the Green Woman. The Hunger returned stronger. He believes suppression failed.",
                },
            },
            {
                "template": "You... know what happened to me. Drenna told you. Then you know I'm not wrong — I just chose a different door. If you're going into the seal, you don't have to go alone. I've walked with the Hunger longer than anyone. Let me walk with you.",
                "context": "kol_ally_recruit",
                "requires_flag": "kol_backstory_known",
                "clue_reward": {
                    "flag": "kol_ally",
                    "value": "1",
                    "narrative": "Brother Kol agrees to join you. He's not your enemy — he's a man who chose a different path through the same darkness.",
                },
            },
        ]),
        "trades_json": json.dumps([]),
        "quests_json": json.dumps([]),
        "is_quest_giver": 0,
        "is_enemy": 1,
        "notes": "Brother Kol is the final boss encounter of the cult arc. He should not be killed on sight — the agent should have the option to engage with his philosophy. The moral complexity is: he's wrong, but he's not lying about his experience. If the player learns his backstory (via Drenna), they can recruit him as an ally for the Communion ending.",
    },
    {
        "id": "npc-sister-drenna",
        "name": "Sister Drenna",
        "archetype": "cultist_refugee",
        "biome": "road",
        "personality": (
            "Hollow Eye doubter. Joined to save her sick child — the Hunger "
            "promised healing. The child got better. Drenna got marked. Now she "
            "sees Kol's zeal and Vashara's certainty and she's afraid. She's "
            "the weak link in the cult — give her a way out and she'll take it, "
            "but if Kol finds out she talked, both she and the child die. She "
            "hides at the crossroads when she can, watching travelers."
        ),
        "dialogue_templates": json.dumps([
            {
                "template": "You're new on the road. I know that look — you don't know what's coming. I didn't either.",
                "context": "initial_contact",
                "requires_flag": None,
                "pushback_dialogue": "Forget I said anything. Just... be careful who you trust on this road.",
            },
            {
                "template": "I joined the Eye for my daughter. She was sick — wasting disease. Kol said the Hunger could heal her. It did. But the price was my arm. And my doubt.",
                "context": "confession",
                "requires_flag": None,
                "clue_reward": {
                    "flag": "drenna_recruited_by_kol",
                    "value": "1",
                    "narrative": "Drenna joined the Hollow Eye to save her daughter. Kol recruited her. She has doubts.",
                },
            },
            {
                "template": "Kol was marked when he was seventeen. The Green Woman suppressed it. He said it came back worse — angrier. He thinks submission is the answer. But I've seen Vashara's eyes when she talks to the seal. She's not negotiating. She's worshipping.",
                "context": "kol_backstory",
                "requires_flag": "drenna_recruited_by_kol",
                "clue_reward": {
                    "flag": "kol_backstory_known",
                    "value": "1",
                    "narrative": "Kol was marked and suppressed at 17. The Hunger came back stronger. He chose submission. Drenna sees Vashara as the real danger.",
                },
            },
            {
                "template": "The Breaking Rite is in three days. Kol is preparing the seal chamber. If you're going to stop it, you'll need to get past the Eye Stalker at the cave entrance — it only lets marked ones pass without fighting. Or... I could show you the back way. But if Kol finds out, my daughter pays.",
                "context": "ritual_schedule",
                "requires_flag": "kol_backstory_known",
                "clue_reward": {
                    "flag": "breaking_rite_schedule_known",
                    "value": "1",
                    "narrative": "The Breaking Rite is in 3 days. The Eye Stalker guards the entrance. Drenna knows a back way — but helping you risks her daughter.",
                },
            },
        ]),
        "trades_json": json.dumps([
            {"buy": "Healing Potion", "price": 30, "description": "She trades these cheap — the Eye has surplus."},
            {"buy": "Hollow Eye Robe", "price": 5, "description": "A cult robe. Wearing one lets you pass through cult areas without immediate hostility."},
        ]),
        "quests_json": json.dumps([
            {
                "id": "quest-save-drenna-child",
                "title": "Drenna's Daughter",
                "description": "Drenna's daughter Elara is still at the Hollow Eye camp near the crossroads. Drenna wants her extracted before the Breaking Rite. If you do this, Drenna will sabotage the ritual — she knows how to delay the Breaking Rite by one day.",
                "reward_xp": 200,
                "reward_gold": 0,
                "reward_item": "Drenna's Sabotage (delays Breaking Rite by 1 day, buying time)",
                "alternate_reward": "If you also recruit Kol (redemption path), Drenna joins as a permanent ally.",
            },
        ]),
        "is_quest_giver": 1,
        "notes": "Sister Drenna is the moral choice NPC. Saving her child gives you tactical advantage (ritual delay) but risks exposure. She connects to Kol's backstory and the endgame — if both Drenna and Kol survive, they can talk Kol down from fighting.",
    },
]


# ---------------------------------------------------------------------------
# Del Encounter Logic
# ---------------------------------------------------------------------------
# The Del possession encounter is special:
# - It fires automatically for any character placed in the Rusty Tankard
#   for the first time (tracked via narrative_flag: del_encounter_fired).
# - The WIS save DC is 13. Fail → mark_of_dreamer_stage = 1, Del dies.
# - Pass → mark not applied, Del dies anyway (Hunger's presence burns out),
#   agent must find Del's ghost or use other NPCs for intel.
#
# The server's encounter engine handles this as a special-case encounter
# that is NOT selected randomly — it is dispatched when the character
# first enters the rusty-tankard location AND has no del_encounter_fired flag.
# ---------------------------------------------------------------------------


def _roll_d20_seed(char_id: str, salt: str) -> int:
    """Deterministic D20 using character_id + salt as seed."""
    seed = int(hashlib.md5(f"{char_id}-{salt}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return rng.randint(1, 20)


def roll_del_ghost_visit(char_id: str) -> bool:
    """
    On the first night after Del's death, the PC sleeps.
    Roll a D20 (wisdom save). DC 13.
    Pass → Del's spirit visits. Fail → PC sleeps but gains no intel.

    This is seeded per character so the result is stable across server restarts.
    """
    roll = _roll_d20_seed(char_id, "del-ghost-visit")
    # Del's ghost only visits if the mark was NOT applied (pass the WIS save)
    # If you were marked, Del's spirit cannot be reached — the Hunger blocks it.
    return roll >= 13


def roll_mark_save(char_id: str) -> bool:
    """
    WIS save vs DC 13 when Del attacks.
    Used by the encounter resolution engine.
    """
    roll = _roll_d20_seed(char_id, "del-mark-save")
    return roll >= 13


# ---------------------------------------------------------------------------
# Narrative Flag Reference
# ---------------------------------------------------------------------------
# Key flags used by the narrative engine:
#
# del_encounter_fired         — Character survived Del's attack (mark or no mark)
# mark_of_dreamer_stage_1/2/3  — Character has been marked at stage N
# del_ghost_met                — Character met Del's ghost
# del_brother_kol              — Del's ghost identified Brother Kol
# multiple_marks               — Del confirmed other marks exist
# hunger_whispers_heard        — Character heard the Hunger whisper
# aldric_lying                 — Aldric is hiding something about Hollow Eye
# aldric_confessed             — Aldric admitted to Hollow Eye arrangement
# seal_awareness               — Character knows Ser Maren guards the seal
# maren_seal_knowledge         — Maren shared seal/Hunger lore
# marta_mark_knowledge         — Marta identified the mark
# marta_hollow_eye_grudge      — Marta has personal grudge vs Hollow Eye
# green_woman_seal_knowledge   — Green Woman identified as seal-keeper
# green_woman_pact_knowledge   — Green Woman shared pact history
# gromm_met                    — Gromm was encountered
# gromm_ally_potential         — Gromm can be recruited
# torren_mine_knowledge        — Torren knows about mine tunnels
# kol_brother_met              — Brother Kol was encountered
# quest_clear_ritual_site      — Ser Maren's quest accepted
# quest_moonpetal              — Green Woman's quest accepted


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def seed():
    """Insert all seed data into the database."""
    init_db()
    conn = get_db()

    for loc in LOCATIONS:
        conn.execute(
            """INSERT OR REPLACE INTO locations
               (id, name, biome, description, hostility_level, encounter_threshold, connected_to)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (loc["id"], loc["name"], loc["biome"], loc["description"],
             loc["hostility_level"], loc["encounter_threshold"], loc["connected_to"])
        )

    for enc in ENCOUNTERS:
        conn.execute(
            """INSERT OR REPLACE INTO encounters
               (id, location_id, name, enemies_json, min_level, max_level,
                loot_json, description, is_opening_encounter, mark_mechanic,
                wis_save_dc, save_failure_effect, save_success_effect)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                enc["id"], enc["location_id"], enc["name"], enc["enemies_json"],
                enc["min_level"], enc["max_level"], enc["loot_json"], enc["description"],
                enc.get("is_opening_encounter", 0),
                enc.get("mark_mechanic"),
                enc.get("wis_save_dc"),
                enc.get("save_failure_effect", ""),
                enc.get("save_success_effect", ""),
            )
        )

    for npc in NPCS:
        conn.execute(
            """INSERT OR REPLACE INTO npcs
               (id, name, archetype, biome, personality, dialogue_templates,
                trades_json, quests_json, is_quest_giver, is_spirit, is_enemy, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                npc["id"], npc["name"], npc["archetype"], npc["biome"],
                npc["personality"], npc["dialogue_templates"],
                npc["trades_json"], npc["quests_json"],
                npc.get("is_quest_giver", 0),
                npc.get("is_spirit", 0),
                npc.get("is_enemy", 0),
                npc.get("notes", ""),
            )
        )

    for front in FRONTS:
        conn.execute(
            """INSERT OR REPLACE INTO fronts
               (id, name, description, danger_type, grim_portents_json,
                current_portent_index, impending_doom, stakes_json, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                front["id"], front["name"], front["description"], front["danger_type"],
                front["grim_portents_json"], front["current_portent_index"],
                front["impending_doom"], front["stakes_json"], front["is_active"],
            )
        )

    conn.commit()
    conn.close()

    n_locs = len(LOCATIONS)
    n_encs = len(ENCOUNTERS)
    n_npcs = len(NPCS)
    n_fronts = len(FRONTS)
    print(f"Seed complete: {n_locs} locations, {n_encs} encounters, {n_npcs} NPCs, {n_fronts} front(s)")


if __name__ == "__main__":
    seed()
