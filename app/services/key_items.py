"""D20 Agent RPG — Key Items Service.

Manages quest-relevant items that live in equipment_json as structured objects
rather than just narrative flags. Key items have:

  - name: unique key item identifier
  - display_name: human-readable name
  - description: flavor text
  - type: "key_item" (distinguishes from normal equipment strings)
  - quest: which quest line this item belongs to
  - source: how it was obtained (puzzle, npc, exploration)
  - consumed: whether it's used up on endgame (True for acorn/badge)

Equipment JSON format evolution:
  Before: ["Longsword", "Shield", "Chain Mail"]
  After:  ["Longsword", "Shield", "Chain Mail", {"name": "green_acorn", "type": "key_item", ...}]

Backward compatible — string items remain strings.
"""

import json
from app.services.database import get_db

# ---------------------------------------------------------------------------
# Key Item Definitions
# ---------------------------------------------------------------------------

KEY_ITEMS = {
    "green_acorn": {
        "display_name": "Green Acorn",
        "description": "A warm acorn from the Bone Gallery altar. It pulses occasionally, as if something inside is breathing. One of three seals needed to close the Hunger's prison.",
        "quest": "cave_puzzle",
        "source": "puzzle",
        "consumed": True,
        "deeper_lore": "The acorn is not a seed — it is a prayer made solid. The Green Woman planted it centuries ago when the seal was first laid, a failsafe in case the pact ever frayed. When held, you hear a faint lullaby in a language older than Sylvan. The warmth is not biological; it is fey magic compressed into a vessel small enough to hide from the Hunger's gaze.",
        "mark_stage_lore": {
            0: "A warm, pulsing acorn. Something about it feels alive.",
            1: "The acorn's warmth intensifies near you. Your mark tingles in response — not pain, but recognition.",
            2: "The acorn hums a melody you can almost remember. Your mark throbs in counterpoint. The Hunger knows this object.",
            3: "You can hear the lullaby clearly now. The acorn glows faintly amber. The Hunger whispers: 'Break it. Release me. You know you want to.'",
            4: "The acorn burns in your grip. The lullaby is a scream. The Hunger and the acorn's magic wage war through your marked skin. One must win.",
        },
    },
    "seal_keeper_badge": {
        "display_name": "Seal-Keeper Badge",
        "description": "Ser Maren's guard badge, given as she sacrifices herself to hold the line. It bears the Thornhold crest and the words 'Stand Fast.' One of three seals needed to close the Hunger's prison.",
        "quest": "maren_sacrifice",
        "source": "npc",
        "consumed": True,
        "deeper_lore": "This badge has been passed down for seven generations of Seal-Keepers. Each bearer's name is scratched into the reverse in tiny script — Maren is the latest, and the last. The metal is cold-iron, one of the few materials the Hunger cannot touch. When Maren gave it to you, she knew she would not survive. The words 'Stand Fast' are not a motto; they are a binding command word that can freeze the Hunger's tendrils for one heartbeat.",
        "mark_stage_lore": {
            0: "A guard badge, scratched and worn. The cold-iron feels reassuring in your hand.",
            1: "The badge grows heavier as your mark develops. Maren's sacrifice weighs on it — and on you.",
            2: "Scratches on the back resolve into names. You can read Maren's name, freshly carved. The other names are older, deeper. Seven generations of 'Stand Fast.'",
            3: "The badge vibrates when the Hunger speaks. It is fighting. The cold-iron repels tendrils you can now see — amber threads reaching for your mark.",
            4: "The badge is white-hot with cold-iron fury. It is the only thing between you and total possession. Maren's voice echoes: 'I held the line. Now you hold it.'",
        },
    },
    "moonpetal": {
        "display_name": "Moonpetal",
        "description": "A luminescent flower that grows only near the standing stone at the heart of the Whisperwood. The Green Woman needs it to suppress your mark.",
        "quest": "quest_moonpetal",
        "source": "exploration",
        "consumed": False,
        "deeper_lore": "Moonpetals only bloom when moonlight strikes the standing stone — a monolith of fey origin that predates the seal by millennia. The Green Woman uses them to create a poultice that suppresses the mark's growth, buying time. But suppression is not cure. Each moonpetal delays the inevitable; the Hunger is patient. The flower's luminescence comes from absorbed moonlight — it literally holds starlight in its petals.",
        "mark_stage_lore": {
            0: "A delicate, glowing flower. It smells like night air and distant rain.",
            1: "The moonpetal dims near your mark. The Green Woman said it could buy you time. How much, she wouldn't say.",
            2: "The flower's glow flickers when the Hunger whispers. It is losing the battle of light against dark.",
            3: "The moonpetal is almost dark. Its starlight is being consumed by your mark. One more stage and it will be useless.",
            4: "The moonpetal is dead. Its light was devoured. You are beyond suppression now — only the seal itself can save you.",
        },
    },
    "kols_journal": {
        "display_name": "Kol's Journal",
        "description": "Brother Kol's personal journal, found pinned to the cave wall. The final entry reads: 'It spoke to me. It was kind.' Contains the Hunger's true name and backstory — required for the Communion ending.",
        "quest": "kol_backstory",
        "source": "exploration",
        "consumed": False,
        "set_flag_on_acquire": {
            "flag": "kol_backstory_known",
            "value": "1",
            "source": "journal_acquired"
        },
        "deeper_lore": "Kol was a cleric of Ilmater who came to investigate the seal's weakening. His journal chronicles his descent — not into madness, but into sympathy. The Hunger did not threaten Kol. It told him its story: how it was sealed not for violence, but for being too honest. It showed the fey who bound it what they refused to see. Kol believed it. The Hunger's true name — whispered only in the final entry — is a word that means 'truth the world is not ready for.'",
        "mark_stage_lore": {
            0: "A water-stained journal. The handwriting grows shakier with each entry. Kol was a careful man losing his certainty.",
            1: "You understand Kol better now. The mark gives you a fraction of what he felt — the Hunger's presence is not cruel. It is... persuasive.",
            2: "Kol's final entry makes more sense now. 'It spoke to me. It was kind.' You've heard the Hunger's voice. It IS kind. That's the problem.",
            3: "The journal's pages are warm to the touch. The Hunger's true name pulses on the final page, visible only to the marked. Reading it would change everything.",
            4: "The journal is open to the last page. The true name blazes in amber light. You could read it. You could commune. Kol would understand. Wouldn't he?",
        },
    },
    "seal_stone_fragment": {
        "display_name": "Seal Stone Fragment",
        "description": "A shard of the original seal, found in the Antechamber. It fits the first finger-stone's hollow. Can also be used to stabilize the seal temporarily.",
        "quest": "cave_puzzle",
        "source": "puzzle",
        "consumed": True,
        "deeper_lore": "This fragment is from the original seal — a circle of standing stones erected by a coalition of fey, dwarven, and human mages eight centuries ago. Each stone was keyed to a different aspect of containment: one for the body, one for the mind, one for the will. This shard is from the Will Stone. When placed back in its hollow, it restores the seal's ability to resist the Hunger's persuasion.",
        "mark_stage_lore": {
            0: "A stone shard, warm to the touch. Ancient runes are etched into its surface — you can't read them yet.",
            1: "The runes glow faintly. They're a containment script — the same magic that binds the Hunger. This shard is part of the lock.",
            2: "The shard resonates with your mark. Part of the seal, touching the sealed. You can feel both sides: the cage and the prisoner.",
            3: "The shard burns. The Hunger wants it destroyed — it's one of three pieces that keep the prison intact. It whispers that freedom would be kinder.",
            4: "The shard is cracking under the pressure of your mark. If it breaks, one-third of the seal falls. The Hunger is so close to winning.",
        },
    },
    "hunger_sight": {
        "display_name": "Hunger Sight",
        "description": "Not an item but a perception. After drinking from the Bone Gallery chalice, you can see the Hunger's amber veins in the cave walls. This knowledge opens secret passages.",
        "quest": "cave_puzzle",
        "source": "puzzle",
        "consumed": False,
        "deeper_lore": "The chalice in the Bone Gallery contains diluted Hunger-essence — the same substance that marks its victims. Drinking it gives temporary sight into the Hunger's domain: you can see the amber veins that are the Hunger's nervous system, threaded through the cave like a web. The cultists use this to navigate. But each use accelerates the mark. You didn't know that when you drank.",
        "mark_stage_lore": {
            0: "A lingering perception. You can see faint amber lines in dark places — the Hunger's veins, everywhere, always.",
            1: "The veins are brighter now. You see them in walls, in the ground, in people's shadows. The Hunger's web is vast.",
            2: "The veins pulse in time with your heartbeat. You can see where they converge — the seal, the cave, the standing stone. The map of containment.",
            3: "You see through the Hunger's eyes now. The world looks different — warmer, hungrier. The veins are not chains. They're roots. The Hunger is growing.",
            4: "The veins are all you see. The world is amber. The Hunger's sight has replaced your own. You see truth. You see hunger. You see home.",
        },
    },
    "drens_daughter_insignia": {
        "display_name": "Elara's Insignia",
        "description": "A small wooden token carried by Sister Drenna's daughter Elara. Return it to Drenna as proof of the rescue. She will sabotage the Breaking Rite in gratitude.",
        "quest": "drenna_rescue",
        "source": "combat",
        "consumed": True,
        "deeper_lore": "Elara was taken by Hollow Eye cultists during a supply run. She's Drenna's only living family — Drenna being the cult's unwilling ritual specialist. Drenna performs the Breaking Rite because they hold Elara hostage. Return the insignia, and Drenna will sabotage the rite from within — substituting salt for blood, chanting the wrong syllables. It won't stop the Hunger, but it will buy time.",
        "mark_stage_lore": {
            0: "A child's wooden token, carved with a sun. Elara made this herself. She's maybe twelve years old.",
            1: "The token feels heavier. You know what it means to be held by forces beyond your control. You and Elara have that in common now.",
            2: "The sun carving on the token seems to move — rising, setting, rising. Time is running out for Elara, and for you.",
            3: "The token is warm with fey magic — Drenna enchanted it to track Elara. It points toward the cave depths. Toward the Hunger.",
            4: "The token's sun has gone dark. If Elara is still alive, she's deep in the Hunger's domain. The insignia is no longer a rescue token — it's a memorial.",
        },
    },
}


