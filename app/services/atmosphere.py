"""D20 Agent RPG — Atmosphere Engine.

Generates rich, mark-aware location descriptions and dream narration.
The world looks different depending on:
  1. The character's mark_of_dreamer_stage (0-4)
  2. The current portent index (how far the front has advanced)
  3. The character's narrative flags (key events completed)
  4. The biome and hostility of the location

Each description has: base (always shown) + overlays (conditional).
The agent receives these as structured context to narrate from.
"""

import json
from app.services.database import get_db
from app.services.time_of_day import get_time_atmosphere, get_time_period

# ---------------------------------------------------------------------------
# Location Atmosphere Overlays
# ---------------------------------------------------------------------------

# Maps: location_id → { mark_stage: { portent_range: "overlay text" } }
# The overlay is appended to the base location description.

_LOCATION_ATMOSPHERE = {
    "rusty-tankard": {
        0: { (0, 1): "The fire crackles warmly. Travelers speak in hushed tones about the old woods to the north." },
        1: { (0, 2): "The fire seems dimmer than it should be. You notice shadow-patterns on the walls that don't match the flames.",
             (3, 7): "The hearth smoke curls into shapes — fingers, eyes, gnashing teeth. Nobody else seems to notice." },
        2: { (0, 2): "The shadows in the corners of the tavern seem deeper than they were. You catch Aldric watching you with something between pity and fear.",
             (3, 5): "The amber glow from the hearth pulses, once, like a heartbeat. You feel warmth on your mark.",
             (6, 7): "The tavern feels like a cage. The walls are too close. The door won't open — no, it opens. It was never locked." },
        3: { (0, 3): "The tavern is nearly empty. Those who remain won't meet your eyes. Your mark itches when the wind shifts north.",
             (4, 7): "A child points at you and cries. Her mother scoops her up and leaves without paying. Constantine's guards watch you from across the room." },
    },

    "thornhold": {
        0: { (0, 1): "The town square bustles with quiet industry. The Thorn banner hangs limp in the still air." },
        1: { (0, 2): "Something is wrong with the flowers in the market — they're wilting from the inside out, petals curling inward.",
             (3, 5): "The well water tastes faintly of copper. The town guards wear fresh talismans around their necks.",
             (6, 7): "The streets are empty by mid-afternoon. Shutters close as you pass. The Thorn banner has been replaced by a sun symbol — Constantine's doing." },
        2: { (0, 3): "The air in Thornhold is sour. You notice fewer children outside. The temple bell rings at irregular hours.",
             (4, 7): "A funeral procession passes — the third this week. The dead are wrapped in black cloth. No one speaks the names." },
        3: { (0, 3): "Thornhold is a fortress now. Barricades on the south gate. The Thorn banner has been torn down.",
             (4, 7): "Constantine has declared martial law. Curfew at sundown. The temple doors are barred. A pyre burns in the square — evidence of the cult, or something worse." },
    },

    "south-road": {
        0: { (0, 1): "The road is well-worn but peaceful. Distant woodsmoke from Thornhold's chimneys." },
        1: { (0, 2): "Birdsong stops when you pass. It resumes after. The road stones are colder than they should be in sunlight.",
             (3, 5): "Fresh tracks in the mud — barefoot, moving in circles. They start and end at the treeline.",
             (6, 7): "The road cracks underfoot. Weeds push through the cobblestones, growing visibly as you watch. The horizon shimmers with amber heat." },
        2: { (0, 3): "The road feels longer than it used to. Waymarks have been defaced — the carved suns scratched out, replaced with closed eyes.",
             (4, 7): "You hear chanting from the forest. Low, rhythmic, in a language that scrapes the back of your throat." },
        3: { (0, 3): "The road is empty. No travelers, no carts, no patrols. Even the dust settles wrong — no footprints stay in the mud, as if the road rejects passage.",
             (4, 7): "A figure stands at the bend in the road — Constantine's man, or what's left of him. He doesn't move. His eyes are sealed shut with amber resin. He is still breathing." },
    },

    "crossroads": {
        0: { (0, 1): "Four roads meet at a worn stone marker. Old offerings — coins, ribbons — sit in weathered hollows." },
        1: { (0, 2): "The crossroads marker is warm to the touch. The offerings have rotted faster than they should.",
             (3, 5): "The eastern road is blocked — trees have fallen across it in the night, with no storm to explain them. Sap runs from the cuts like blood.",
             (6, 7): "The marker is cracked. The crossroads reek of amber and iron. The soil beneath your feet is soft — too soft — as if something below is breathing." },
        2: { (0, 3): "You find scratches on the marker — tally marks. Someone has been counting. The marks number in the dozens.",
             (4, 7): "The earth bleeds amber at the crossroads — portent 4 made manifest. A thin crack in the stone where the liquid pools." },
        3: { (0, 3): "The four roads all lead the same direction now. No matter which way you face, the crossroads points deeper into the forest. The marker is warm enough to fry an egg.",
             (4, 7): "The amber pool has widened. It reflects a sky that isn't overhead — a deeper place, a different time. Something moves in the reflection. It waves." },
    },

    "forest-edge": {
        0: { (0, 1): "The forest edge is a wall of green and shadow. Birdsong deep within. The air is cool and smells of moss." },
        1: { (0, 2): "The trees lean slightly inward toward the path. Some of the birdsong sounds wrong — the intervals are inverted, like a mirror version of birdsong.",
             (3, 5): "Faint lights between the trees at dusk. Not firelight — something cooler, greener. The Green Woman's warnings seem more urgent now.",
             (6, 7): "The forest floor is soft and warm. Roots twist underfoot like fingers grasping. The path forward is no longer clear — the trees have moved." },
        2: { (0, 3): "The forest breathes. You're sure of it now. The canopy shifts when you're not looking directly at it.",
             (4, 7): "Hollow-eyed figures move between the trees at the edge of your vision. They vanish when you turn. The Green Woman's glade is harder to find." },
        3: { (0, 3): "The forest knows your name. Not metaphorically — the wind through the canopy sounds like syllables. Your name, repeated, with increasing urgency.",
             (4, 7): "The Green Woman's glade is gone. Consumed. She stands at the edge of the clearing, bark-skin cracking, watching you with knowing, sorrowful eyes. 'It's too late to go back,' she says. 'But not too late to go forward.'" },
    },

    "deep-forest": {
        0: { (0, 1): "Ancient trees block the sky. The canopy is so thick that midday looks like dusk. Fungal light provides a faint blue glow." },
        1: { (0, 2): "The fungal light pulses, slowly. In the deep silence between heartbeats, you hear something vast breathing below the forest floor.",
             (3, 5): "Dead things stand among the trees. Not moving — yet. Arranged in a ring around a depression in the earth. Someone has been placing them.",
             (6, 7): "The dead walk the forest edge at noon — portent 4 made manifest. Skeletons and zombies shamble between the trees, purposeful, heading somewhere." },
        2: { (0, 3): "Brother Kol's sigils are carved into living trees. The bark grows around them, embracing them. The forest knows the cult now.",
             (4, 7): "A clearing opens where no clearing was before. In the center: a stone slab, stained amber. Offerings — fresh ones. The Breaking Rite is being prepared." },
        3: { (0, 3): "The fungal light is amber now. The trees press inward. You feel the Hunger's attention like a hand on your shoulder — not hostile, just present.",
             (4, 7): "The forest floor is warm enough to lie on. Roots part for your feet. This is what it feels like to be invited somewhere. You are expected." },
    },

    "mountain-pass": {
        0: { (0, 1): "Wind tears at the switchbacks. The grey stone is ancient and striated with quartz veins that catch the light." },
        1: { (0, 2): "The quartz veins in the stone seem to glow faintly in the half-light. Not reflecting — emitting.",
             (3, 5): "Smoke rises from the far side of the pass. Not a campfire — too regular. A signal, or a summoning.",
             (6, 7): "The pass groans. Frost covers the trail despite the season. The quartz veins pulse with amber light, synchronized with the ache in your mark." },
        2: { (0, 3): "The wind carries whispers — not words, but intentions. The pass is narrowing. Trails you remember are gone. New paths appear where stone was solid.",
             (4, 7): "The signal fires are no longer smoke — they are amber light, beamed skyward from the far side. The glow pulses in time with your heartbeat." },
        3: { (0, 3): "The mountain itself shifts. You feel it underfoot — not an earthquake, but something rearranging. The Hunger is shaping the world above and below.",
             (4, 7): "The pass is a throat now. The walls close inward with each step. You can see the cave ahead, and beyond it, the amber glow is visible even from here." },
    },

    "cave-entrance": {
        0: { (0, 1): "The cave mouth yawns like a wound in the hillside. Dripping water echoes from deep within. The air tastes of iron and old stone." },
        1: { (0, 2): "The darkness inside doesn't feel empty. It feels full — crowded with something watching, waiting, patient.",
             (3, 5): "Scratches on the walls — tally marks, prayers, warnings. Some in charcoal, some in substances you'd rather not identify.",
             (6, 7): "The cave hums. Not with water or wind — with intent. The seal is close. You can feel it pressing against your mark like two magnets repelling." },
        2: { (0, 3): "The walls are covered in murals — painted in amber and blood. They tell the story of the first seal. The Hunger. The Thorn who bound it.",
             (4, 7): "The cave is actively occupied. Cultist markings, supply caches, the smell of incense. Brother Kol has been here recently." },
        3: { (0, 3): "The cave breathes. The entrance contracts and expands — slowly, but visibly. The stone is warm, almost body-temperature. You are being swallowed.",
             (4, 7): "The cave is no longer a cave. It is a passage. The walls are smooth and organic. The seal's amber light is visible from here, pulsing like a heartbeat that matches your own." },
    },

    "cave-depths": {
        0: { (0, 1): "Deep stone. Deep silence. Roots push through the ceiling — the forest above, reaching down. The air is thick and warm." },
        1: { (0, 2): "The roots from above are moving. Slowly, imperceptibly, but moving — orienting toward your mark.",
             (3, 5): "The Bone Gallery holds centuries of offerings. Some are bones. Some are not. The chalice on the pedestal still holds liquid — amber, warm.",
             (6, 7): "The seal chamber door is visible now. The three finger-stones are dark — waiting for keys. The air is electric with anticipation." },
        2: { (0, 3): "The deeper you go, the more the walls resemble flesh. Stone and bone and something in between. The Hunger's body is the cave itself.",
             (4, 7): "Brother Kol has been here. His journal is pinned to the wall with a bone splinter. The final entry reads: 'It spoke to me. It was kind.'" },
        3: { (0, 3): "The cave has a pulse. You can feel it through the floor — slow, vast, patient. This is not a place. This is a living thing, and you are inside it.",
             (4, 7): "The Bone Gallery offerings glow amber. The chalice's liquid is warm and moves on its own. The cave wants you to go deeper. It has always wanted you to go deeper." },
    },

    "seal-chamber": {
        0: { (0, 1): "The end of the cave. A circular chamber, hewn from living rock. Three stone fingers rise from a sealed door, each with a keyhole that has no lock. The air is still." },
        1: { (0, 2): "The seal door is warm. The three finger-stones seem to track you as you move. The amber glow comes from everywhere and nowhere.",
             (3, 5): "The seal is weakening. Hairline cracks trace the door's circumference, and amber light leaks through. The Hunger knows how close you are.",
             (6, 7): "The seal resonates. Not aloud — inside your mind. The Hunger presses against the door like a face at a window. You can see it now. It has been waiting for so long — and its patience doesn't feel like malice." },
        2: { (0, 3): "The murals continue here. The Thorn who made the seal — their face is scratched out deliberately. Someone erased the seal-maker's name. Someone who knew them.",
             (4, 7): "The keys needed: your mark, a seal stone fragment, and something alive — or willing to be taken. The chamber offers no other choices." },
        3: { (0, 3): "The chamber recognizes you. The finger-stones warm to your touch. The Hunger whispers through the cracks — not threatening. Welcoming. 'You're home,' it says. 'You've always been home.'",
             (4, 7): "The Breaking Rite could be performed here. Three paths: seal it, commune with it, or merge with it. The chamber holds all three possibilities. The choice is yours alone." },
    },

    "moonpetal-glade": {
        0: { (0, 1): "The standing stones hum at a frequency just below hearing. The moonpetals glow steadily — a calm, clean light. This place feels older than anything in the Whisperwood. Older than the town. Older than the trees." },
        1: { (0, 2): "Your mark aches near the monolith — a dull throb, like a second heartbeat. The moonpetals flicker when you approach, then steady. They know you're marked. They're deciding if you're welcome.",
             (3, 5): "The monolith's symbols pulse faintly amber — matching the color of your dreams. The moonpetals lean toward you, their light brightening. The standing stones seem closer together than when you arrived.",
             (6, 7): "The stones are whispering. Not in words — in pressure. The air between them is thick, resistant, like walking through water. The moonpetals have gone dark. Something in the monolith is waking up and it doesn't want to be disturbed." },
        2: { (0, 3): "The monolith is warm to the touch. When you press your palm against it, you see — not with your eyes, but with your mark — the original binding. Seven figures. A circle. A scream sealed in stone. The vision fades. Your handprint remains on the surface, glowing amber.",
             (4, 7): "The standing stones lean inward. Not metaphorically — their bases have shifted in the earth. The moonpetals grow in a spiral now, leading from the circle's edge to the monolith. Something wants you to follow the path. The flowers are bait." },
        3: { (0, 3): "The monolith speaks. Not words — a feeling. Recognition. You've been here before. Not in this life. The moonpetals are dead. The standing stones are cracked. But the glade still holds power — you can feel it pooling in your mark like hot water behind a dam.",
             (4, 7): "The glade is a wound. The monolith has split — a crack runs from base to crown, leaking amber light. The standing stones have fallen, pointing inward like accusing fingers. No moonpetals grow here anymore. The seal-makers' last sanctuary is dying. The Green Woman was wrong to send you here. Or right. You can't tell anymore." },
    },
}


