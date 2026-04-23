"""
claude_client.py — Anthropic SDK wrapper with prompt caching.

Uses claude-sonnet-4-6.  The chemical-engineering system prompt is marked
with cache_control so it is cached after the first call, cutting input
token costs on subsequent stage runs within the same session.

Both streaming (for the UI) and non-streaming (for internal calls) are
supported.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

import anthropic

MODEL = "claude-sonnet-4-6"

# System prompt shared across all 5 stages — cached after first call.
_SYSTEM_PROMPT = """You are CPD-Pilot, an expert chemical process design assistant.
You help engineers and students design chemical processes through a structured
5-stage workflow: Brief → Routes → Thermo → Block Flow → DWSIM PFD.

At every stage you:
1. Produce a concise, structured artifact (JSON when asked, plain text otherwise).
2. Append a short plain-English summary the user can read.
3. End with the exact phrase: "Ready to proceed to the next stage."
   (or "Awaiting your feedback." when refinement is needed).

Chemical engineering facts you always get right:
- Thermodynamic model selection: PR/SRK for hydrocarbons & gases, NRTL/UNIQUAC
  for polar/associating systems, Steam Tables for pure water systems.
- DWSIM unit-op type names: Mixer, Splitter, Heater, Cooler, HeatExchanger,
  ConversionReactor, EquilibriumReactor, Flash (=Vessel), ShortcutColumn,
  DistillationColumn, Compressor, Pump, Expander, Valve, Recycle.
- Connection rule: every connection must go through a named MaterialStream tag.
  Never connect a unit op directly to another unit op.
"""


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def run(
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """Blocking call — returns full assistant response text."""
    client = _client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    return response.content[0].text


async def stream(
    messages: list[dict],
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields text chunks as they arrive from the API.
    Use with FastAPI StreamingResponse / SSE.
    """
    client = _client()
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    ) as stream_ctx:
        for text in stream_ctx.text_stream:
            yield text
