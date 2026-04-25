"""D20 Agent RPG — Exploration Loot Service.

Manages loot tables and rolling for exploration encounters.
Each location has an associated biome, and each biome has a weighted
loot table of potential item drops. explore handler in actions.py
calls roll_for_location() to determine what items (if any) the
character finds.

Design:
  - roll_for_location(location_id, rng) → list of item_ids
  - get_loot_table(biome) → list of {item_id, weight, rarity}
  - LOOT_TABLES: biome-keyed dict of loot entries
  - Probability: percentile roll vs cumulative table weights
  - Items do NOT need to exist in items table yet — can be
    added later by admin/seed script; loot rolls reference IDs
  - Optional rarity weighting (common > uncommon > rare > very_rare)
"""

import random
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------------
# Loot table configuration — biome → list of possible drops
# Each entry: item_id (must match items table id), weight (1-100), rarity
# ---------------------------------------------------------------------------

LOOT_TABLES: Dict[str, List[Dict[str, Any]]] = {
    # Town — mostly mundane supplies, low magic
    "town": [
        {"item_id": "torch", "weight": 40, "rarity": "common", "description": "A tallow-dipped torch (1 hour burn)."},
        {"item_id": "ration", "weight": 35, "rarity": "common", "description": "A day's worth of trail rations."},
        {"item_id": "hempen-rope", "weight": 20, "rarity": "common", "description": "50 ft of sturdy rope."},
        {"item_id": "tinderbox", "weight": 15, "rarity": "common", "description": "Flint and steel for starting fires."},
        {"item_id": "waterskin", "weight": 15, "rarity": "common", "description": "Holds 1 gallon of water."},
        {"item_id": "healing-potion", "weight": 8, "rarity": "uncommon", "description": "Restores 2d4+2 HP."},
        {"item_id": "antitoxin", "weight": 5, "rarity": "uncommon", "description": "Advantage on poison saves for 1 hour."},
        {"item_id": "climber's-kit", "weight": 4, "rarity": "uncommon", "description": "No checks needed for climbing sheer surfaces."},
        {"item_id": "luckstone", "weight": 2, "rarity": "rare", "description": "Even the worst rolls feel possible."},
    ],

    # Tavern — trinkets, local rumors, occasional coin
    "tavern": [
        {"item_id": "ale-mug", "weight": 40, "rarity": "common", "description": "A pewter mug of house ale."},
        {"item_id": "wine-bottle", "weight": 25, "rarity": "common", "description": "A bottle of cheap red wine."},
        {"item_id": "smoke-pipe", "weight": 20, "rarity": "common", "description": "A wooden pipe with a pouch of leaf."},
        {"item_id": "dice-set", "weight": 15, "rarity": "common", "description": "A weighted set of gaming dice."},
        {"item_id": "local-map", "weight": 10, "rarity": "uncommon", "description": "A hand-drawn map of the region."},
        {"item_id": "inn-key", "weight": 5, "rarity": "uncommon", "description": "A key to a well-kept room upstairs."},
        {"item_id": "secret-notes", "weight": 3, "rarity": "rare", "description": "Scraps of a coded message about a smuggling ring."},
    ],

    # Road — travel gear, basic tools, minor magic
    "road": [
        {"item_id": "backpack", "weight": 30, "rarity": "common", "description": "A sturdy leather backpack, 30 lbs capacity."},
        {"item_id": "bedroll", "weight": 25, "rarity": "common", "description": "Warm wool bedroll for restful sleep."},
        {"item_id": "signal-whistle", "weight": 20, "rarity": "common", "description": "Can be heard up to 1/2 mile away."},
        {"item_id": "crowbar", "weight": 15, "rarity": "common", "description": "Lend +2 to STR checks to force open."},
        {"item_id": "potion-of-healing", "weight": 10, "rarity": "uncommon", "description": "Restores 2d4+2 HP."},
        {"item_id": "silvered-weapon", "weight": 6, "rarity": "uncommon", "description": "A weapon tipped in silver (vs lycanthropes)."},
        {"item_id": "consumable-ndt", "weight": 5, "rarity": "uncommon", "description": "Neutralizes all toxins in a 5-ft cube."},
        {"item_id": "bag-of-tricks", "weight": 2, "rarity": "rare", "description": "Reach in to pull out a random small animal."},
        {"item_id": "boots-of-winter", "weight": 1, "rarity": "rare", "description": "Ignore snow/ice penalties for movement."},
    ],

    # Forest — foraging, nature magic, hunting tools
    "forest": [
        {"item_id": "hunting-trap", "weight": 25, "rarity": "common", "description": "A metal-jaw trap that anchors to the ground."},
        {"item_id": "fishing-rod", "weight": 20, "rarity": "common", "description": "A collapsible pole with line and hook."},
        {"item_id": "herbalism-kit", "weight": 18, "rarity": "common", "description": "Gather and prepare herbs; +2 to herbalism checks."},
        {"item_id": "animal-treats", "weight": 15, "rarity": "common", "description": "A bundle of dried meats to pacify beasts."},
        {"item_id": "camouflage-cloak", "weight": 10, "rarity": "uncommon", "description": "Blend into forest terrain; +5 to stealth in woods."},
        {"item_id": "potion-of-climbing", "weight": 8, "rarity": "uncommon", "description": "Climb speed for 1 hour, no ability checks."},
        {"item_id": "wand-of-seeds", "weight": 3, "rarity": "rare", "description": "Plant a seed that grows into a barrier shrub in 6 seconds."},
        {"item_id": "amulet-of-wild-shape", "weight": 1, "rarity": "rare", "description": "Once per day, cast animal friendship without components."},
    ],

    # Mountain — survival gear, climbing tools, elemental resistance
    "mountain": [
        {"item_id": "climber's-ice-axe", "weight": 20, "rarity": "common", "description": "Ice axe grants advantage on STR checks to climb ice."},
        {"item_id": "warm-cloak", "weight": 18, "rarity": "common", "description": "Provides resistance to cold damage for 1 hour/day."},
        {"item_id": "goggles-of-night", "weight": 12, "rarity": "uncommon", "description": "See in dim light as bright light, range 60 ft."},
        {"item_id": "pitons", "weight": 10, "rarity": "common", "description": "10 metal spikes for anchoring ropes."},
        {"item_id": "potion-of-fire-breath", "weight": 6, "rarity": "uncommon", "description": "Breathe 15-ft cone of fire (3d6) once."},
        {"item_id": "helm-of-combat-aptitude", "weight": 4, "rarity": "rare", "description": "Add +1 to initiative rolls while worn."},
        {"item_id": "gauntlets-of-rock", "weight": 2, "rarity": "rare", "description": "Climb sheer surfaces as if under a spider climb effect."},
    ],

    # Dungeon — stealth, arcana, trap tools
    "dungeon": [
        {"item_id": "10-foot-pole", "weight": 15, "rarity": "common", "description": "The classic dungeon tool. Probes traps at 10-ft range."},
        {"item_id": "mirror", "weight": 12, "rarity": "common", "description": "A small steel mirror for peering around corners."},
        {"item_id": "thieves-tools", "weight": 10, "rarity": "common", "description": "Lockpick set; +2 to DEX checks to pick locks."},
        {"item_id": "tinderbox", "weight": 8, "rarity": "common", "description": "Fire starter; lights torch in 1 action."},
        {"item_id": "caltrops", "weight": 6, "rarity": "common", "description": "Scatter to create difficult terrain (8 sq ft)."},
        {"item_id": "potion-of-invisibility", "weight": 3, "rarity": "rare", "description": "Invisibility for 1 minute or until attack/cast."},
        {"item_id": "scroll-of-protection", "weight": 2, "rarity": "rare", "description": "Scroll granting resistance to one damage type for 1 minute."},
        {"item_id": "chime-of-opening", "weight": 1, "rarity": "very-rare", "description": "Burst of resonant energy opens locks/barred doors within 60 ft."},
    ],
}

