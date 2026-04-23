"""
gating.py — Gate state machine for the 5-stage workflow.

A gate sits between every stage transition.  It checks whether the current
stage artifact has been approved before allowing the next stage to run.

Refinement loop:
  1. Stage produces artifact + summary.
  2. User reads summary → approves OR provides feedback.
  3. If feedback → stage re-runs with feedback appended to its prompt.
  4. Loop repeats up to MAX_REFINEMENTS times, then forces a decision.
  5. On approval → session advances to next stage.
"""
from __future__ import annotations

from typing import Any

MAX_REFINEMENTS = 5

STAGE_NAMES = {
    1: "Brief",
    2: "Routes",
    3: "Thermo",
    4: "Block Flow Diagram",
    5: "DWSIM PFD",
}


def gate_summary(stage: int, artifact: Any, summary: str) -> str:
    """
    Format the gate card shown to the user after a stage completes.

    Returns a plain-text message the frontend renders in the StageGate
    component.
    """
    name = STAGE_NAMES.get(stage, f"Stage {stage}")
    return (
        f"── Stage {stage}: {name} ──────────────────────\n"
        f"{summary}\n"
        f"─────────────────────────────────────────────\n"
        f"Does this look correct?\n"
        f"  • Reply 'approve' to proceed to the next stage.\n"
        f"  • Or describe what you'd like to change."
    )


def is_approved(stage_data: dict, stage: int) -> bool:
    """Return True if the given stage has been approved in session stage_data."""
    return stage_data.get(str(stage), {}).get("approved", False)


def refinement_count(stage_data: dict, stage: int) -> int:
    """Count how many refinement rounds have been done for a stage."""
    entry = stage_data.get(str(stage), {})
    # We track it by counting feedback history entries if stored,
    # otherwise treat any non-empty feedback as 1 refinement.
    history = entry.get("feedback_history", [])
    return len(history)


def build_refinement_messages(
    original_messages: list[dict],
    feedback: str,
    previous_response: str,
) -> list[dict]:
    """
    Append the user's feedback to the conversation so the stage re-runs
    with full context.
    """
    return original_messages + [
        {"role": "assistant", "content": previous_response},
        {
            "role": "user",
            "content": (
                f"Please revise the above based on this feedback:\n\n{feedback}\n\n"
                "Produce the updated artifact and summary in the same format as before."
            ),
        },
    ]


def check_gate(session: dict, stage: int) -> tuple[bool, str]:
    """
    Check whether a stage is gated (i.e. the previous stage must be approved).

    Returns (can_run: bool, reason: str).
    """
    if stage == 1:
        return True, "Stage 1 is always available."
    prev = stage - 1
    if is_approved(session.get("stage_data", {}), prev):
        return True, f"Stage {prev} approved."
    return (
        False,
        f"Stage {prev} ({STAGE_NAMES.get(prev, '?')}) must be approved "
        f"before running Stage {stage}.",
    )
