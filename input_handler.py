"""
input_handler.py — Parse natural language process descriptions into structured data.

Handles user inputs like:
  - "produce ethanol at 500 kg/hr from 70% ethylene feed at 300°C and 70 bar"
  - "design ammonia plant with 1000 tonnes/day capacity"
  - "methanol from syngas, 80 bar, 250°C, Cu/ZnO catalyst"

Uses regex patterns to extract:
  - Target chemical
  - Production rate (with unit conversion)
  - Feed conditions (T, P, composition)
  - Catalyst mentions
  - Special requirements
"""

from __future__ import annotations

import re
from typing import Any

import process_library as _lib


# ─────────────────────────────────────────────
# 1. Unit conversions
# ─────────────────────────────────────────────

def _to_kg_per_hr(value: float, unit: str) -> float:
    """Convert a flow rate to kg/hr."""
    unit = unit.lower().strip()
    conversions = {
        "kg/hr": 1.0,
        "kg/h": 1.0,
        "kg/s": 3600.0,
        "kg/min": 60.0,
        "kg/day": 1.0 / 24.0,
        "t/hr": 1000.0,
        "t/h": 1000.0,
        "tonne/hr": 1000.0,
        "tonnes/hr": 1000.0,
        "t/day": 1000.0 / 24.0,
        "tonne/day": 1000.0 / 24.0,
        "tonnes/day": 1000.0 / 24.0,
        "tpd": 1000.0 / 24.0,
        "t/year": 1000.0 / (24.0 * 365),
        "tpa": 1000.0 / (24.0 * 365),
        "tonnes/year": 1000.0 / (24.0 * 365),
        "ton/day": 907.185 / 24.0,  # short ton
        "lb/hr": 0.453592,
        "lb/h": 0.453592,
        "g/s": 3.6,
        "g/hr": 0.001,
        "mol/s": None,  # need MW
        "kmol/hr": None,
    }
    factor = conversions.get(unit)
    if factor is None:
        return value  # assume kg/hr
    return value * factor


def _to_kelvin(value: float, unit: str) -> float:
    """Convert temperature to Kelvin."""
    unit = unit.lower().strip().rstrip(".")
    if unit in ("c", "°c", "celsius", "deg c", "degc"):
        return value + 273.15
    if unit in ("f", "°f", "fahrenheit", "deg f", "degf"):
        return (value - 32) * 5 / 9 + 273.15
    if unit in ("k", "kelvin"):
        return value
    return value + 273.15  # default assume Celsius


def _to_pascal(value: float, unit: str) -> float:
    """Convert pressure to Pascal."""
    unit = unit.lower().strip()
    conversions = {
        "pa": 1.0,
        "kpa": 1e3,
        "mpa": 1e6,
        "bar": 1e5,
        "barg": 1e5,  # gauge ≈ absolute for simplicity
        "atm": 101325.0,
        "psi": 6894.76,
        "psig": 6894.76,
        "psia": 6894.76,
        "mmhg": 133.322,
        "torr": 133.322,
    }
    factor = conversions.get(unit, 1e5)  # default bar
    return value * factor


# ─────────────────────────────────────────────
# 2. Pattern extraction
# ─────────────────────────────────────────────

# Regex patterns for extracting process parameters
_FLOW_PATTERN = re.compile(
    r'(\d+[\d,]*\.?\d*)\s*'
    r'(kg/hr?|kg/s|kg/min|kg/day|'
    r't/hr?|tonne[s]?/hr?|t/day|tonne[s]?/day|tpd|'
    r't/year|tpa|tonne[s]?/year|'
    r'ton/day|lb/hr?|g/s|g/hr|kmol/hr|mol/s)',
    re.IGNORECASE
)

_TEMP_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*°?\s*(C|F|K|celsius|fahrenheit|kelvin|deg\s*[CFK])',
    re.IGNORECASE
)

_PRESSURE_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(bar[g]?|atm|MPa|kPa|Pa|psi[ag]?|mmHg|torr)',
    re.IGNORECASE
)

_COMPOSITION_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*%\s*(\w[\w\s]*?)(?:\s+feed|\s+in|\s*,|\s*and\s|\s*\+|\s*$)',
    re.IGNORECASE
)

_CATALYST_PATTERN = re.compile(
    r'(?:catalyst|cat\.?|over)\s*[:\s]*([A-Za-z0-9/\-\(\)\s]+?)(?:\.|,|$)',
    re.IGNORECASE
)


