"""Unit tests for the SQLite session store (no DWSIM, no API key needed)."""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect the session DB to a temp file for test isolation."""
    import api.session as s
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test_sessions.db")


import api.session as sess


def test_create_and_get():
    s = sess.create_session("test project")
    assert s["session_id"]
    assert s["project_name"] == "test project"
    assert s["current_stage"] == 1
    assert s["stage_data"] == {}

    fetched = sess.get_session(s["session_id"])
    assert fetched["session_id"] == s["session_id"]


def test_get_nonexistent():
    assert sess.get_session("no-such-id") is None


def test_update_stage_stores_artifact():
    s = sess.create_session()
    updated = sess.update_stage(
        s["session_id"], 1,
        artifact={"target_chemical": "methanol"},
        summary="Methanol at 1000 kg/hr",
    )
    assert updated["stage_data"]["1"]["artifact"]["target_chemical"] == "methanol"
    assert not updated["stage_data"]["1"]["approved"]


def test_approve_stage_advances_pointer():
    s = sess.create_session()
    sess.update_stage(s["session_id"], 1, artifact={}, summary="ok")
    updated = sess.approve_stage(s["session_id"], 1)
    assert updated["stage_data"]["1"]["approved"]
    assert updated["current_stage"] == 2


def test_approve_stage_5_does_not_advance_beyond_5():
    s = sess.create_session()
    # Approve stages 1–4 first to advance pointer
    for stage in range(1, 5):
        sess.update_stage(s["session_id"], stage, artifact={}, summary="ok")
        sess.approve_stage(s["session_id"], stage)
    sess.update_stage(s["session_id"], 5, artifact={}, summary="done")
    updated = sess.approve_stage(s["session_id"], 5)
    assert updated["current_stage"] == 5  # stays at 5


def test_set_feedback():
    s = sess.create_session()
    sess.update_stage(s["session_id"], 1, artifact={}, summary="initial")
    updated = sess.set_feedback(s["session_id"], 1, "Change the chemical to ethanol")
    assert updated["stage_data"]["1"]["feedback"] == "Change the chemical to ethanol"
    assert not updated["stage_data"]["1"]["approved"]


def test_list_sessions():
    sess.create_session("alpha")
    sess.create_session("beta")
    sessions = sess.list_sessions()
    names = [s["project_name"] for s in sessions]
    assert "alpha" in names
    assert "beta" in names


def test_delete_session():
    s = sess.create_session("to delete")
    assert sess.delete_session(s["session_id"])
    assert sess.get_session(s["session_id"]) is None


def test_delete_nonexistent_returns_false():
    assert not sess.delete_session("ghost-id-xyz")


def test_update_nonexistent_raises():
    with pytest.raises(KeyError):
        sess.update_stage("ghost", 1, artifact={}, summary="")