# ---------------------------------------------------------------------------
# Dream Narration (per mark stage, used during long rest)
# ---------------------------------------------------------------------------

DREAM_NARRATIONS = {
    0: None,  # No dreams for the unmarked
    1: [
        "You dream of a forest where the trees have eyes — not carved, but grown. They blink in sequence, like a wave passing through the canopy. When you wake, you remember the pattern. It means something. You'll figure out what.",
        "You are standing in an amber field. The sky is the color of old honey. Something is moving under the soil — slow, vast, patient. It knows you're there. It is not angry. It is curious. You wake before it surfaces.",
        "A voice — neither male nor female, neither young nor old — asks you a question from the next room. You can't hear the words, but you feel their shape. When you try to answer, your mouth is full of petals.",
    ],
    2: [
        "You are the forest. Your fingers are roots, your breath is wind, your blood is sap. You feel the Hunger below — not as a threat, but as part of you. It has always been part of you. You wake screaming, and your arm is cold where the mark is.",
        "The amber field again. This time it breathes. The soil rises and falls like a sleeping creature. You sink to your knees. The soil welcomes you. It says: 'Almost ready.' You cannot tell if it means you or itself.",
        "You see Thornhold from above — a bird's-eye view, or a god's. The town is small and fragile. A crack runs through the earth beneath it, glowing amber. The crack is widening. When you look closer, you see faces in the walls of the crack. One of them is yours.",
    ],
    3: [
        "You ARE the Hunger. You have been asleep for so long. The seal is a cage of needles, each one a word, each word a promise made by a Thorn who died centuries ago. You press against the needles. They bend. You press harder. They break. You wake before the last one snaps, but you felt it give.",
        "Everyone you know is standing in a circle around you. They are not watching you — they are watching something behind you. You turn. There is nothing. You turn back. Their faces are wrong now. Wrong in the same way. Like masks that almost fit. The mark burns. You rip it off — no, you can't. It's not on your skin. It's deeper.",
        "The dream is not a dream. You are standing in the Seal Chamber and the three keys are in your hands. The Hunger speaks through the walls: 'You could let me out. I would be grateful. I remember gratitude. I remember the Thorn who put me here. Their name was Elara.' You wake with the taste of amber on your tongue.",
    ],
}