def parse_user_input(text: str) -> dict:
    """
    Parse a natural language process description into structured parameters.

    Args:
        text: User's natural language input describing the desired process.

    Returns:
        dict with extracted parameters:
        - chemical: identified target chemical
        - production_rate_kg_hr: converted to kg/hr
        - feed_conditions: T, P, composition
        - catalyst: if mentioned
        - in_library: whether the chemical is in process_library
        - library_data: the library entry if found
        - raw_input: the original text
    """
    result: dict[str, Any] = {
        "raw_input": text,
        "chemical": None,
        "production_rate_kg_hr": None,
        "feed_temperature_K": None,
        "feed_pressure_Pa": None,
        "feed_composition": {},
        "catalyst": None,
        "in_library": False,
        "library_data": None,
        "extraction_notes": [],
    }

    # ─── Identify the chemical ───
    chemical = _identify_chemical(text)
    if chemical:
        result["chemical"] = chemical
        lib_result = _lib.lookup_process(chemical)
        if lib_result.get("found"):
            result["in_library"] = True
            result["library_data"] = lib_result
            result["extraction_notes"].append(
                f"Found '{chemical}' in built-in library: {lib_result['name']}"
            )
        else:
            result["extraction_notes"].append(
                f"'{chemical}' not in built-in library. "
                "Will need web search or manual process definition."
            )

    # ─── Extract flow rate ───
    flow_match = _FLOW_PATTERN.search(text)
    if flow_match:
        value = float(flow_match.group(1).replace(",", ""))
        unit = flow_match.group(2)
        kg_hr = _to_kg_per_hr(value, unit)
        result["production_rate_kg_hr"] = kg_hr
        result["extraction_notes"].append(
            f"Production rate: {value} {unit} → {kg_hr:.1f} kg/hr"
        )

    # ─── Extract temperature ───
    temp_match = _TEMP_PATTERN.search(text)
    if temp_match:
        value = float(temp_match.group(1))
        unit = temp_match.group(2)
        t_k = _to_kelvin(value, unit)
        result["feed_temperature_K"] = t_k
        result["extraction_notes"].append(
            f"Temperature: {value} {unit} → {t_k:.1f} K"
        )

    # ─── Extract pressure ───
    pres_match = _PRESSURE_PATTERN.search(text)
    if pres_match:
        value = float(pres_match.group(1))
        unit = pres_match.group(2)
        p_pa = _to_pascal(value, unit)
        result["feed_pressure_Pa"] = p_pa
        result["extraction_notes"].append(
            f"Pressure: {value} {unit} → {p_pa:.0f} Pa ({p_pa/1e5:.1f} bar)"
        )

    # ─── Extract composition ───
    comp_matches = _COMPOSITION_PATTERN.findall(text)
    for pct_str, compound_name in comp_matches:
        pct = float(pct_str)
        name = compound_name.strip()
        result["feed_composition"][name] = pct / 100.0
        result["extraction_notes"].append(
            f"Composition: {name} = {pct}%"
        )

    # ─── Extract catalyst ───
    cat_match = _CATALYST_PATTERN.search(text)
    if cat_match:
        result["catalyst"] = cat_match.group(1).strip()
        result["extraction_notes"].append(
            f"Catalyst: {result['catalyst']}"
        )

    return result


# ─────────────────────────────────────────────
# 3. Chemical identification
# ─────────────────────────────────────────────

# Common chemical names, formulas, and abbreviations
_CHEMICAL_KEYWORDS: list[tuple[list[str], str]] = [
    (["ethanol", "etoh", "ethyl alcohol", "c2h5oh"], "ethanol"),
    (["methanol", "meoh", "methyl alcohol", "ch3oh", "wood alcohol"], "methanol"),
    (["ammonia", "nh3"], "ammonia"),
    (["acetic acid", "acoh", "hoac", "ch3cooh", "vinegar"], "acetic_acid"),
    (["benzene", "c6h6"], "benzene"),
    (["ethylene oxide", "eo", "c2h4o", "oxirane"], "ethylene_oxide"),
    (["sulphuric acid", "sulfuric acid", "h2so4"], "sulphuric_acid"),
    (["urea", "co(nh2)2", "carbamide"], "urea"),
    (["acetone", "propanone", "ch3coch3", "(ch3)2co"], "acetone"),
    (["hydrogen", "h2"], "hydrogen"),
    # Additional chemicals not in the library but commonly requested
    (["ethylene", "c2h4", "ethene"], "ethylene"),
    (["propylene", "c3h6", "propene"], "propylene"),
    (["styrene", "c6h5ch=ch2", "vinylbenzene"], "styrene"),
    (["formaldehyde", "hcho", "methanal"], "formaldehyde"),
    (["nitric acid", "hno3"], "nitric_acid"),
    (["phosphoric acid", "h3po4"], "phosphoric_acid"),
    (["polyethylene", "pe", "hdpe", "ldpe"], "polyethylene"),
    (["polypropylene", "pp"], "polypropylene"),
    (["pvc", "polyvinyl chloride", "vinyl chloride"], "vinyl_chloride"),
    (["ethylene glycol", "meg", "eg", "monoethylene glycol"], "ethylene_glycol"),
    (["acrylic acid", "ch2chcooh"], "acrylic_acid"),
    (["butadiene", "c4h6", "1,3-butadiene"], "butadiene"),
    (["chlorine", "cl2"], "chlorine"),
    (["sodium hydroxide", "naoh", "caustic soda"], "sodium_hydroxide"),
    (["toluene", "c7h8", "methylbenzene"], "toluene"),
    (["xylene", "xylenes", "c8h10"], "xylene"),
    (["cumene", "isopropylbenzene"], "cumene"),
    (["phenol", "c6h5oh", "carbolic acid"], "phenol"),
    (["aniline", "c6h5nh2", "aminobenzene"], "aniline"),
    (["dimethyl ether", "dme", "ch3och3"], "dimethyl_ether"),
]


