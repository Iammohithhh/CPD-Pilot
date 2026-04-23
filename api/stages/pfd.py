"""
Stage 5 — DWSIM PFD: build flowsheet, save .dwxmz, export image.

Claude generates the full process_data dict, then we call dwsim_tools
directly (no MCP round-trip) to build and save the flowsheet.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dwsim_tools as _dt
import process_library as _lib
from api import claude_client as _cc

_PROMPT = """Based on all approved stages, produce a complete DWSIM process_data dict.

The dict must have exactly these keys:
  chemical       — string (target chemical name, snake_case for file naming)
  name           — string (human-readable process name)
  compounds      — list of DWSIM compound names (from the approved Thermo stage)
  thermo_model   — string (from the approved Thermo stage)
  unit_operations — list of objects:
      { "type": "<DWSIM type>", "name": "<TAG>", "purpose": "<one sentence>" }
  streams        — list of feed stream objects:
      { "name": "<TAG>", "type": "material",
        "T_C": <number>, "P_bar": <number>,
        "total_flow_kg_hr": <number>,
        "composition": { "<compound>": <mole_frac>, ... } }
  connections    — list of [from_tag, to_tag] pairs
      RULE: connections must ALWAYS route through a named stream tag.
      Correct:   ["S-01", "MIX-101"] and ["MIX-101", "_AUTO_out"]
      Incorrect: ["MIX-101", "R-101"]  ← unit→unit not allowed
  unit_op_specs  — dict: { "<TAG>": { spec_key: value, ... } }
  notes          — string

Respond with a JSON block only (```json {...} ```).
No prose before or after the JSON block.
"""


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a markdown code block."""
    m = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    # Fallback: try to parse the whole response
    return json.loads(text.strip())


def build_messages(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    bfd_artifact: dict,
    feedback: str = "",
) -> list[dict]:
    chemical = brief_artifact.get("target_chemical", "")
    lib_data = _lib.lookup_process(chemical)
    lib_hint = ""
    if lib_data.get("found"):
        lib_hint = (
            f"\nLibrary reference for '{chemical}':\n"
            f"unit_operations: {lib_data.get('unit_operations')}\n"
            f"streams: {lib_data.get('streams')}\n"
            f"connections: {lib_data.get('connections')}\n"
            f"unit_op_specs: {lib_data.get('unit_op_specs', {})}"
        )

    content = (
        f"Process Brief: {brief_artifact}\n"
        f"Selected Route: {selected_route}\n"
        f"Thermo: {thermo_artifact}\n"
        f"Block Flow Diagram: {bfd_artifact}\n"
        f"{lib_hint}\n\n"
        f"{_PROMPT}"
    )
    if feedback:
        content += f"\n\nUser feedback for revision: {feedback}"
    return [{"role": "user", "content": content}]


def run_and_build(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    bfd_artifact: dict,
    output_dir: str | None = None,
    feedback: str = "",
) -> dict:
    """
    1. Ask Claude to produce the process_data dict.
    2. Call dwsim_tools.build_flowsheet_no_sim.
    3. Call dwsim_tools.export_flowsheet_image.
    4. Return a result dict with file paths and topology summary.
    """
    out_dir = output_dir or os.path.join(
        os.path.dirname(__file__), "..", "..", "outputs"
    )

    # Step 1: generate process_data via Claude
    messages = build_messages(
        brief_artifact, selected_route, thermo_artifact, bfd_artifact, feedback
    )
    raw = _cc.run(messages, max_tokens=8192)

    try:
        process_data = _extract_json(raw)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Could not parse Claude's process_data JSON: {exc}",
            "raw_response": raw,
        }

    # Step 2: build DWSIM flowsheet (no simulation)
    build_result = _dt.build_flowsheet_no_sim(process_data, output_dir=out_dir)
    if not build_result.get("success"):
        return {
            "success": False,
            "error": "DWSIM build_flowsheet_no_sim failed.",
            "build_result": build_result,
            "process_data": process_data,
        }

    # Step 3: export flowsheet image
    chemical_slug = (
        process_data.get("chemical", "process")
        .lower()
        .replace(" ", "_")
    )
    img_path = os.path.join(out_dir, f"{chemical_slug}_pfd.png")
    img_result = _dt.export_flowsheet_image(img_path)

    return {
        "success": True,
        "dwxmz_path": build_result.get("file_path"),
        "image_path": img_result.get("image_path"),
        "image_strategy": img_result.get("strategy"),
        "topology_summary": build_result.get("topology_summary"),
        "connections_wired": build_result.get("connections_wired"),
        "connections_failed": build_result.get("connections_failed", 0),
        "process_data": process_data,
        "connection_warning": build_result.get("connection_warning"),
    }


async def stream_generation(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    bfd_artifact: dict,
    feedback: str = "",
):
    """Stream the Claude generation of process_data (tokens only; no DWSIM call)."""
    messages = build_messages(
        brief_artifact, selected_route, thermo_artifact, bfd_artifact, feedback
    )
    async for chunk in _cc.stream(messages, max_tokens=8192):
        yield chunk
