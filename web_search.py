"""
web_search.py — Web search fallback for chemicals not in the built-in library.

When a user requests a chemical that isn't in process_library.py, this module
searches the web for the standard industrial synthesis route and constructs
a process_library-compatible dict from the results.

This module is used by the MCP server — the actual web search is performed
via MCP tool calls (WebSearch/WebFetch) from the server layer, and the
results are parsed here into structured process data.

For offline / no-internet scenarios, it also provides a heuristic builder
that Claude can fill in using its own chemistry knowledge.
"""

from __future__ import annotations

import json
import re
from typing import Any


def build_process_from_description(
    chemical_name: str,
    route_name: str,
    description: str,
    reactions: list[dict],
    compounds: list[str],
    thermo_model: str,
    unit_operations: list[dict],
    streams: list[dict],
    connections: list[tuple[str, str]],
    notes: str = "",
) -> dict:
    """
    Build a process_library-compatible dict from structured data.

    This is the function Claude calls after gathering process info
    (either from web search results or its own chemistry knowledge).

    Args:
        chemical_name:   Target chemical (e.g. "Styrene")
        route_name:      Industrial route (e.g. "Ethylbenzene Dehydrogenation")
        description:     Paragraph describing the process
        reactions:       List of reaction dicts, each with keys:
                         equation, type, conversion (optional), temperature_C,
                         pressure_bar, catalyst
        compounds:       List of compound names (must match DWSIM database)
        thermo_model:    Thermodynamic model name (e.g. "Peng-Robinson", "NRTL")
        unit_operations: List of dicts with keys: type, name, purpose
        streams:         List of feed stream dicts with keys: name, type,
                         description, T_C, P_bar, total_flow_kg_hr, composition
        connections:     List of (from_tag, to_tag) tuples
        notes:           Additional process notes

    Returns:
        A dict matching the process_library.PROCESS_LIBRARY entry format.
    """
    return {
        "found": True,
        "chemical": chemical_name.lower().replace(" ", "_"),
        "name": f"{chemical_name} Production",
        "route": route_name,
        "description": description,
        "reactions": reactions,
        "compounds": compounds,
        "thermo_model": thermo_model,
        "unit_operations": unit_operations,
        "streams": streams,
        "connections": connections,
        "notes": notes,
        "source": "web_search_or_claude_knowledge",
    }


def parse_web_search_to_process(
    chemical_name: str,
    search_text: str,
) -> dict:
    """
    Parse raw web search text about a chemical process and extract
    structured process data.

    This is a best-effort parser — Claude should validate and correct
    the output before using it for simulation.

    Args:
        chemical_name: Target chemical
        search_text:   Raw text from web search results

    Returns:
        A partially-filled process dict. Claude should complete any
        missing fields before passing to DWSIM.
    """
    result: dict[str, Any] = {
        "found": True,
        "chemical": chemical_name.lower().replace(" ", "_"),
        "name": f"{chemical_name} Production",
        "route": "",
        "description": "",
        "reactions": [],
        "compounds": [],
        "thermo_model": "Peng-Robinson",  # safe default
        "unit_operations": [],
        "streams": [],
        "connections": [],
        "notes": "",
        "source": "web_search",
        "raw_search_text": search_text[:3000],  # keep for reference
        "needs_review": True,
    }

    # Try to extract temperature mentions (°C patterns)
    temp_matches = re.findall(r'(\d{2,4})\s*°?\s*C\b', search_text)
    if temp_matches:
        result["_extracted_temperatures_C"] = [int(t) for t in temp_matches[:5]]

    # Try to extract pressure mentions (bar/atm/MPa patterns)
    pressure_matches = re.findall(
        r'(\d+\.?\d*)\s*(bar|atm|MPa|kPa)', search_text, re.IGNORECASE
    )
    if pressure_matches:
        result["_extracted_pressures"] = [
            {"value": float(p[0]), "unit": p[1]} for p in pressure_matches[:5]
        ]

    # Try to extract catalyst mentions
    catalyst_patterns = [
        r'catalyst[:\s]+([A-Za-z0-9/\-\(\)\s,]+?)(?:\.|,|\n)',
        r'over\s+(?:a\s+)?([A-Za-z0-9/\-\(\)\s]+?)\s+catalyst',
        r'using\s+([A-Za-z0-9/\-\(\)\s]+?)\s+(?:as\s+)?catalyst',
    ]
    catalysts = []
    for pattern in catalyst_patterns:
        matches = re.findall(pattern, search_text, re.IGNORECASE)
        catalysts.extend([m.strip() for m in matches])
    if catalysts:
        result["_extracted_catalysts"] = catalysts[:5]

    # Try to extract conversion/yield mentions
    conv_matches = re.findall(
        r'(?:conversion|yield|selectivity)[:\s]+(\d+\.?\d*)\s*%',
        search_text, re.IGNORECASE
    )
    if conv_matches:
        result["_extracted_conversions_pct"] = [float(c) for c in conv_matches[:5]]

    return result


