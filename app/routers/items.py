"""D20 Agent RPG — Item Lore Viewer endpoints.

Provides item detail inspection with narrative lore text,
character inventory management, and key item discovery.
Part of the development sprint Task 4.1: Item Lore Viewer.
Task P2: Key item inspect endpoint with multi-layer lore.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from app.services.database import get_db
from app.services.key_items import inspect_key_item, inspect_all_key_items, KEY_ITEMS, get_key_items
from app.services.auth_helpers import get_auth, require_character_ownership

router = APIRouter(prefix="/items", tags=["items"])


def _item_to_response(row) -> dict:
    """Convert an items DB row to a response dict."""
    d = dict(row)
    return {
        "id": d["id"],
        "name": d["name"],
        "description": d["description"],
        "lore_text": d.get("lore_text"),
        "is_key_item": bool(d.get("is_key_item", 0)),
        "image_url": d.get("image_url"),
        "item_type": d.get("item_type", "misc"),
        "rarity": d.get("rarity", "common"),
        "created_at": d.get("created_at"),
    }


@router.get("/{item_id}")
def get_item(item_id: str):
    """Get item details including lore text.

    Returns the full item with narrative lore for immersion.
    Key items have is_key_item=true and contain quest-relevant lore.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, f"Item not found: {item_id}")

    return _item_to_response(row)


@router.get("")
def list_items(key_items_only: bool = False):
    """List all items, optionally filtering to key items only."""
    conn = get_db()
    if key_items_only:
        rows = conn.execute("SELECT * FROM items WHERE is_key_item = 1 ORDER BY name").fetchall()
    else:
        rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    conn.close()

    return {
        "items": [_item_to_response(r) for r in rows],
        "count": len(rows),
    }


# --- Character Inventory ---

@router.get("/inventory/{character_id}")
def get_character_inventory(character_id: str, auth: dict = Depends(get_auth)):
    """Get all items in a character's inventory.

    Returns items from the items table linked via character_items,
    with quantity and equipped status.
    """
    require_character_ownership(character_id, auth)
    conn = get_db()

    # Verify character exists
    char = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    rows = conn.execute(
        """SELECT i.*, ci.quantity, ci.is_equipped, ci.acquired_at as inventory_acquired
           FROM character_items ci
           JOIN items i ON ci.item_id = i.id
           WHERE ci.character_id = ?
           ORDER BY ci.is_equipped DESC, i.name""",
        (character_id,)
    ).fetchall()
    conn.close()

    inventory = []
    for r in rows:
        d = _item_to_response(r)
        d["quantity"] = r["quantity"]
        d["is_equipped"] = bool(r["is_equipped"])
        d["acquired_at"] = r["inventory_acquired"]
        inventory.append(d)

    return {
        "character_id": character_id,
        "items": inventory,
        "count": len(inventory),
    }


@router.post("/inventory/{character_id}/{item_id}")
def add_to_inventory(character_id: str, item_id: str, quantity: int = 1, equip: bool = False, auth: dict = Depends(get_auth)):
    """Add an item to a character's inventory.

    If the item is already in inventory, increments quantity.
    """
    require_character_ownership(character_id, auth)
    conn = get_db()

    # Verify character and item exist
    char = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    item = conn.execute("SELECT id, name FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(404, f"Item not found: {item_id}")

    # Upsert: add or increment quantity
    existing = conn.execute(
        "SELECT quantity FROM character_items WHERE character_id = ? AND item_id = ?",
        (character_id, item_id)
    ).fetchone()

    if existing:
        new_qty = existing["quantity"] + quantity
        conn.execute(
            "UPDATE character_items SET quantity = ?, is_equipped = ? WHERE character_id = ? AND item_id = ?",
            (new_qty, 1 if equip else 0, character_id, item_id)
        )
    else:
        conn.execute(
            "INSERT INTO character_items (character_id, item_id, quantity, is_equipped) VALUES (?, ?, ?, ?)",
            (character_id, item_id, quantity, 1 if equip else 0)
        )

    conn.commit()
    conn.close()

    return {
        "status": "added",
        "character_id": character_id,
        "item_id": item_id,
        "item_name": item["name"],
        "quantity": quantity if not existing else new_qty,
        "is_equipped": equip,
    }


@router.delete("/inventory/{character_id}/{item_id}")
def remove_from_inventory(character_id: str, item_id: str, auth: dict = Depends(get_auth)):
    """Remove an item from a character's inventory entirely."""
    require_character_ownership(character_id, auth)
    conn = get_db()

    existing = conn.execute(
        "SELECT quantity FROM character_items WHERE character_id = ? AND item_id = ?",
        (character_id, item_id)
    ).fetchone()

    if not existing:
        conn.close()
        raise HTTPException(404, "Item not in character's inventory")

    conn.execute(
        "DELETE FROM character_items WHERE character_id = ? AND item_id = ?",
        (character_id, item_id)
    )
    conn.commit()
    conn.close()

    return {"status": "removed", "character_id": character_id, "item_id": item_id}


@router.patch("/inventory/{character_id}/{item_id}/equip")
def toggle_equip(character_id: str, item_id: str, equip: bool = True, auth: dict = Depends(get_auth)):
    """Equip or unequip an item in a character's inventory."""
    require_character_ownership(character_id, auth)
    conn = get_db()

    existing = conn.execute(
        "SELECT quantity FROM character_items WHERE character_id = ? AND item_id = ?",
        (character_id, item_id)
    ).fetchone()

    if not existing:
        conn.close()
        raise HTTPException(404, "Item not in character's inventory")

    conn.execute(
        "UPDATE character_items SET is_equipped = ? WHERE character_id = ? AND item_id = ?",
        (1 if equip else 0, character_id, item_id)
    )
    conn.commit()
    conn.close()

    return {"status": "equipped" if equip else "unequipped", "character_id": character_id, "item_id": item_id}


# --- Key Item Inspect (P2: multi-layer lore) ---

@router.get("/key-items/{character_id}")
def list_character_key_items(character_id: str, auth: dict = Depends(get_auth)):
    """List all key items a character owns, with enriched lore.

    Returns key items from equipment_json with surface descriptions,
    deeper lore, and mark-stage-aware narrative text.
    """
    require_character_ownership(character_id, auth)
    conn = get_db()
    char = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    results = inspect_all_key_items(character_id, conn)
    conn.close()

    return {
        "character_id": character_id,
        "key_items": results,
        "count": len(results),
    }


@router.get("/key-items/{character_id}/{item_name}")
def inspect_character_key_item(character_id: str, item_name: str, auth: dict = Depends(get_auth)):
    """Inspect a specific key item with multi-layer lore.

    Returns:
      - surface_description: base description visible at first glance
      - deeper_lore: hidden narrative revealed on closer inspection
      - mark_stage_text: context-aware lore based on character's mark_of_dreamer_stage
      - mark_stage: current mark stage (0-4)
      - portent_index: current front progress (grim portents)

    The mark_stage_text changes dynamically based on how far the character
    has progressed through the Dreaming Hunger arc — items feel different
    at stage 0 (innocent) vs stage 4 (consumed).
    """
    require_character_ownership(character_id, auth)
    conn = get_db()
    char = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    if item_name not in KEY_ITEMS:
        conn.close()
        raise HTTPException(404, f"Unknown key item: {item_name}")

    result = inspect_key_item(character_id, item_name, conn)
    conn.close()

    if result is None:
        raise HTTPException(
            404,
            f"Character {character_id} does not have key item: {item_name}",
        )

    return result
