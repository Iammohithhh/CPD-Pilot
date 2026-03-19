"""
pfd_parser.py — Parse PFD images uploaded by the user.

When a user uploads a Process Flow Diagram image, this module provides
structured prompts and parsing logic so Claude (which is multimodal)
can extract unit operations, streams, and connections from the image.

Strategy:
  Claude is a vision model — it can SEE the PFD image directly.
  This module provides:
    1. A structured prompt template that tells Claude exactly what to extract
    2. Validation functions to check the extracted data
    3. Conversion to process_library-compatible format

The MCP server reads the image file (via the Read tool which handles images)
and then uses these functions to structure the extracted information.
"""

from __future__ import annotations

import json
import os
from typing import Any


# ─────────────────────────────────────────────
# 1. Prompt template for Claude vision
# ─────────────────────────────────────────────

PFD_EXTRACTION_PROMPT = """You are looking at a Process Flow Diagram (PFD) for a chemical process.

Extract ALL of the following information from this diagram and return it as a JSON object:

{
  "process_name": "Name of the process (if visible)",
  "chemical_product": "Main product chemical",

  "unit_operations": [
    {
      "tag": "Equipment tag (e.g. R-101, T-101, H-101)",
      "type": "One of: Mixer, Splitter, Heater, Cooler, HeatExchanger, Valve, Pump, Compressor, Expander, Pipe, Flash, Vessel, Tank, ShortcutColumn, DistillationColumn, AbsorptionColumn, ConversionReactor, EquilibriumReactor, GibbsReactor, CSTR, PFR, ComponentSeparator",
      "name_or_label": "Any label/name shown on the diagram",
      "purpose": "What this equipment does in the process"
    }
  ],

  "streams": [
    {
      "tag": "Stream number or tag (e.g. S-01, 1, FEED)",
      "type": "material or energy",
      "from_unit": "Source equipment tag or FEED if external feed",
      "to_unit": "Destination equipment tag or PRODUCT if leaving system",
      "description": "What this stream contains",
      "conditions": {
        "T_C": null,
        "P_bar": null,
        "flow_kg_hr": null,
        "composition": {}
      }
    }
  ],

  "connections": [
    ["from_tag", "to_tag"]
  ],

  "compounds_visible": ["List of chemical names/formulas visible on the diagram"],

  "operating_conditions": {
    "temperatures_C": [],
    "pressures_bar": [],
    "notes": ""
  },

  "additional_notes": "Any other relevant information from the diagram"
}

IMPORTANT:
- Extract EVERY piece of equipment you can see, even if the tag is not fully readable
- Follow stream arrows to determine connections
- If conditions (T, P, flow) are written on streams, include them
- If composition tables are shown, extract them
- Use your best judgment for equipment types based on their shape/symbol
- Standard PFD symbols: circles = pumps/compressors, rectangles = vessels/columns,
  triangles/trapezoids = heaters/coolers, cylinders = tanks

Return ONLY the JSON object, no other text.
"""


def get_extraction_prompt() -> str:
    """Return the PFD extraction prompt for Claude vision."""
    return PFD_EXTRACTION_PROMPT


# ─────────────────────────────────────────────
# 2. Validate and clean extracted PFD data
# ─────────────────────────────────────────────

# Valid unit operation types that map to DWSIM ObjectType
VALID_UNIT_TYPES = {
    "Mixer", "Splitter", "Heater", "Cooler", "HeatExchanger",
    "Valve", "Pump", "Compressor", "Expander", "Pipe",
    "Flash", "Vessel", "Tank", "ShortcutColumn", "DistillationColumn",
    "AbsorptionColumn", "ConversionReactor", "EquilibriumReactor",
    "GibbsReactor", "CSTR", "PFR", "ComponentSeparator",
    "Filter",
}

# Common PFD symbol → type mapping (fuzzy matching)
SYMBOL_ALIASES = {
    "reactor": "ConversionReactor",
    "heat exchanger": "HeatExchanger",
    "exchanger": "HeatExchanger",
    "column": "DistillationColumn",
    "tower": "DistillationColumn",
    "distillation": "DistillationColumn",
    "absorber": "AbsorptionColumn",
    "stripper": "AbsorptionColumn",
    "separator": "Flash",
    "flash drum": "Flash",
    "flash": "Flash",
    "drum": "Flash",
    "pump": "Pump",
    "compressor": "Compressor",
    "turbine": "Expander",
    "expander": "Expander",
    "heater": "Heater",
    "furnace": "Heater",
    "fired heater": "Heater",
    "cooler": "Cooler",
    "condenser": "Cooler",
    "reboiler": "Heater",
    "valve": "Valve",
    "mixer": "Mixer",
    "splitter": "Splitter",
    "tee": "Splitter",
    "tank": "Tank",
    "storage": "Tank",
    "filter": "Filter",
    "pfr": "PFR",
    "plug flow": "PFR",
    "cstr": "CSTR",
    "stirred tank": "CSTR",
}


