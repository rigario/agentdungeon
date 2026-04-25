"""Regression tests for action-handler module scope hazards."""

import ast
from pathlib import Path


def test_explore_loot_service_call_cannot_be_shadowed_by_combat_loot_variable():
    """Explore should call a service alias, not a name that combat assigns locally."""
    source = Path("app/routers/actions.py").read_text()
    tree = ast.parse(source)

    imports_loot_alias = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.services"
        and any(alias.name == "loot" and alias.asname == "loot_service" for alias in node.names)
        for node in tree.body
    )
    assert imports_loot_alias, "loot service must be imported as loot_service to avoid submit_action local-name shadowing"

    submit = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "submit_action"
    )
    calls_roll_for_location_via_alias = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "roll_for_location"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "loot_service"
        for node in ast.walk(submit)
    )
    assert calls_roll_for_location_via_alias, "explore item rolls must call loot_service.roll_for_location(...)"
