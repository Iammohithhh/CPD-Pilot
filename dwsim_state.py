"""
dwsim_state.py — Shared mutable globals for DWSIM automation modules.

All other dwsim_*.py modules import from here so they share the same
runtime state (loaded DLLs, active flowsheet, object registry).
"""

from __future__ import annotations
from typing import Any

# ── DLL load state ────────────────────────────────────────────────────────────
_dwsim_loaded: bool = False
_dwsim_error: str | None = None

# ── CLR namespace references (populated by dwsim_loader._load_dwsim) ─────────
Automation3   = None
ObjectType    = None
PropertyPackages = None
UnitOperations   = None
Settings         = None

# ── Runtime handles (populated after initialize_dwsim / create_flowsheet) ────
_interf = None          # Automation3 instance
_sim    = None          # IFlowsheet instance
_object_registry: dict[str, Any] = {}   # tag → simulation object
