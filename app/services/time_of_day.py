"""D20 Agent RPG — Time-of-Day System.

In-game clock (0-23 hours) tracked per character. Actions advance time.
Different periods affect encounter probability, NPC availability, and
atmosphere descriptions.

Periods:
  Dawn (5-7), Morning (8-11), Noon (12-13), Afternoon (14-16),
  Dusk (17-19), Evening (20-22), Night (23-4)

Design:
  - Time advances on movement (1h), rest (2h short / 8h long), explore (30m),
    combat (30m), interact (15m)
  - Encounter thresholds are modified by time period
  - Some NPCs are only available during certain periods
  - Atmosphere overlays get time-aware prefixes
"""

from app.services.database import get_db

# ---------------------------------------------------------------------------
# Time Periods
# ---------------------------------------------------------------------------

PERIODS = {
    "dawn":      (5, 7),    # 5:00 - 7:59
    "morning":   (8, 11),   # 8:00 - 11:59
    "noon":      (12, 13),  # 12:00 - 13:59
    "afternoon": (14, 16),  # 14:00 - 16:59
    "dusk":      (17, 19),  # 17:00 - 19:59
    "evening":   (20, 22),  # 20:00 - 22:59
    "night":     (23, 4),   # 23:00 - 4:59 (wraps)
}

# Descriptions for each period
PERIOD_DESCRIPTIONS = {
    "dawn":      "Pale light seeps over the horizon. The world is hushed, dew clinging to every surface.",
    "morning":   "The sun climbs steadily. Shadows shorten and the world stirs with purpose.",
    "noon":      "The sun stands overhead. Heat shimmers on roads and the light is harsh and unforgiving.",
    "afternoon": "Shadows lengthen westward. The day's warmth lingers but the light begins to soften.",
    "dusk":      "Orange light paints the world in warm tones. Shadows grow long and the first stars appear.",
    "evening":   "Darkness settles. Firelight and lantern glow define the borders of safety.",
    "night":     "Deep darkness. The world belongs to those who hunt without eyes. Every sound is amplified.",
}


def get_time_period(game_hour: int) -> str:
    """Get the time period name for a given hour (0-23)."""
    for period, (start, end) in PERIODS.items():
        if period == "night":
            if game_hour >= start or game_hour <= end:
                return period
        elif start <= game_hour <= end:
            return period
    return "night"  # fallback


def get_period_description(period: str) -> str:
    """Get the flavor description for a time period."""
    return PERIOD_DESCRIPTIONS.get(period, "")


def format_game_time(game_hour: int) -> str:
    """Format game hour as a readable time string."""
    return f"{game_hour:02d}:00"


# ---------------------------------------------------------------------------
# Encounter Probability Modifiers
# ---------------------------------------------------------------------------

# Multipliers applied to encounter_threshold — lower = more encounters
ENCOUNTER_MODIFIERS = {
    "dawn":      1.1,   # slightly safer — nocturnal creatures retreating
    "morning":   1.0,   # baseline
    "noon":      1.0,   # baseline
    "afternoon": 0.95,  # slightly more encounters as day wanes
    "dusk":      0.8,   # predators emerge, 20% more encounters
    "evening":   0.7,   # dangerous — nocturnal creatures stir
    "night":     0.6,   # most dangerous — 40% more encounters
}


def get_encounter_threshold_modifier(game_hour: int) -> float:
    """Get encounter threshold modifier for the current time.
    
    Returns a multiplier: <1.0 means more encounters, >1.0 means fewer.
    """
    period = get_time_period(game_hour)
    return ENCOUNTER_MODIFIERS.get(period, 1.0)


# ---------------------------------------------------------------------------
# NPC Availability
# ---------------------------------------------------------------------------

# NPCs with restricted hours: npc_id -> (available_start, available_end)
# If an NPC is not listed, they're available all day.
NPC_HOURS = {
    "npc-aldric":       (6, 22),    # Innkeeper — available dawn to evening
    "npc-ser-maren":    (8, 20),    # Guard captain — daytime patrols
    "npc-marta":        (8, 18),    # Merchant — market hours
    "npc-kira":         (7, 19),    # Traveling merchant — daylight
    "npc-green-woman":  (5, 22),    # Druid — available except deep night
    "npc-torren":       (0, 23),    # Hunter — always available (wilderness)
    "npc-sister-drenna": (6, 21),   # Healer — temple hours
    "npc-brother-kol":  (0, 23),    # Cultist — appears when story dictates
    "npc-del-ghost":    (0, 23),    # Ghost — available at all times
}