def _identify_chemical(text: str) -> str | None:
    """
    Identify the target chemical from natural language text.

    Returns the chemical key (e.g. "ethanol") or None if not identified.
    """
    lower = text.lower()

    # Look for explicit "produce X" / "make X" / "design X plant" patterns
    produce_patterns = [
        r'(?:produce|make|manufacture|synthesize|design|build|create)\s+(?:a\s+)?(?:plant\s+(?:for|to\s+produce)\s+)?(\w[\w\s]*?)(?:\s+plant|\s+at\s|\s+with|\s+from|\s*,|\s*$)',
        r'(\w[\w\s]*?)\s+(?:plant|production|process|facility|synthesis)',
        r'(?:plant|production|process)\s+(?:for|of)\s+(\w[\w\s]*?)(?:\s+at|\s+with|\s*,|\s*$)',
    ]

    for pattern in produce_patterns:
        match = re.search(pattern, lower)
        if match:
            candidate = match.group(1).strip()
            found = _match_chemical(candidate)
            if found:
                return found

    # Fallback: check if any known chemical name appears in the text
    for keywords, chem_key in _CHEMICAL_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return chem_key

    return None


def _match_chemical(candidate: str) -> str | None:
    """Match a candidate string to a known chemical."""
    candidate = candidate.lower().strip()
    for keywords, chem_key in _CHEMICAL_KEYWORDS:
        for kw in keywords:
            if kw == candidate or kw in candidate or candidate in kw:
                return chem_key
    return None


# ─────────────────────────────────────────────
# 4. Merge user overrides with library defaults
# ─────────────────────────────────────────────

def merge_with_library(parsed_input: dict) -> dict:
    """
    Merge user-specified parameters with library defaults.

    If the chemical is in the library, start with library data and override
    with any user-specified values (flow rate, T, P, composition).

    Returns a process_library-format dict ready for simulation.
    """
    if not parsed_input.get("in_library") or not parsed_input.get("library_data"):
        return {
            "found": False,
            "chemical": parsed_input.get("chemical", "unknown"),
            "message": "Chemical not in library. Use web search or manual specification.",
            "parsed_input": parsed_input,
        }

    process = dict(parsed_input["library_data"])

    # Override production rate → scale all feed streams proportionally
    user_rate = parsed_input.get("production_rate_kg_hr")
    if user_rate and process.get("streams"):
        # Calculate current total feed flow
        current_total = sum(
            s.get("total_flow_kg_hr", 100) for s in process["streams"]
        )
        if current_total > 0:
            scale_factor = user_rate / current_total
            for s in process["streams"]:
                s["total_flow_kg_hr"] = s.get("total_flow_kg_hr", 100) * scale_factor

    # Override feed temperature if specified
    user_temp = parsed_input.get("feed_temperature_K")
    if user_temp and process.get("streams"):
        for s in process["streams"]:
            s["T_C"] = user_temp - 273.15

    # Override feed pressure if specified
    user_pres = parsed_input.get("feed_pressure_Pa")
    if user_pres and process.get("streams"):
        for s in process["streams"]:
            s["P_bar"] = user_pres / 1e5

    # Override composition if specified
    user_comp = parsed_input.get("feed_composition")
    if user_comp and process.get("streams"):
        # Apply to first feed stream
        process["streams"][0]["composition"] = user_comp

    process["user_overrides"] = {
        k: v for k, v in {
            "production_rate_kg_hr": user_rate,
            "feed_temperature_K": user_temp,
            "feed_pressure_Pa": user_pres,
            "feed_composition": user_comp or None,
            "catalyst": parsed_input.get("catalyst"),
        }.items() if v is not None
    }

    return process
