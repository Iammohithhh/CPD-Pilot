"""
main.py — CPD-Pilot FastAPI application.

5-Stage workflow endpoints:

  POST   /sessions                              — create new session
  GET    /sessions                              — list all sessions
  GET    /sessions/{session_id}                 — get session state
  DELETE /sessions/{session_id}                 — delete session

  POST   /sessions/{session_id}/stages/{n}/run      — run stage n (streaming SSE)
  POST   /sessions/{session_id}/stages/{n}/approve  — approve stage output
  POST   /sessions/{session_id}/stages/{n}/refine   — submit refinement feedback

  GET    /sessions/{session_id}/download        — download zip bundle (Stage 5 only)

  GET    /health                                — liveness check

Run locally:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import gating, session as _sess, bundler
from api.stages import brief, routes, thermo, bfd, pfd

app = FastAPI(
    title="CPD-Pilot API",
    version="1.0.0",
    description="Chemical Process Design — 5-stage AI-assisted workflow",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic request bodies ────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    project_name: str = ""


class RunStageRequest(BaseModel):
    user_input: str = ""
    # Stage-specific extra fields passed as freeform JSON
    extra: dict = {}


class RefineRequest(BaseModel):
    feedback: str


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Sessions ───────────────────────────────────────────────────────────────────

@app.post("/sessions", status_code=201)
def create_session(req: CreateSessionRequest):
    return _sess.create_session(req.project_name)


@app.get("/sessions")
def list_sessions():
    return _sess.list_sessions()


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    sess = _sess.get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return sess


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not _sess.delete_session(session_id):
        raise HTTPException(404, f"Session {session_id!r} not found")


# ── Stage runners ──────────────────────────────────────────────────────────────

def _require_session(session_id: str) -> dict:
    sess = _sess.get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id!r} not found")
    return sess


def _check_gate(sess: dict, stage: int):
    can_run, reason = gating.check_gate(sess, stage)
    if not can_run:
        raise HTTPException(409, reason)


def _get_artifact(sess: dict, stage: int) -> Any:
    return sess["stage_data"].get(str(stage), {}).get("artifact")


def _sse_wrap(generator):
    """Wrap an async generator as SSE (text/event-stream)."""
    async def _inner():
        async for chunk in generator:
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(_inner(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/stages/1/run")
async def run_stage_1(session_id: str, req: RunStageRequest):
    """
    Stage 1 — Brief.
    Body: { "user_input": "I want to produce 1000 kg/hr of methanol..." }
    Streams tokens as SSE.  After streaming, call /approve or /refine.
    """
    sess = _require_session(session_id)
    feedback = sess["stage_data"].get("1", {}).get("feedback", "")

    async def _gen():
        full = []
        async for chunk in brief.stream(req.user_input, feedback=feedback):
            full.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        # Persist raw response as artifact (JSON extraction happens in /approve)
        _sess.update_stage(session_id, 1,
                           artifact={"raw": "".join(full)},
                           summary="".join(full)[:300] + "…")
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/stages/2/run")
async def run_stage_2(session_id: str, req: RunStageRequest):
    """
    Stage 2 — Routes.
    Requires Stage 1 approved.
    Body: {} (uses saved Stage 1 artifact automatically)
    """
    sess = _require_session(session_id)
    _check_gate(sess, 2)
    brief_artifact = _get_artifact(sess, 1) or {}
    feedback = sess["stage_data"].get("2", {}).get("feedback", "")

    async def _gen():
        full = []
        async for chunk in routes.stream(brief_artifact, feedback=feedback):
            full.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        _sess.update_stage(session_id, 2,
                           artifact={"raw": "".join(full)},
                           summary="".join(full)[:300] + "…")
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/stages/3/run")
async def run_stage_3(session_id: str, req: RunStageRequest):
    """
    Stage 3 — Thermo.
    Requires Stage 2 approved.
    Body: { "extra": { "selected_route": {...} } }
    If selected_route is omitted, the recommended route from Stage 2 is used.
    """
    sess = _require_session(session_id)
    _check_gate(sess, 3)
    brief_art = _get_artifact(sess, 1) or {}
    route_art = req.extra.get("selected_route") or _get_artifact(sess, 2) or {}
    feedback = sess["stage_data"].get("3", {}).get("feedback", "")

    async def _gen():
        full = []
        async for chunk in thermo.stream(brief_art, route_art, feedback=feedback):
            full.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        _sess.update_stage(session_id, 3,
                           artifact={"raw": "".join(full)},
                           summary="".join(full)[:300] + "…")
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/stages/4/run")
async def run_stage_4(session_id: str, req: RunStageRequest):
    """
    Stage 4 — Block Flow Diagram.
    Requires Stage 3 approved.
    Body: {} (uses all previous stage artifacts)
    """
    sess = _require_session(session_id)
    _check_gate(sess, 4)
    brief_art = _get_artifact(sess, 1) or {}
    route_art = _get_artifact(sess, 2) or {}
    thermo_art = _get_artifact(sess, 3) or {}
    feedback = sess["stage_data"].get("4", {}).get("feedback", "")

    async def _gen():
        full = []
        async for chunk in bfd.stream(brief_art, route_art, thermo_art, feedback=feedback):
            full.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        _sess.update_stage(session_id, 4,
                           artifact={"raw": "".join(full)},
                           summary="".join(full)[:300] + "…")
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/stages/5/run")
async def run_stage_5(session_id: str, req: RunStageRequest):
    """
    Stage 5 — DWSIM PFD.
    Requires Stage 4 approved.

    This stage does NOT stream tokens — it calls DWSIM synchronously and
    returns the final result JSON when done.  The frontend should show a
    spinner.

    Returns:
      success, dwxmz_path, image_path, topology_summary, connections_wired,
      connections_failed, connection_warning
    """
    sess = _require_session(session_id)
    _check_gate(sess, 5)
    brief_art = _get_artifact(sess, 1) or {}
    route_art = _get_artifact(sess, 2) or {}
    thermo_art = _get_artifact(sess, 3) or {}
    bfd_art = _get_artifact(sess, 4) or {}
    feedback = sess["stage_data"].get("5", {}).get("feedback", "")

    result = pfd.run_and_build(
        brief_art, route_art, thermo_art, bfd_art, feedback=feedback
    )

    summary = (
        f"DWSIM flowsheet built: {result.get('connections_wired', 0)} connections wired, "
        f"{result.get('connections_failed', 0)} failed.\n"
        f"Files: {result.get('dwxmz_path')} | {result.get('image_path')}"
    )
    _sess.update_stage(session_id, 5, artifact=result, summary=summary)
    return result


# ── Gate: approve ──────────────────────────────────────────────────────────────

@app.post("/sessions/{session_id}/stages/{stage}/approve")
def approve_stage(session_id: str, stage: int):
    """Mark stage as approved and advance the session pointer."""
    if stage < 1 or stage > 5:
        raise HTTPException(400, "stage must be 1–5")
    _require_session(session_id)
    try:
        updated = _sess.approve_stage(session_id, stage)
    except KeyError as e:
        raise HTTPException(404, str(e))
    gate_msg = gating.gate_summary(
        stage,
        updated["stage_data"].get(str(stage), {}).get("artifact"),
        updated["stage_data"].get(str(stage), {}).get("summary", ""),
    )
    return {"session": updated, "gate_message": gate_msg}


# ── Gate: refine ───────────────────────────────────────────────────────────────

@app.post("/sessions/{session_id}/stages/{stage}/refine")
def refine_stage(session_id: str, stage: int, req: RefineRequest):
    """
    Store user feedback for a stage.  The frontend should then call
    /run again to re-execute the stage with the feedback incorporated.
    """
    if stage < 1 or stage > 5:
        raise HTTPException(400, "stage must be 1–5")
    _require_session(session_id)
    try:
        updated = _sess.set_feedback(session_id, stage, req.feedback)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {
        "session": updated,
        "message": f"Feedback stored for Stage {stage}. Call /run to re-execute.",
    }


# ── Download bundle ─────────────────────────────────────────────────────────────

@app.get("/sessions/{session_id}/download")
def download_bundle(session_id: str):
    """
    Stream the zip bundle containing .dwxmz + PFD image + brief.json.
    Stage 5 must have been run first.
    """
    sess = _require_session(session_id)
    if not gating.is_approved(sess["stage_data"], 5):
        # Allow download even if not formally approved, as long as Stage 5 ran
        stage5 = sess["stage_data"].get("5", {})
        if not stage5.get("artifact"):
            raise HTTPException(
                409,
                "Stage 5 (DWSIM PFD) must be run before downloading the bundle.",
            )

    data = bundler.create_bundle(sess)
    filename = bundler.bundle_filename(sess)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
