"""
FastAPI route tests using TestClient (no real Claude/DWSIM calls).

Patches claude_client.run and dwsim_tools.build_flowsheet_no_sim so
these tests run without API keys or DWSIM installed.
"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import api.session as s
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test_api.db")


@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


@pytest.fixture()
def session_id(client):
    r = client.post("/sessions", json={"project_name": "test"})
    assert r.status_code == 201
    return r.json()["session_id"]


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Session CRUD ───────────────────────────────────────────────────────────────

def test_create_session(client):
    r = client.post("/sessions", json={"project_name": "my plant"})
    assert r.status_code == 201
    data = r.json()
    assert data["project_name"] == "my plant"
    assert data["current_stage"] == 1


def test_get_session(client, session_id):
    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200


def test_get_session_404(client):
    r = client.get("/sessions/no-such-id")
    assert r.status_code == 404


def test_list_sessions(client, session_id):
    r = client.get("/sessions")
    assert r.status_code == 200
    ids = [s["session_id"] for s in r.json()]
    assert session_id in ids


def test_delete_session(client, session_id):
    r = client.delete(f"/sessions/{session_id}")
    assert r.status_code == 204
    r2 = client.get(f"/sessions/{session_id}")
    assert r2.status_code == 404


# ── Gating ─────────────────────────────────────────────────────────────────────

def test_stage_2_blocked_without_stage_1_approval(client, session_id):
    r = client.post(f"/sessions/{session_id}/stages/2/run", json={})
    assert r.status_code == 409


def test_approve_advances_stage(client, session_id):
    import api.session as s
    # Manually insert a Stage 1 artifact so approve can fire
    s.update_stage(session_id, 1, artifact={"target_chemical": "methanol"},
                   summary="ok")
    r = client.post(f"/sessions/{session_id}/stages/1/approve")
    assert r.status_code == 200
    data = r.json()
    assert data["session"]["current_stage"] == 2


def test_refine_stores_feedback(client, session_id):
    import api.session as s
    s.update_stage(session_id, 1, artifact={}, summary="initial")
    r = client.post(
        f"/sessions/{session_id}/stages/1/refine",
        json={"feedback": "change to ethanol"},
    )
    assert r.status_code == 200
    sess = client.get(f"/sessions/{session_id}").json()
    assert sess["stage_data"]["1"]["feedback"] == "change to ethanol"


# ── Download ────────────────────────────────────────────────────────────────────

def test_download_before_stage_5_returns_409(client, session_id):
    r = client.get(f"/sessions/{session_id}/download")
    assert r.status_code == 409


def test_download_after_stage_5_returns_zip(client, session_id, tmp_path):
    import api.session as s
    # Fake a Stage 5 artifact with paths to non-existent files
    # (bundler gracefully skips missing files)
    s.update_stage(session_id, 5,
                   artifact={"dwxmz_path": None, "image_path": None},
                   summary="done")
    r = client.get(f"/sessions/{session_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert len(r.content) > 0   # at minimum brief.json is in the zip
