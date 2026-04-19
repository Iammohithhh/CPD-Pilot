"""Stage 3 — Thermo: confirm compound list and property package."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import process_library as _lib
from api import claude_client as _cc

_PROMPT = """Based on the approved Process Brief and selected Route, define the thermodynamic
model for this simulation.

Provide:
- compounds: list of compound names exactly as they appear in the DWSIM database
  (e.g. "Carbon Monoxide", not "CO")
- thermo_model: one of "Peng-Robinson", "SRK", "NRTL", "UNIQUAC", "UNIFAC",
  "Steam Tables", "CoolProp", "PRSV2"
- justification: 2–3 sentences explaining WHY this model was chosen
  (polarity, association, pressure range, etc.)
- warnings: list of any compound availability or model-fit concerns

Respond with a JSON block (```json {...} ```) then a plain-English summary.
"""


def build_messages(
    brief_artifact: dict,
    selected_route: dict,
    feedback: str = "",
) -> list[dict]:
    chemical = brief_artifact.get("target_chemical", "")
    lib_data = _lib.lookup_process(chemical)
    lib_compounds = lib_data.get("compounds", []) if lib_data.get("found") else []
    lib_thermo = lib_data.get("thermo_model", "") if lib_data.get("found") else ""

    hint = ""
    if lib_compounds:
        hint = (
            f"\nLibrary hint — compounds: {lib_compounds}, "
            f"recommended thermo: {lib_thermo}"
        )

    content = (
        f"Process Brief: {brief_artifact}\n"
        f"Selected Route: {selected_route}\n"
        f"{hint}\n\n"
        f"{_PROMPT}"
    )
    if feedback:
        content += f"\n\nUser feedback: {feedback}"
    return [{"role": "user", "content": content}]


def run(brief_artifact: dict, selected_route: dict, feedback: str = "") -> str:
    return _cc.run(build_messages(brief_artifact, selected_route, feedback))


async def stream(brief_artifact: dict, selected_route: dict, feedback: str = ""):
    async for chunk in _cc.stream(
        build_messages(brief_artifact, selected_route, feedback)
    ):
        yield chunk