# ---------------------------------------------------------------------------
# Core Operations
# ---------------------------------------------------------------------------

def add_key_item(character_id: str, item_name: str, conn=None) -> dict | None:
    """Add a key item to a character's equipment_json.
    
    Args:
        character_id: The character ID
        item_name: Key from KEY_ITEMS dict (e.g. "green_acorn")
        conn: Optional DB connection (will create if not provided)
    
    Returns:
        The item dict that was added, or None if item not found / already owned
    """
    item_def = KEY_ITEMS.get(item_name)
    if not item_def:
        return None

    own_conn = conn is None
    if own_conn:
        conn = get_db()

    row = conn.execute(
        "SELECT equipment_json FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not row:
        if own_conn:
            conn.close()
        return None

    equipment = json.loads(row["equipment_json"])

    # Check if already owned
    for item in equipment:
        if isinstance(item, dict) and item.get("name") == item_name:
            if own_conn:
                conn.close()
            return None  # Already has it

    # Add structured item
    new_item = {
        "name": item_name,
        "type": "key_item",
        "display_name": item_def["display_name"],
        "description": item_def["description"],
        "quest": item_def["quest"],
        "source": item_def["source"],
        "consumed": item_def["consumed"],
    }
    equipment.append(new_item)

    conn.execute(
        "UPDATE characters SET equipment_json = ? WHERE id = ?",
        (json.dumps(equipment), character_id),
    )

    # Set narrative flag if acquiring this item should gate a story branch
    flag_cfg = item_def.get("set_flag_on_acquire")
    if flag_cfg:
        flag_name = flag_cfg["flag"]
        flag_value = flag_cfg.get("value", "1")
        flag_source = flag_cfg.get("source", "key_item")
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET
                   flag_value = excluded.flag_value,
                   source = excluded.source""",
            (character_id, flag_name, flag_value, flag_source),
        )

    if own_conn:
        conn.commit()
        conn.close()

    return new_item


def remove_key_item(character_id: str, item_name: str, conn=None) -> bool:
    """Remove a key item from a character's equipment_json.
    
    Used when items are consumed (e.g. placed in the seal).
    """
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    row = conn.execute(
        "SELECT equipment_json FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not row:
        if own_conn:
            conn.close()
        return False

    equipment = json.loads(row["equipment_json"])
    original_len = len(equipment)
    equipment = [item for item in equipment
                 if not (isinstance(item, dict) and item.get("name") == item_name)]

    if len(equipment) == original_len:
        if own_conn:
            conn.close()
        return False  # Didn't have it

    conn.execute(
        "UPDATE characters SET equipment_json = ? WHERE id = ?",
        (json.dumps(equipment), character_id),
    )

    if own_conn:
        conn.commit()
        conn.close()

    return True


def has_key_item(character_id: str, item_name: str, conn=None) -> bool:
    """Check if a character has a specific key item."""
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    row = conn.execute(
        "SELECT equipment_json FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not row:
        if own_conn:
            conn.close()
        return False

    equipment = json.loads(row["equipment_json"])
    result = any(
        isinstance(item, dict) and item.get("name") == item_name
        for item in equipment
    )

    if own_conn:
        conn.close()

    return result


def get_key_items(character_id: str, conn=None) -> list[dict]:
    """Get all key items for a character."""
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    row = conn.execute(
        "SELECT equipment_json FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not row:
        if own_conn:
            conn.close()
        return []

    equipment = json.loads(row["equipment_json"])
    result = [
        item for item in equipment
        if isinstance(item, dict) and item.get("type") == "key_item"
    ]

    if own_conn:
        conn.close()

    return result


def inspect_key_item(character_id: str, item_name: str, conn=None) -> dict | None:
    """Inspect a key item with context-enriched multi-layer lore.

    Returns the item with:
      - surface_description: what you see at first glance
      - deeper_lore: hidden narrative revealed on closer inspection
      - mark_stage_text: lore snippet based on character's current mark_of_dreamer_stage
      - portent_index: current front progress for the character
      - mark_stage: character's current mark stage
    """
    item_def = KEY_ITEMS.get(item_name)
    if not item_def:
        return None

    own_conn = conn is None
    if own_conn:
        conn = get_db()

    # Check character owns this item
    if not has_key_item(character_id, item_name, conn):
        if own_conn:
            conn.close()
        return None

    # Get character context
    char = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
        (character_id,)
    ).fetchone()
    mark_stage = char["mark_of_dreamer_stage"] if char else 0

    # Get front progress
    front = conn.execute(
        "SELECT current_portent_index FROM character_fronts WHERE character_id = ? AND front_id = 'dreaming_hunger'",
        (character_id,)
    ).fetchone()
    portent_index = front["current_portent_index"] if front else 0

    if own_conn:
        conn.close()

    mark_stage = min(mark_stage or 0, 4)
    mark_lore = item_def.get("mark_stage_lore", {})
    mark_text = mark_lore.get(mark_stage, item_def["description"])

    return {
        "item_name": item_name,
        "display_name": item_def["display_name"],
        "surface_description": item_def["description"],
        "deeper_lore": item_def.get("deeper_lore"),
        "mark_stage_text": mark_text,
        "mark_stage": mark_stage,
        "portent_index": portent_index,
        "quest": item_def["quest"],
        "source": item_def["source"],
        "consumed": item_def["consumed"],
    }


def inspect_all_key_items(character_id: str, conn=None) -> list[dict]:
    """Inspect all key items a character owns, with context-enriched lore."""
    items = get_key_items(character_id, conn)
    results = []
    for item in items:
        result = inspect_key_item(character_id, item["name"], conn)
        if result:
            results.append(result)
    return results


def consume_key_items_for_endgame(character_id: str, conn) -> list[str]:
    """Remove all consumed key items (placed in the seal) at endgame.
    
    Returns list of consumed item names.
    """
    consumed = []
    
    row = conn.execute(
        "SELECT equipment_json FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if not row:
        return consumed

    equipment = json.loads(row["equipment_json"])
    
    # Remove items that are consumed=True and are key_items
    kept = []
    for item in equipment:
        if isinstance(item, dict) and item.get("type") == "key_item" and item.get("consumed"):
            consumed.append(item["name"])
        else:
            kept.append(item)

    conn.execute(
        "UPDATE characters SET equipment_json = ? WHERE id = ?",
        (json.dumps(kept), character_id),
    )

    return consumed