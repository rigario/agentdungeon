"""
Unit tests for check_deployment_parity.py
"""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from check_deployment_parity import (
    sha256_of_file,
    symbol_in_file,
    check_symbols,
    FILES_TO_CHECK,
    REQUIRED_SYMBOLS,
)


def test_sha256_of_file_known_content():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("hello world\n")
        path = f.name
    try:
        sha = sha256_of_file(Path(path))
        assert sha == "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"
    finally:
        Path(path).unlink()


def test_symbol_in_file_basic():
    assert symbol_in_file("def foo(x): pass", "foo") is True

def test_symbol_in_file_async():
    assert symbol_in_file("async def bar(): pass", "bar") is True

def test_symbol_in_file_missing():
    assert symbol_in_file("def baz(): pass", "missing") is False

def test_check_symbols_all_present():
    content = """
def _extract_trace(data): pass
def _build_absurd_refusal(intent, world): pass
def synthesize_narration(server_result, intent, world_context, session_id=None): pass
"""
    missing = check_symbols(content, ["_extract_trace", "_build_absurd_refusal", "synthesize_narration"], "test")
    assert missing == []

def test_check_symbols_missing_one():
    content = """
def _extract_trace(data): pass
def synthesize_narration(server_result, intent, world_context, session_id=None): pass
"""
    missing = check_symbols(content, ["_extract_trace", "_build_absurd_refusal"], "test")
    assert len(missing) == 1

def test_required_symbols_coverage():
    for rel in FILES_TO_CHECK:
        assert rel in REQUIRED_SYMBOLS, f"{rel} missing from REQUIRED_SYMBOLS"

def test_required_symbols_include_critical_p0_fixes():
    assert "_extract_trace" in REQUIRED_SYMBOLS["services/synthesis.py"]
    assert "_extract_error_status" in REQUIRED_SYMBOLS["services/intent_router.py"]
    assert "_build_absurd_refusal" in REQUIRED_SYMBOLS["services/synthesis.py"]
