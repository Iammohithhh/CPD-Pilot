"""Stage 2 — Routes: present 2-3 chemistry routes, user picks one."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import process_library as _lib
import web_search as _ws
from api import claude_client as _cc

_PROMPT = """Based on the approved Process Brief, identify 2–3 industrial synthesis routes
for the target chemical.

For each route provide:
- route_name: string
- description: 1–2 sentences
- key_reaction: balanced equation + T (°C) + P (bar) + catalyst
- single_pass_conversion: percentage
- pros: list of 2–3 advantages
- cons: list of 2–3 disadvantages
- recommended: bool (mark the best route True)

Respond with a JSON block (```json {"routes": [...]} ```) followed by a 2–3 sentence
summary explaining your recommendation.

At the end add: "Which route would you like to proceed with?"
"""


def _library_context(chemical: str) -> str:
    data = _lib.lookup_process(chemical)
    if data.get("found"):
        return (
            f"Library data for '{chemical}':\n"
            f"Route: {data.get('route')}\n"
            f"Reactions: {data.get('reactions')}\n"
            f"Notes: {data.get('notes', '')}"
        )
    return ""


def build_messages(brief_artifact: dict, feedback: str = "") -> list[dict]:
    chemical = brief_artifact.get("target_chemical", "")
    lib_ctx = _library_context(chemical)

    content = (
        f"Approved Process Brief:\n{brief_artifact}\n\n"
        f"{lib_ctx}\n\n"
        f"{_PROMPT}"
    )
    if feedback:
        content += f"\n\nUser feedback: {feedback}"
    return [{"role": "user", "content": content}]


def run(brief_artifact: dict, feedback: str = "") -> str:
    return _cc.run(build_messages(brief_artifact, feedback))


async def stream(brief_artifact: dict, feedback: str = ""):
    async for chunk in _cc.stream(build_messages(brief_artifact, feedback)):
        yield chunk