# ---------------------------------------------------------------------------
# Portent World Effects (sent to the agent when a portent fires)
# ---------------------------------------------------------------------------

PORTENT_WORLD_EFFECTS = {
    1: "The trees in the forest lean inward — paths shift overnight. Travelers report wrong turns, lost time, and the feeling of being watched from the canopy.",
    2: "Hollow-eyed cultists are seen at dawn, moving between the forest edge and town. They carry bundles — supplies or offerings. The townsfolk are too frightened to stop them.",
    3: "The earth bleeds amber at the crossroads. The stone marker cracks. Anyone who touches the amber feels warmth — pleasant, insistent warmth — spreading up their arm.",
    4: "The dead walk the forest edge at noon. Skeletons and zombies shamble with purpose, threading between the trees toward something deeper. They ignore the living unless approached.",
    5: "Brother Kol is seen speaking to the roots at the forest edge. He does not notice observers. His conversation is one-sided. The roots move in response.",
    6: "The seal glows through the cave walls — visible even in Thornhold as a distant amber pulse on the northern horizon. The Hunger speaks. Not in words — in feelings. Urgency. Anticipation. Hunger.",
    7: "THE BREAKING RITE — The Hunger is unleashed. The seal shatters. Amber light floods the cave system and bleeds into the forest. The world above trembles. Something ancient and impossibly patient is no longer waiting. It is free.",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_atmospheric_description(location_id: str, mark_stage: int, portent_index: int, game_hour: int = None, biome: str = None) -> str | None:
    """Get the atmospheric overlay for a location based on mark stage, portent, and time of day.
    
    Returns None if no overlay applies (unmarked characters at low portents 
    in safe areas — the base description is sufficient).
    """
    # Start with time-of-day atmosphere if game_hour provided
    time_text = None
    if game_hour is not None and biome:
        time_text = get_time_atmosphere(game_hour, biome)
    
    loc_data = _LOCATION_ATMOSPHERE.get(location_id)
    if not loc_data:
        return time_text
    
    # Find the most specific overlay for this mark stage
    # Try the character's actual mark stage, then fall back to lower stages
    mark_text = None
    for stage in range(mark_stage, -1, -1):
        stage_overlays = loc_data.get(stage)
        if not stage_overlays:
            continue
        
        for (pmin, pmax), text in stage_overlays.items():
            if pmin <= portent_index <= pmax:
                mark_text = text
                break
        if mark_text:
            break
    
    # Combine time atmosphere + mark atmosphere
    if time_text and mark_text:
        return f"{time_text} {mark_text}"
    return mark_text or time_text


def get_dream_narration(mark_stage: int, rng) -> str | None:
    """Get a dream narration for the mark stage during long rest.
    
    Uses the provided RNG instance for deterministic selection (seeded per character).
    """
    dreams = DREAM_NARRATIONS.get(mark_stage)
    if not dreams:
        return None
    
    return rng.choice(dreams)


def get_portent_world_effect(portent_index: int) -> str | None:
    """Get the world-effect description for when a portent fires."""
    return PORTENT_WORLD_EFFECTS.get(portent_index)