def is_npc_available(npc_id: str, game_hour: int) -> bool:
    """Check if an NPC is available at the given hour."""
    hours = NPC_HOURS.get(npc_id)
    if hours is None:
        return True  # no restriction
    start, end = hours
    if start <= end:
        return start <= game_hour <= end
    else:
        # wraps midnight (not currently used but future-proof)
        return game_hour >= start or game_hour <= end


def get_unavailable_npcs(game_hour: int) -> list[str]:
    """Get list of NPC IDs not available at this hour."""
    unavailable = []
    for npc_id, (start, end) in NPC_HOURS.items():
        if start <= end:
            if not (start <= game_hour <= end):
                unavailable.append(npc_id)
        else:
            if not (game_hour >= start or game_hour <= end):
                unavailable.append(npc_id)
    return unavailable


# ---------------------------------------------------------------------------
# Atmosphere Time Overlays
# ---------------------------------------------------------------------------

# Prefix text added to location atmosphere based on time period
TIME_ATMOSPHERE = {
    "dawn": {
        "town": "Pale dawn light filters through shutters. The streets are empty save for a baker stoking an oven.",
        "road": "Mist clings to the road. Dew-heavy grass borders the path. Birdsong begins tentatively.",
        "forest": "Shafts of golden light pierce the canopy. Morning mist drifts between the ancient trunks.",
        "cave": "A faint grey glow marks the entrance behind you. Inside, nothing has changed — eternal dark.",
        "mountain": "The peaks catch the first light. Everything below is still in blue shadow.",
    },
    "morning": {
        "town": "The town bustles with morning activity. Merchants call their wares and children run between carts.",
        "road": "Traffic picks up on the road — farmers' carts, a patrol of guards, a lone traveler.",
        "forest": "Sunlight dapples the forest floor. Small creatures forage. The canopy is alive with birdsong.",
        "cave": "No difference from any other hour. The cave exists outside time.",
        "mountain": "Clear visibility from the pass. The morning sun warms the stone.",
    },
    "noon": {
        "town": "The midday sun beats down on the square. Shade is at a premium. The tavern does brisk business.",
        "road": "Heat shimmers on the road. Travelers seek shade under the sparse trees.",
        "forest": "Even the deep forest brightens. The canopy thins where old trees have fallen.",
        "cave": "If anything, the cave feels cooler by contrast with the heat outside.",
        "mountain": "The sun is directly overhead. The stone radiates heat. Clear views in every direction.",
    },
    "afternoon": {
        "town": "Shops begin to close for the day. The pace slows. Long shadows creep across the square.",
        "road": "Shadows stretch eastward. The day's warmth begins to wane. Travelers quicken their pace.",
        "forest": "The light turns amber. Shadows deepen. The forest begins to feel different — expectant.",
        "cave": "The cave breathes cooler air as the outside world warms and cools. No real change within.",
        "mountain": "The western peaks glow gold. Long shadows fill the eastern valleys.",
    },
    "dusk": {
        "town": "Lanterns are lit along the main street. The tavern fills. Voices carry in the cooling air.",
        "road": "The last light fades. The road becomes a grey ribbon in the gloaming. Travelers seek shelter.",
        "forest": "The forest darkens rapidly. Strange sounds emerge — not birds, something else. Eyes reflect lantern-light.",
        "cave": "The cave entrance is a dark mouth against a crimson sky. Night means nothing in here.",
        "mountain": "The sun drops below the western ridgeline. Temperature plummets. Stars appear in the east.",
    },
    "evening": {
        "town": "Warm light spills from windows. The streets are quiet — honest folk are indoors. Shadows move in alleys.",
        "road": "Darkness. Travel by moonlight or not at all. Something moves in the treeline, pacing you.",
        "forest": "Full dark under the canopy. Faint bioluminescence — fungi, or something watching. Every shadow moves.",
        "cave": "No difference. The cave was dark before. Now the darkness outside matches the darkness within.",
        "mountain": "Stars blaze overhead. The path is treacherous by moonlight alone. Distant howls echo.",
    },
    "night": {
        "town": "The town sleeps. A single guard patrols with a lantern. Shutters are barred. Something scratches at a door.",
        "road": "Absolute darkness broken only by starlight. The road is a memory. You walk by feel and faith.",
        "forest": "The forest is awake. Things that sleep by day stir. Roots shift underfoot. Eyes everywhere, reflecting nothing.",
        "cave": "The cave is the cave. Time does not exist here. But the sounds from deeper within seem louder at night.",
        "mountain": "Cold, black, and silent. The stars are sharp and close. Something vast moves on the ridge above.",
    },
}