# ─────────────────────────────────────────────
# Thermo model recommendation heuristic
# ─────────────────────────────────────────────

def recommend_thermo_model(compounds: list[str], pressure_bar: float = 1.0) -> str:
    """
    Recommend a thermodynamic model based on the compounds and pressure.

    Heuristic rules:
    - Water + organics → NRTL (polar/non-ideal liquid)
    - Only hydrocarbons, high pressure → Peng-Robinson
    - Only gases (H2, N2, O2, CO, CH4) → Peng-Robinson or SRK
    - Electrolytes / acids → NRTL or UNIQUAC
    - Steam/water only → Steam Tables
    """
    lower_compounds = [c.lower() for c in compounds]

    has_water = "water" in lower_compounds
    has_organics = any(c in lower_compounds for c in [
        "ethanol", "methanol", "acetone", "acetic acid", "phenol",
        "isopropanol", "butanol", "glycol", "ethylene glycol",
    ])
    all_hydrocarbons = all(c in lower_compounds for c in lower_compounds) and all(
        any(kw in c for kw in ["ane", "ene", "yne", "benzene", "toluene", "xylene",
                                "hexane", "pentane", "butane", "propane", "methane",
                                "ethane", "naphthalene"])
        for c in lower_compounds
    )
    only_water = lower_compounds == ["water"]
    has_acid = any("acid" in c for c in lower_compounds)

    if only_water:
        return "Steam Tables"
    if has_water and has_organics:
        return "NRTL"
    if has_acid:
        return "NRTL"
    if has_water and has_organics:
        return "UNIQUAC"
    if all_hydrocarbons or pressure_bar > 10:
        return "Peng-Robinson"

    return "Peng-Robinson"  # safe default


# ─────────────────────────────────────────────
# Template for Claude to fill in
# ─────────────────────────────────────────────

EMPTY_PROCESS_TEMPLATE = {
    "chemical": "",
    "name": "",
    "route": "",
    "description": "",
    "reactions": [
        {
            "equation": "",
            "type": "ConversionReactor",  # or EquilibriumReactor
            "conversion": 0.0,
            "temperature_C": 0,
            "pressure_bar": 0,
            "catalyst": "",
        }
    ],
    "compounds": [],
    "thermo_model": "",
    "unit_operations": [
        {"type": "", "name": "", "purpose": ""},
    ],
    "streams": [
        {
            "name": "S-01",
            "type": "material",
            "description": "",
            "T_C": 25,
            "P_bar": 1.0,
            "total_flow_kg_hr": 100,
            "composition": {},
        }
    ],
    "connections": [],
    "notes": "",
}


def get_empty_template() -> dict:
    """Return a blank process template for Claude to fill in."""
    import copy
    return copy.deepcopy(EMPTY_PROCESS_TEMPLATE)