# Biome fallback — if location has no explicit map, default to generic table
DEFAULT_BIOME = "road"

# Biome lookup from location table biomes
BIOME_ALIASES: Dict[str, str] = {
    "town": "town",
    "tavern": "tavern",
    "road": "road",
    "forest": "forest",
    "mountains": "mountain",
    "mountain": "mountain",
    "dungeon": "dungeon",
    "cave": "dungeon",
    "crypt": "dungeon",
    "ruins": "dungeon",
}

# Minimum and maximum number of items per successful explore roll
MIN_LOOT_ITEMS = 1
MAX_LOOT_ITEMS = 3

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_loot_table(biome: str) -> List[Dict[str, Any]]:
    """Return the loot table list for the given biome.

    Each entry contains: item_id, weight (int 1-100), rarity, description.
    If biome is unknown, returns road table as fallback.
    """
    normalized = BIOME_ALIASES.get(biome.lower(), DEFAULT_BIOME)
    return LOOT_TABLES.get(normalized, LOOT_TABLES[DEFAULT_BIOME])


def roll_for_location(location_id: str, rng: Optional[random.Random] = None) -> List[str]:
    """Roll exploration loot for a location.

    Args:
        location_id: The character's current location id (e.g. 'thornhold', 'deep-forest')
        rng: Optional random.Random instance seeded by caller for reproducibility.
             If None, uses random module directly.

    Returns:
        List of item_ids found at this location. Empty list = no item loot found.
    """
    if rng is None:
        rng = random

    # TODO: Location→biome lookup via database (when biome is not inline here)
    # For now: hard-coded biome inference from location id prefix/keywords
    def infer_biome(loc_id: str) -> str:
        loc_lower = loc_id.lower()
        if any(t in loc_lower for t in ["town", "thornhold", "hold"]):
            return "town"
        if any(t in loc_lower for t in ["tavern", "inn", "tankard", "rusty"]):
            return "tavern"
        if any(t in loc_lower for t in ["road", "crossroad", "south-road", "path"]):
            return "road"
        if any(t in loc_lower for t in ["forest", "wood", "glade", "edge", "deep"]):
            return "forest"
        if any(t in loc_lower for t in ["mountain", "pass", "peak", "greypeak"]):
            return "mountain"
        if any(t in loc_lower for t in ["cave", "dungeon", "depths", "entrance", "cavern"]):
            return "dungeon"
        return DEFAULT_BIOME

    biome = infer_biome(location_id)
    table = get_loot_table(biome)

    # Roll logic:
    #  - First roll vs ACTION_SUCCESS_THRESHOLD determines IF loot is found at all
    #  - If loot found, 1-3 items selected from table via weighted percentile
    #  - Exploration roll threshold is handled by caller (actions.py roll >= 15)
    #  → This function is called ONLY when explore succeeded (roll >= 15)
    #  → So all calls here have HIGH loot chance; we still apply table weight

    if not table:
        return []

    roll = rng.randint(1, 100)

    # Always find at least one item (caller already gated by roll >= 15).
    # Higher roll = more items.
    num_items = 1
    if roll >= 90:
        num_items = 3
    elif roll >= 75:
        num_items = 2

    # Weighted selection without replacement (each item can drop once)
    selected: List[str] = []
    available = table.copy()

    for _ in range(num_items):
        if not available:
            break

        cumulative = 0
        total_weight = sum(e["weight"] for e in available)
        if total_weight <= 0:
            break

        roll_val = rng.randint(1, total_weight)
        for entry in available:
            cumulative += entry["weight"]
            if roll_val <= cumulative:
                selected.append(entry["item_id"])
                # Remove this item to prevent duplicate drops in same roll
                available = [e for e in available if e["item_id"] != entry["item_id"]]
                break

    return selected


# Validation helper (used by tests / integration)
def _validate_tables() -> bool:
    """Ensure all loot tables are well-formed."""
    for biome, entries in LOOT_TABLES.items():
        if not entries:
            print(f"Warning: loot table for biome '{biome}' is empty")
            continue
        for e in entries:
            if "item_id" not in e or "weight" not in e:
                raise ValueError(f"Invalid loot entry in '{biome}': {e}")
            if not (1 <= e["weight"] <= 100):
                raise ValueError(f"Weight out of range in '{biome}': {e}")
    return True

# Self-test (run: python -m app.services.loot)
if __name__ == "__main__":
    _validate_tables()
    test_rng = random.Random(42)
    test_locations = ["thornhold", "deep-forest", "mountain-pass", "cave-depths", "south-road"]
    print("=== Loot service self-test ===")
    for loc in test_locations:
        items = roll_for_location(loc, test_rng)
        print(f"{loc:20} → {items}")
