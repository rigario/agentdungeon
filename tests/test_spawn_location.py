"""Test default character spawn location is valid and actionable.

Validates the fix for task 276ed636 — fresh-character spawn/world-state mismatch.

This test ensures the default starting_location constant is a valid
location known to the world seed, so that actions and turns succeed
immediately after character creation.
"""
import pytest

# Constants: canonical location IDs from world seed
RUSTY_TANKARD_ID = "rusty-tankard"
VALID_STARTING_LOCATIONS = {RUSTY_TANKARD_ID, "thornhold"}  # both exist in seed

def test_default_starting_location_is_valid():
    """Character creation uses a starting location that is present in the world seed."""
    # Import here to avoid circular imports; characters.py defines it at module scope
    from app.routers.characters import create_character
    # We can't actually call create_character without DB, but we can inspect the source constant.
    # Instead, sanity-check: the fallback used in level-up path and map default.
    from app.routers.characters import _get_character as _  # noqa: F401
    # Check by reading the source value
    import inspect
    import app.routers.characters as chars_mod
    source = inspect.getsource(chars_mod.create_character)
    # The create_character inner function sets starting_location; we assert the string literal is valid
    assert 'rusty-tankard' in source, "Default spawn should be 'rusty-tankard' (valid seeded location)"

def test_map_default_current_location():
    """Map endpoint returns a valid default current_location matching seed."""
    import app.routers.map as map_mod
    import inspect
    source = inspect.getsource(map_mod.get_world_state)
    assert 'rusty-tankard' in source or 'rusty_tankard' in source, \
        "Map default current_location should be a valid seeded location"

def test_valid_starting_location_in_seed():
    """The chosen default location ('rusty-tankard') exists in seed.py LOCATIONS."""
    from app.scripts import seed
    # seed.LOCATIONS is a list of dicts
    ids = [loc["id"] for loc in seed.LOCATIONS]
    assert RUSTY_TANKARD_ID in ids, f"rusty-tankard must exist in seed.LOCATIONS; found: {ids[:5]}..."
