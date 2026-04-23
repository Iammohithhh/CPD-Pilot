"""
Integration tests: build a DWSIM topology for every library process and
assert that all connections are wired without failures.

These tests require DWSIM to be installed and are skipped otherwise.
Run with: pytest tests/integration/test_library_processes.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import process_library as lib
import dwsim_tools as dt
from tests.conftest import DWSIM_AVAILABLE

ALL_CHEMICALS = lib.list_available_processes()


@pytest.fixture(autouse=True)
def reset_dwsim_state():
    """Reset module-level DWSIM state before each test to avoid cross-test leakage."""
    dt._sim = None
    dt._object_registry = {}
    # Reset the auto-stream counter so tags are deterministic per test
    connect_counter_attr = "_counter"
    if hasattr(dt.connect_objects, connect_counter_attr):
        setattr(dt.connect_objects, connect_counter_attr, 0)
    yield
    dt._sim = None
    dt._object_registry = {}


@pytest.mark.skipif(not DWSIM_AVAILABLE, reason="DWSIM not installed")
@pytest.mark.parametrize("chemical", ALL_CHEMICALS)
def test_build_topology_zero_connection_failures(chemical, tmp_path):
    """
    Build a full DWSIM flowsheet topology for every library process.
    Asserts:
      - build_flowsheet_no_sim succeeds
      - connections_failed == 0
      - output .dwxmz file exists and is non-empty
    """
    process = lib.lookup_process(chemical)
    assert process["found"], f"Process '{chemical}' not found in library"

    result = dt.build_flowsheet_no_sim(process, output_dir=str(tmp_path))

    assert result["success"], (
        f"build_flowsheet_no_sim failed for '{chemical}'.\n"
        f"Connection warning: {result.get('connection_warning', 'none')}\n"
        f"Steps: {result.get('steps', [])}"
    )
    assert result["connections_failed"] == 0, (
        f"'{chemical}' had {result['connections_failed']} connection failure(s).\n"
        f"{result.get('connection_warning', '')}"
    )

    file_path = result["file_path"]
    assert file_path is not None, f"No file_path returned for '{chemical}'"
    assert os.path.exists(file_path), f"Output file not created: {file_path}"
    assert os.path.getsize(file_path) > 1024, (
        f"Output file suspiciously small ({os.path.getsize(file_path)} bytes): {file_path}"
    )


@pytest.mark.skipif(not DWSIM_AVAILABLE, reason="DWSIM not installed")
@pytest.mark.parametrize("chemical", ALL_CHEMICALS)
def test_all_unit_ops_added(chemical, tmp_path):
    """All declared unit operations must be added successfully."""
    process = lib.lookup_process(chemical)
    result = dt.build_flowsheet_no_sim(process, output_dir=str(tmp_path))

    add_step = next(
        (s for s in result.get("steps", []) if s.get("step") == "add_unit_operations"),
        None,
    )
    assert add_step is not None, f"add_unit_operations step missing for '{chemical}'"
    assert add_step.get("failed", 0) == 0, (
        f"'{chemical}' had {add_step['failed']} unit-op add failure(s): "
        f"{[d for d in add_step.get('details', []) if not d.get('success')]}"
    )
