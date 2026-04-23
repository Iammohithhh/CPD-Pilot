"""
Unit tests for connection / layout logic that does NOT require DWSIM.

These run in any environment (CI, no-DWSIM machines, etc.).
Run with: pytest tests/unit/ -v
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dwsim_tools as dt


# ── Helpers ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_state():
    """Ensure _sim and _object_registry are reset before and after each test."""
    dt._sim = None
    dt._object_registry = {}
    if hasattr(dt.connect_objects, "_counter"):
        dt.connect_objects._counter = 0
    yield
    dt._sim = None
    dt._object_registry = {}


# ── connect_objects (no flowsheet) ────────────────────────────────────────────

def test_connect_objects_no_flowsheet():
    r = dt.connect_objects("A", "B")
    assert not r["success"]
    assert "error" in r


def test_connect_objects_missing_source():
    dt._sim = object()
    dt._object_registry = {"B": object()}
    r = dt.connect_objects("MISSING", "B")
    assert not r["success"]
    assert "MISSING" in r["error"]


def test_connect_objects_missing_dest():
    dt._sim = object()
    dt._object_registry = {"A": object()}
    r = dt.connect_objects("A", "MISSING")
    assert not r["success"]
    assert "MISSING" in r["error"]


# ── connect_all parsing ────────────────────────────────────────────────────────

def test_connect_all_empty_list():
    result = dt.connect_all([])
    assert result["success"]
    assert result["connected"] == 0
    assert result["failed"] == 0
    assert result["details"] == []


def test_connect_all_triplet_expands_to_two_calls():
    """A triplet [A, MID, B] must expand into two pair calls → 2 detail entries."""
    result = dt.connect_all([("A", "MID", "B")])
    assert len(result["details"]) == 2


def test_connect_all_mixed_formats():
    """Mix of pairs and triplets produces correct detail count."""
    result = dt.connect_all([
        ("A", "B"),          # pair → 1 call
        ("C", "D", "E"),     # triplet → 2 calls
        ("F", "G"),          # pair → 1 call
    ])
    assert len(result["details"]) == 4


# ── _is_stream ────────────────────────────────────────────────────────────────

def test_is_stream_absent_tag():
    assert not dt._is_stream("NO_SUCH_TAG")


def test_is_stream_unrecognised_object():
    """An object that doesn't expose GraphicObject.ObjectType is not a stream."""
    dt._object_registry["FAKE"] = object()
    assert not dt._is_stream("FAKE")


# ── _compute_layout ───────────────────────────────────────────────────────────

def test_compute_layout_no_connections_returns_all_nodes():
    ops = [{"name": f"U-{i}"} for i in range(9)]
    positions = dt._compute_layout(ops, [])
    assert set(positions.keys()) == {f"U-{i}" for i in range(9)}


def test_compute_layout_no_connections_unique_positions():
    ops = [{"name": f"U-{i}"} for i in range(9)]
    positions = dt._compute_layout(ops, [])
    assert len(set(positions.values())) == 9


def test_compute_layout_linear_chain_x_increases():
    """A→B→C should be placed left to right."""
    ops = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    pos = dt._compute_layout(ops, [("A", "B"), ("B", "C")])
    assert pos["A"][0] < pos["B"][0] < pos["C"][0]


def test_compute_layout_all_nodes_placed():
    """Every node, including unreachable ones, must appear in the output."""
    ops = [{"name": n} for n in ["X", "Y", "Z", "ISLAND"]]
    pos = dt._compute_layout(ops, [("X", "Y"), ("Y", "Z")])
    assert set(pos.keys()) == {"X", "Y", "Z", "ISLAND"}


def test_compute_layout_cycle_does_not_hang():
    """Cyclic graphs (recycle loops) must not cause infinite recursion."""
    ops = [{"name": n} for n in ["A", "B", "C"]]
    pos = dt._compute_layout(ops, [("A", "B"), ("B", "C"), ("C", "A")])
    assert len(pos) == 3


def test_compute_layout_empty():
    pos = dt._compute_layout([], [])
    assert pos == {}


# ── process_library structural integrity ──────────────────────────────────────

import process_library as lib


def test_all_processes_have_connections():
    for name in lib.list_available_processes():
        proc = lib.lookup_process(name)
        assert proc["found"]
        assert len(proc.get("connections", [])) > 0, f"'{name}' has no connections"


def test_all_connection_tags_declared():
    """
    Every tag referenced in connections must exist in unit_operations or streams.
    Catches typos in the process library before they hit DWSIM.
    """
    for name in lib.list_available_processes():
        proc = lib.lookup_process(name)
        all_tags = (
            {u["name"] for u in proc.get("unit_operations", [])}
            | {s["name"] for s in proc.get("streams", [])}
        )
        for conn in proc.get("connections", []):
            for tag in conn:
                assert tag in all_tags, (
                    f"Process '{name}': tag '{tag}' in connections "
                    f"not declared in unit_operations or streams"
                )


def test_all_processes_have_required_keys():
    required = {"compounds", "thermo_model", "unit_operations", "streams", "connections"}
    for name in lib.list_available_processes():
        proc = lib.lookup_process(name)
        missing = required - set(proc.keys())
        assert not missing, f"Process '{name}' missing keys: {missing}"


def test_lookup_aliases():
    """Common aliases resolve to the correct canonical process."""
    assert lib.lookup_process("nh3")["chemical"] == "ammonia"
    assert lib.lookup_process("meoh")["chemical"] == "methanol"
    assert lib.lookup_process("acetic acid")["chemical"] == "acetic_acid"
    assert lib.lookup_process("h2so4")["chemical"] == "sulphuric_acid"
    assert lib.lookup_process("h2")["chemical"] == "hydrogen"


def test_lookup_missing_returns_not_found():
    result = lib.lookup_process("unobtainium_xyz")
    assert not result["found"]
    assert "available_chemicals" in result