def normalize_unit_type(raw_type: str) -> str:
    """
    Normalize a unit operation type string to a valid DWSIM type.
    Handles common aliases and fuzzy matching.
    """
    if raw_type in VALID_UNIT_TYPES:
        return raw_type

    lower = raw_type.lower().strip()
    if lower in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[lower]

    # Partial match
    for alias, valid_type in SYMBOL_ALIASES.items():
        if alias in lower or lower in alias:
            return valid_type

    return raw_type  # return as-is, let downstream handle


def validate_extracted_pfd(data: dict) -> dict:
    """
    Validate and clean PFD data extracted by Claude vision.

    Returns a dict with:
      - valid: bool
      - warnings: list of issues found
      - cleaned_data: the cleaned version
    """
    warnings: list[str] = []
    cleaned = dict(data)

    # Check unit operations
    if "unit_operations" not in cleaned or not cleaned["unit_operations"]:
        warnings.append("No unit operations found in the PFD.")
        cleaned["unit_operations"] = []
    else:
        for i, op in enumerate(cleaned["unit_operations"]):
            if "type" in op:
                original = op["type"]
                op["type"] = normalize_unit_type(original)
                if op["type"] not in VALID_UNIT_TYPES:
                    warnings.append(
                        f"Unit op #{i} ({op.get('tag', '?')}): type '{original}' "
                        f"could not be mapped to a valid DWSIM type."
                    )
            else:
                warnings.append(f"Unit op #{i}: missing 'type' field.")

            if "tag" not in op or not op["tag"]:
                op["tag"] = f"UNIT-{i+1:03d}"
                warnings.append(f"Unit op #{i}: missing tag, assigned '{op['tag']}'.")

    # Check streams
    if "streams" not in cleaned or not cleaned["streams"]:
        warnings.append("No streams found in the PFD.")
        cleaned["streams"] = []
    else:
        for i, stream in enumerate(cleaned["streams"]):
            if "tag" not in stream or not stream["tag"]:
                stream["tag"] = f"S-{i+1:02d}"
                warnings.append(f"Stream #{i}: missing tag, assigned '{stream['tag']}'.")
            if "type" not in stream:
                stream["type"] = "material"

    # Check connections
    if "connections" not in cleaned or not cleaned["connections"]:
        # Try to infer from streams
        inferred = []
        for stream in cleaned.get("streams", []):
            from_u = stream.get("from_unit")
            to_u = stream.get("to_unit")
            if from_u and to_u and from_u != "FEED" and to_u != "PRODUCT":
                inferred.append([from_u, to_u])
        if inferred:
            cleaned["connections"] = inferred
            warnings.append(f"Connections inferred from stream data ({len(inferred)} found).")
        else:
            warnings.append("No connections found or inferred.")

    return {
        "valid": len([w for w in warnings if "missing" not in w.lower()]) == 0,
        "warnings": warnings,
        "cleaned_data": cleaned,
    }


# ─────────────────────────────────────────────
# 3. Convert extracted PFD to process_library format
# ─────────────────────────────────────────────

def pfd_to_process_dict(
    extracted_data: dict,
    chemical_name: str = "",
    thermo_model: str = "Peng-Robinson",
) -> dict:
    """
    Convert validated PFD extraction data into a process_library-compatible dict.

    Args:
        extracted_data: Output from validate_extracted_pfd()["cleaned_data"]
        chemical_name:  Target chemical name
        thermo_model:   Thermodynamic model to use

    Returns:
        process_library-format dict ready for DWSIM simulation
    """
    unit_ops = []
    for op in extracted_data.get("unit_operations", []):
        unit_ops.append({
            "type": op.get("type", "Vessel"),
            "name": op.get("tag", "UNIT"),
            "purpose": op.get("purpose", op.get("name_or_label", "")),
        })

    streams = []
    for s in extracted_data.get("streams", []):
        conditions = s.get("conditions", {})
        comp = conditions.get("composition", {})
        streams.append({
            "name": s.get("tag", "S-01"),
            "type": s.get("type", "material"),
            "description": s.get("description", ""),
            "T_C": conditions.get("T_C", 25) or 25,
            "P_bar": conditions.get("P_bar", 1.0) or 1.0,
            "total_flow_kg_hr": conditions.get("flow_kg_hr", 100) or 100,
            "composition": comp if comp else {},
        })

    connections = []
    for conn in extracted_data.get("connections", []):
        if isinstance(conn, (list, tuple)) and len(conn) == 2:
            connections.append(tuple(conn))

    compounds = extracted_data.get("compounds_visible", [])

    return {
        "found": True,
        "chemical": chemical_name.lower().replace(" ", "_") if chemical_name else "unknown",
        "name": extracted_data.get("process_name", f"{chemical_name} Production"),
        "route": "Extracted from PFD",
        "description": extracted_data.get("additional_notes", "Process extracted from user-provided PFD image."),
        "reactions": [],  # Claude should fill in reaction details
        "compounds": compounds,
        "thermo_model": thermo_model,
        "unit_operations": unit_ops,
        "streams": streams,
        "connections": connections,
        "notes": "This process was extracted from a PFD image. Reaction details and some stream conditions may need manual specification.",
        "source": "pfd_image",
    }
