"""Stage 4 — Block Flow Diagram: numbered block-level process description."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import process_library as _lib
from api import claude_client as _cc

_PROMPT = """Based on the approved Brief, Route, and Thermo, describe the process as a
Block Flow Diagram (BFD).

The BFD is a numbered, plain-language description of each process block —
no DWSIM unit-op tags yet, just conceptual blocks.

Provide:
- blocks: list of objects, each with:
    number: int
    name: string (e.g. "Feed Compression", "Reactor", "Flash Separation")
    purpose: string (one sentence)
    inlet_streams: list of stream descriptions
    outlet_streams: list of stream descriptions
    key_conditions: string (T, P, key parameters)
- overall_flow: one paragraph describing the process from feed to product

Respond with a JSON block (```json {"blocks": [...], "overall_flow": "..."} ```)
then a plain-English 3–4 sentence summary of the process topology.
"""


def build_messages(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    feedback: str = "",
) -> list[dict]:
    chemical = brief_artifact.get("target_chemical", "")
    lib_data = _lib.lookup_process(chemical)
    lib_notes = lib_data.get("notes", "") if lib_data.get("found") else ""

    content = (
        f"Process Brief: {brief_artifact}\n"
        f"Selected Route: {selected_route}\n"
        f"Thermo: {thermo_artifact}\n"
        f"{'Library notes: ' + lib_notes if lib_notes else ''}\n\n"
        f"{_PROMPT}"
    )
    if feedback:
        content += f"\n\nUser feedback: {feedback}"
    return [{"role": "user", "content": content}]


def run(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    feedback: str = "",
) -> str:
    return _cc.run(build_messages(brief_artifact, selected_route, thermo_artifact, feedback))


async def stream(
    brief_artifact: dict,
    selected_route: dict,
    thermo_artifact: dict,
    feedback: str = "",
):
    async for chunk in _cc.stream(
        build_messages(brief_artifact, selected_route, thermo_artifact, feedback)
    ):
        yield chunk
