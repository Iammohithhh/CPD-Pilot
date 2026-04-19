"""
Unit tests for export_flowsheet_image and the SVG fallback renderer.
No DWSIM required.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dwsim_tools as dt


@pytest.fixture(autouse=True)
def clean_state():
    dt._sim = None
    dt._object_registry = {}
    yield
    dt._sim = None
    dt._object_registry = {}


def test_export_no_flowsheet():
    r = dt.export_flowsheet_image()
    assert not r["success"]
    assert "error" in r


def test_render_flowsheet_svg_empty(tmp_path):
    """SVG renderer handles empty registry without raising."""
    out = str(tmp_path / "empty.svg")
    dt._render_flowsheet_svg({}, out)
    assert os.path.exists(out)
    content = open(out).read()
    assert "<svg" in content


def test_render_flowsheet_svg_produces_valid_svg(tmp_path):
    """Registry with mock objects produces an SVG with tag labels."""

    class FakeGO:
        X, Y = 100, 150
        ObjectType = "Heater"

    class FakeObj:
        GraphicObject = FakeGO()

    registry = {"H-01": FakeObj(), "C-01": FakeObj()}
    registry["C-01"].GraphicObject.X = 300
    registry["C-01"].GraphicObject.Y = 150
    registry["C-01"].GraphicObject.ObjectType = "Cooler"

    out = str(tmp_path / "flowsheet.svg")
    dt._render_flowsheet_svg(registry, out)

    assert os.path.exists(out)
    content = open(out).read()
    assert "<svg" in content
    assert "H-01" in content
    assert "C-01" in content


def test_svg_fallback_strategy_uses_registry(tmp_path):
    """
    export_flowsheet_image falls through to svg_fallback when _sim is set
    but FlowsheetSurface is not available.
    """

    class FakeSim:
        pass

    class FakeGO:
        X, Y = 120, 200
        ObjectType = "Flash"

    class FakeObj:
        GraphicObject = FakeGO()

    dt._sim = FakeSim()
    dt._object_registry = {"V-01": FakeObj()}

    out = str(tmp_path / "pfd.png")
    r = dt.export_flowsheet_image(output_path=out)

    # Success with svg_fallback strategy (png conversion may not be available)
    assert r["success"], f"SVG fallback failed: {r.get('error')}"
    assert r["strategy"] == "svg_fallback"
    assert os.path.exists(r["image_path"])
