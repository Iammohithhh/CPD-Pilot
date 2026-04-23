"""
Integration tests: fine-grained connect_objects regression tests.

Covers the specific cases that historically caused silent failures:
  - stream → unit op
  - unit op → unit op (auto intermediate stream)
  - multi-outlet unit ops (Flash, ShortcutColumn, Splitter)
  - multi-inlet unit ops (Mixer)

Skipped unless DWSIM is installed.
Run with: pytest tests/integration/test_dwsim_connect.py -v
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dwsim_tools as dt
from tests.conftest import DWSIM_AVAILABLE

pytestmark = pytest.mark.skipif(not DWSIM_AVAILABLE, reason="DWSIM not installed")


@pytest.fixture(autouse=True)
def fresh_flowsheet():
    """Each test gets a clean single-compound flowsheet."""
    dt._sim = None
    dt._object_registry = {}
    if hasattr(dt.connect_objects, "_counter"):
        dt.connect_objects._counter = 0
    dt.initialize_dwsim()
    dt.create_flowsheet(["Water", "Methanol", "Ethanol"], "NRTL")
    yield
    dt._sim = None
    dt._object_registry = {}


def test_stream_to_unit_op():
    """MaterialStream → Heater direct connection."""
    dt.add_unit_operation("MaterialStream", "S-01", 60, 100)
    dt.add_unit_operation("Heater", "H-01", 200, 100)
    r = dt.connect_objects("S-01", "H-01")
    assert r["success"], f"Stream→UnitOp failed: {r.get('error')}"
    assert "intermediate_stream" not in r


def test_unit_op_to_unit_op_creates_intermediate():
    """Both sides are unit ops → connect_objects inserts an AUTO stream."""
    dt.add_unit_operation("Heater", "H-01", 200, 100)
    dt.add_unit_operation("Cooler", "C-01", 400, 100)
    r = dt.connect_objects("H-01", "C-01")
    assert r["success"], f"UnitOp→UnitOp failed: {r.get('error')}"
    assert "intermediate_stream" in r
    mid = r["intermediate_stream"]
    assert mid.startswith("_AUTO_S"), f"Unexpected auto-stream name: {mid}"
    assert dt._is_stream(mid), "Auto-created tag is not recognised as a stream"


def test_flash_dual_outlet_both_connect():
    """
    Flash has vapour outlet (port 0) and liquid outlet (port 1).
    Both must wire successfully without port conflicts.
    This was the primary bug: the second call to ConnectObjects(-1,-1)
    would silently fail because port 0 was already occupied.
    """
    dt.add_unit_operation("MaterialStream", "FEED", 60, 150)
    dt.add_unit_operation("Flash", "V-01", 240, 150)
    dt.add_unit_operation("Cooler", "C-VAP", 420, 80)
    dt.add_unit_operation("Pump", "P-LIQ", 420, 220)

    r = dt.connect_objects("FEED", "V-01")
    assert r["success"], f"Feed→Flash: {r.get('error')}"

    r_vap = dt.connect_objects("V-01", "C-VAP")
    assert r_vap["success"], f"Flash vapour→Cooler: {r_vap.get('error')}"

    r_liq = dt.connect_objects("V-01", "P-LIQ")
    assert r_liq["success"], f"Flash liquid→Pump: {r_liq.get('error')}"


def test_mixer_multi_inlet():
    """Mixer accepts three separate inlet streams without port conflicts."""
    for i in range(1, 4):
        dt.add_unit_operation("MaterialStream", f"S-{i:02d}", 60, i * 100)
    dt.add_unit_operation("Mixer", "MIX-01", 240, 200)

    for i in range(1, 4):
        r = dt.connect_objects(f"S-{i:02d}", "MIX-01")
        assert r["success"], f"S-{i:02d}→Mixer failed: {r.get('error')}"


def test_column_dual_outlet_both_connect():
    """ShortcutColumn has distillate (port 0) and bottoms (port 1)."""
    dt.add_unit_operation("MaterialStream", "FEED", 60, 150)
    dt.add_unit_operation("ShortcutColumn", "T-01", 240, 150)
    dt.add_unit_operation("Cooler", "C-DIST", 420, 80)
    dt.add_unit_operation("Heater", "H-BOT", 420, 220)

    dt.connect_objects("FEED", "T-01")

    r_dist = dt.connect_objects("T-01", "C-DIST")
    assert r_dist["success"], f"Column distillate→Cooler: {r_dist.get('error')}"

    r_bot = dt.connect_objects("T-01", "H-BOT")
    assert r_bot["success"], f"Column bottoms→Heater: {r_bot.get('error')}"


def test_splitter_dual_outlet():
    """Splitter (NodeOut) has two outlets; both must wire."""
    dt.add_unit_operation("MaterialStream", "FEED", 60, 150)
    dt.add_unit_operation("Splitter", "SPL-01", 240, 150)
    dt.add_unit_operation("Heater", "H-A", 420, 80)
    dt.add_unit_operation("Cooler", "C-B", 420, 220)

    dt.connect_objects("FEED", "SPL-01")

    r1 = dt.connect_objects("SPL-01", "H-A")
    assert r1["success"], f"Splitter→Heater: {r1.get('error')}"

    r2 = dt.connect_objects("SPL-01", "C-B")
    assert r2["success"], f"Splitter→Cooler: {r2.get('error')}"


def test_connect_all_linear_chain():
    """connect_all on a simple linear chain reports 0 failures."""
    dt.add_unit_operation("MaterialStream", "S-01", 60, 150)
    dt.add_unit_operation("Heater", "H-01", 200, 150)
    dt.add_unit_operation("ConversionReactor", "R-01", 380, 150)
    dt.add_unit_operation("Cooler", "C-01", 560, 150)

    result = dt.connect_all([
        ("S-01", "H-01"),
        ("H-01", "R-01"),
        ("R-01", "C-01"),
    ])
    assert result["success"], f"connect_all failed: {result}"
    assert result["failed"] == 0, (
        f"connect_all had {result['failed']} failure(s): "
        f"{[d for d in result['details'] if not d.get('success')]}"
    )


def test_connect_objects_unknown_tags():
    """Connecting non-existent tags returns a clean failure dict."""
    r = dt.connect_objects("GHOST_A", "GHOST_B")
    assert not r["success"]
    assert "error" in r
