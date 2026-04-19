"""
bundler.py — Creates the download zip for a completed project.

Bundle contains:
  <chemical>_topology.dwxmz   — DWSIM flowsheet file
  <chemical>_pfd.png (or .svg) — flowsheet image
  brief.json                  — structured session summary
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path


def create_bundle(session: dict, output_dir: str | None = None) -> bytes:
    """
    Pack the session's Stage 5 outputs into an in-memory zip.

    Returns the zip as bytes so it can be streamed directly from FastAPI
    without writing a temp file.
    """
    stage_data = session.get("stage_data", {})
    stage5 = stage_data.get("5", {})
    artifact = stage5.get("artifact", {}) or {}

    dwxmz = artifact.get("dwxmz_path")
    image = artifact.get("image_path")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # 1. DWSIM flowsheet
        if dwxmz and os.path.exists(dwxmz):
            zf.write(dwxmz, arcname=Path(dwxmz).name)

        # 2. PFD image
        if image and os.path.exists(image):
            zf.write(image, arcname=Path(image).name)

        # 3. Brief JSON — human-readable session summary
        brief = {
            "session_id": session.get("session_id"),
            "project_name": session.get("project_name"),
            "stages": {
                k: {
                    "summary": v.get("summary", ""),
                    "artifact": v.get("artifact"),
                }
                for k, v in stage_data.items()
            },
        }
        zf.writestr("brief.json", json.dumps(brief, indent=2, default=str))

    buf.seek(0)
    return buf.read()


def bundle_filename(session: dict) -> str:
    """Return a safe filename for the zip download."""
    name = (
        session.get("project_name")
        or (
            session.get("stage_data", {})
            .get("1", {})
            .get("artifact", {})
            or {}
        ).get("target_chemical", "process")
    )
    slug = str(name).lower().replace(" ", "_").replace("/", "_")
    return f"{slug}_cpd_bundle.zip"
