"""Stage 1 — Brief: parse user request into a structured process spec."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import input_handler as _inp
from api import claude_client as _cc

_PROMPT = """The user has described a chemical process they want to design.

Parse their request and produce a structured **Process Brief** with:
- target_chemical: string
- production_rate_kg_hr: number
- feed_description: string (what feeds are available)
- purity_target: string (product purity requirement, if stated)
- constraints: list of strings (pressure limits, temperature limits, budget, etc.)
- additional_notes: any other context

Respond with a JSON block (```json ... ```) followed by a 2–3 sentence plain-English summary.
"""


def build_messages(user_input: str, feedback: str = "") -> list[dict]:
    content = f"User request:\n\n{user_input}"
    if feedback:
        content += f"\n\nPrevious feedback to incorporate: {feedback}"
    return [
        {"role": "user", "content": f"{_PROMPT}\n\n{content}"},
    ]


def run(user_input: str, feedback: str = "") -> str:
    """Run Stage 1 (blocking). Returns raw Claude response text."""
    # Also try the structured parser for a head start
    try:
        parsed = _inp.parse_user_input(user_input)
        merged = _inp.merge_with_library(parsed)
        context = (
            f"Structured parse result (use as context, override with user's words):\n"
            f"chemical={parsed.get('chemical')}, "
            f"rate={parsed.get('production_rate_kg_hr')} kg/hr, "
            f"in_library={merged.get('in_library')}"
        )
    except Exception:
        context = ""

    messages = build_messages(
        f"{context}\n\n{user_input}" if context else user_input,
        feedback=feedback,
    )
    return _cc.run(messages)


async def stream(user_input: str, feedback: str = ""):
    """Stream Stage 1 response tokens."""
    messages = build_messages(user_input, feedback=feedback)
    async for chunk in _cc.stream(messages):
        yield chunk