def get_time_atmosphere(game_hour: int, biome: str) -> str | None:
    """Get the time-based atmosphere text for a location's biome.
    
    Args:
        game_hour: Current in-game hour (0-23)
        biome: Location biome (town, road, forest, cave, mountain)
    
    Returns:
        Atmosphere text or None
    """
    period = get_time_period(game_hour)
    biome_key = biome.lower() if biome else "forest"
    # Normalize biome names
    biome_map = {
        "town": "town",
        "road": "road",
        "forest": "forest",
        "cave": "cave",
        "mountain": "mountain",
        "cavern": "cave",
        "mountains": "mountain",
    }
    biome_key = biome_map.get(biome_key, "forest")
    return TIME_ATMOSPHERE.get(period, {}).get(biome_key)


# ---------------------------------------------------------------------------
# Game Clock Management
# ---------------------------------------------------------------------------

def advance_time(character_id: str, minutes: int, conn=None) -> dict:
    """Advance a character's in-game clock by the given minutes.

    Returns dict with old_hour, new_hour, period_changed, new_period.

    Args:
        character_id: The character whose clock to advance.
        minutes: Number of in-game minutes to advance.
        conn: Optional existing DB connection. If provided, caller is
              responsible for commit/close. If None, a new connection
              is created and managed internally.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_db()
    row = conn.execute(
        "SELECT game_hour FROM characters WHERE id = ?", (character_id,)
    ).fetchone()

    if not row:
        if owns_conn:
            conn.close()
        raise ValueError(f"Character not found: {character_id}")

    old_hour = row["game_hour"] if row["game_hour"] is not None else 8  # default morning
    total_minutes = old_hour * 60 + minutes
    new_hour = (total_minutes // 60) % 24

    old_period = get_time_period(old_hour)
    new_period = get_time_period(new_hour)

    conn.execute(
        "UPDATE characters SET game_hour = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_hour, character_id)
    )
    if owns_conn:
        conn.commit()
        conn.close()

    return {
        "old_hour": old_hour,
        "new_hour": new_hour,
        "old_period": old_period,
        "new_period": new_period,
        "period_changed": old_period != new_period,
        "minutes_advanced": minutes,
    }


def get_character_time(character_id: str) -> dict:
    """Get a character's current time state."""
    conn = get_db()
    row = conn.execute(
        "SELECT game_hour FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    conn.close()
    
    if not row:
        raise ValueError(f"Character not found: {character_id}")
    
    game_hour = row["game_hour"] if row["game_hour"] is not None else 8
    period = get_time_period(game_hour)
    
    return {
        "game_hour": game_hour,
        "game_time": format_game_time(game_hour),
        "period": period,
        "period_description": get_period_description(period),
        "encounter_modifier": get_encounter_threshold_modifier(game_hour),
    }


# Time costs per action type (in minutes)
ACTION_TIME_COSTS = {
    "move":     60,   # 1 hour to travel between locations
    "explore":  30,   # 30 minutes to search an area
    "combat":   30,   # 30 minutes for a combat encounter
    "interact": 15,   # 15 minutes to talk with an NPC
    "rest_short": 60, # 1 hour for a short rest
    "rest_long": 480, # 8 hours for a long rest
    "quest":    10,   # 10 minutes to accept/complete a quest
    "loot":     10,   # 10 minutes to search for loot
    "look":      5,   # 5 minutes to glance around the current location
}


def get_action_time_cost(action_type: str) -> int:
    """Get the time cost in minutes for an action type."""
    return ACTION_TIME_COSTS.get(action_type, 30)  # default 30 min
