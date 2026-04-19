"""
server.py — MCP server for Chemical Process Design (CPD) Pilot (v1 — 5-stage workflow).

Exposes the following tools to Claude:

  PROCESS LIBRARY:
    • lookup_chemical_process    — get blueprint for a named chemical
    • list_available_processes   — list all chemicals in the library
    • get_process_summary        — human-readable summary card

  INPUT HANDLING:
    • parse_process_request      — parse natural language descriptions

  WEB SEARCH (for chemicals not in library):
    • search_chemical_process    — search web for industrial process info
    • build_custom_process       — build process dict from Claude's knowledge

  DWSIM (requires DWSIM installation):
    • dwsim_status               — check if DWSIM is available
    • create_flowsheet           — create flowsheet with compounds + thermo model
    • add_unit_operation         — add a single unit operation
    • set_stream_conditions      — set T / P / flow / composition on a stream
    • connect_objects            — connect two simulation objects
    • run_simulation             — solve the flowsheet
    • get_stream_results         — read T, P, flow, composition from streams
    • get_unit_op_results        — read duty, ΔP etc. from unit operations
    • save_flowsheet             — save to .dwxmz file
    • build_process_from_library — one-shot: build topology + save from library
    • export_flowsheet_image     — export DWSIM flowsheet as PNG / SVG

Usage:
    python server.py                  (stdio — for Claude Desktop / Claude Code)
    mcp dev server.py                 (dev mode with MCP Inspector)
"""

from __future__ import annotations
import sys
import json
import os
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

import process_library as _lib
import dwsim_tools as _dwsim
import web_search as _ws
import input_handler as _inp

# ─────────────────────────────────────────────
# Create MCP server instance
# ─────────────────────────────────────────────

mcp = FastMCP(
    "CPD-Pilot",
    instructions=(
        "You are a Chemical Process Design assistant. "
        "Guide the user through the 5-stage design workflow. "
        "After EACH stage, present a summary and ask: "
        "'Does this look correct? Approve to proceed or tell me what to change.'\n\n"
        "STAGE 1 — BRIEF: Parse the user's request with parse_process_request. "
        "Confirm capacity, product, feed, and constraints.\n\n"
        "STAGE 2 — ROUTES: Use lookup_chemical_process (or search_chemical_process "
        "for unknowns). Present 2-3 chemistry routes with tradeoffs. "
        "User picks one.\n\n"
        "STAGE 3 — THERMO: Confirm compound list and property package "
        "(PR, SRK, NRTL, etc.). Explain the choice.\n\n"
        "STAGE 4 — BLOCK FLOW: Summarise the process as a numbered block-flow "
        "description (no DWSIM yet). Confirm topology.\n\n"
        "STAGE 5 — DWSIM PFD: Build the flowsheet with build_flowsheet_no_sim, "
        "then call export_flowsheet_image to get the PFD image. "
        "Return both the .dwxmz file path and the image path. "
        "The user opens the .dwxmz in DWSIM, sets stream conditions, and presses Solve.\n\n"
        "REACTION SETUP (inside Stage 5): always call configure_reactions with "
        "mode='ask' first, then follow user's choice (auto or manual).\n\n"
        "Use prompt templates: 'Design Chemical Process', 'Configure Reactions', "
        "'Compare Two Processes'."
    ),
)

# ─────────────────────────────────────────────
# PROCESS LIBRARY TOOLS
# ─────────────────────────────────────────────

@mcp.tool()
def lookup_chemical_process(
    chemical: Annotated[str, Field(
        description=(
            "Name of the chemical to look up. Examples: 'ethanol', 'ammonia', "
            "'methanol', 'acetic acid', 'benzene', 'ethylene oxide', "
            "'sulphuric acid', 'urea', 'acetone', 'hydrogen'."
        )
    )],
) -> dict:
    """
    Look up the industrial synthesis route and process blueprint for a chemical.

    Returns structured data including:
    - Industrial route name
    - Reactions with conditions (T, P, catalyst, conversion)
    - List of unit operations needed
    - Feed stream definitions
    - Recommended thermodynamic model
    - Process notes

    Use this as the starting point before building a DWSIM simulation.
    """
    return _lib.lookup_process(chemical)


@mcp.tool()
def list_available_processes() -> dict:
    """
    List all chemicals that have a built-in process blueprint in the library.

    Returns a list of chemical keys that can be passed to lookup_chemical_process.
    """
    chemicals = _lib.list_available_processes()
    return {
        "available_chemicals": chemicals,
        "count": len(chemicals),
        "usage": "Pass any of these to lookup_chemical_process to get the full blueprint.",
    }


@mcp.tool()
def get_process_summary(
    chemical: Annotated[str, Field(
        description="Name of the chemical (e.g. 'ethanol', 'ammonia')."
    )],
) -> str:
    """
    Return a concise, human-readable summary card for a chemical process.

    Includes: route, reactions, unit operations, compounds, thermo model.
    Useful for explaining the process to a student before diving into simulation.
    """
    data = _lib.lookup_process(chemical)

    if not data.get("found"):
        return (
            f"❌ '{chemical}' is not in the built-in process library.\n"
            f"Available chemicals: {', '.join(data.get('available_chemicals', []))}"
        )

    lines = [
        f"═══ {data['name']} ═══",
        f"Route:   {data['route']}",
        f"",
        f"Description:",
        f"  {data['description']}",
        f"",
        f"Reactions:",
    ]
    for rxn in data.get("reactions", []):
        lines.append(f"  • {rxn['equation']}")
        lines.append(f"    Type: {rxn['type']}  |  T: {rxn['temperature_C']}°C  "
                     f"|  P: {rxn['pressure_bar']} bar")
        if "conversion" in rxn:
            lines.append(f"    Conversion: {rxn['conversion']*100:.0f}%")
        lines.append(f"    Catalyst: {rxn.get('catalyst', 'N/A')}")
        lines.append("")

    lines.append("Unit Operations:")
    for op in data.get("unit_operations", []):
        lines.append(f"  [{op['type']:20s}] {op['name']}  — {op['purpose']}")

    lines.append("")
    lines.append(f"Compounds:     {', '.join(data['compounds'])}")
    lines.append(f"Thermo Model:  {data['thermo_model']}")
    lines.append("")
    lines.append(f"Notes: {data.get('notes', '')}")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# INPUT HANDLING TOOLS
# ─────────────────────────────────────────────

@mcp.tool()
def parse_process_request(
    user_input: Annotated[str, Field(
        description=(
            "The user's natural language description of the process they want. "
            "Examples: 'produce ethanol at 500 kg/hr from ethylene', "
            "'design ammonia plant 1000 tonnes/day', "
            "'methanol from syngas at 80 bar and 250°C'"
        )
    )],
) -> dict:
    """
    Parse a natural language process description into structured parameters.

    Extracts:
    - Target chemical name
    - Production rate (auto-converts units to kg/hr)
    - Feed temperature, pressure (auto-converts to SI)
    - Feed composition (percentages)
    - Catalyst mentions

    Also checks if the chemical is in the built-in library and returns
    the library data merged with user overrides if found.

    Use this as the FIRST step when a user describes a process in plain English.
    """
    parsed = _inp.parse_user_input(user_input)
    merged = _inp.merge_with_library(parsed)
    return {
        "parsed_input": parsed,
        "merged_process": merged,
        "next_steps": (
            "If 'in_library' is True, use the merged_process directly with "
            "build_flowsheet_no_sim (Stage 5). "
            "If False, use search_chemical_process or build_custom_process "
            "to create the process definition."
        ),
    }


# ─────────────────────────────────────────────
# WEB SEARCH / CUSTOM PROCESS TOOLS
# ─────────────────────────────────────────────

@mcp.tool()
def search_chemical_process(
    chemical: Annotated[str, Field(
        description="Name of the chemical to search for (e.g. 'styrene', 'formaldehyde')."
    )],
    search_text: Annotated[str, Field(
        description=(
            "Raw text from web search results about the industrial process. "
            "Paste the relevant search results here."
        )
    )] = "",
) -> dict:
    """
    Parse web search results about a chemical process into structured data.

    Use this when the chemical is NOT in the built-in library:
    1. First search the web for '{chemical} industrial production process'
    2. Pass the search results text to this tool
    3. The tool extracts temperatures, pressures, catalysts, conversions
    4. Claude should then review and complete the partial data

    Returns a partially-filled process dict that Claude should complete
    before passing to DWSIM simulation tools.
    """
    result = _ws.parse_web_search_to_process(chemical, search_text)
    result["recommended_thermo_model"] = _ws.recommend_thermo_model(
        result.get("compounds", [])
    )
    return result


@mcp.tool()
def build_custom_process(
    chemical_name: Annotated[str, Field(
        description="Name of the target chemical."
    )],
    route_name: Annotated[str, Field(
        description="Industrial route name (e.g. 'Ethylbenzene Dehydrogenation')."
    )],
    description: Annotated[str, Field(
        description="Process description paragraph."
    )],
    reactions: Annotated[list[dict], Field(
        description=(
            "List of reaction dicts. Each must have: equation, type "
            "(ConversionReactor/EquilibriumReactor), temperature_C, pressure_bar. "
            "Optional: conversion (0-1), catalyst."
        )
    )],
    compounds: Annotated[list[str], Field(
        description="List of compound names (must match DWSIM database)."
    )],
    thermo_model: Annotated[str, Field(
        description="Thermodynamic model (Peng-Robinson, NRTL, SRK, etc.)."
    )],
    unit_operations: Annotated[list[dict], Field(
        description=(
            "List of unit op dicts. Each must have: type, name, purpose. "
            "Type must be one of the valid DWSIM types."
        )
    )],
    streams: Annotated[list[dict], Field(
        description=(
            "List of feed stream dicts. Each must have: name, type (material/energy), "
            "T_C, P_bar, total_flow_kg_hr, composition (dict of compound: mole_frac)."
        )
    )],
    connections: Annotated[list[list[str]], Field(
        description=(
            "List of [from_tag, to_tag] pairs for wiring the flowsheet. "
            "CRITICAL: connections must always route THROUGH named stream tags — "
            "never connect a unit-op directly to another unit-op. "
            "Every stream in the 'streams' list must appear in at least one connection. "
            "Pattern: ['S-01', 'MIX-101'] (stream→unit), ['MIX-101', 'S-02'] (unit→stream), "
            "['S-02', 'H-101'] (stream→unit), etc. "
            "Feed streams come first, then alternate unit→stream→unit through the flowsheet."
        )
    )],
    notes: Annotated[str, Field(
        description="Additional process notes."
    )] = "",
) -> dict:
    """
    Build a complete process definition from scratch.

    Use this when the chemical is NOT in the built-in library and you have
    gathered enough information (from web search or Claude's knowledge)
    to define the full process.

    Returns a process_library-compatible dict ready for DWSIM simulation,
    PFD generation, or balance reporting.
    """
    return _ws.build_process_from_description(
        chemical_name=chemical_name,
        route_name=route_name,
        description=description,
        reactions=reactions,
        compounds=compounds,
        thermo_model=thermo_model,
        unit_operations=unit_operations,
        streams=streams,
        connections=[tuple(c) for c in connections],
        notes=notes,
    )


# ─────────────────────────────────────────────
# DWSIM SIMULATION TOOLS
# ─────────────────────────────────────────────

@mcp.tool()
def dwsim_status() -> dict:
    """
    Check whether DWSIM is installed and available for simulation.

    Returns path, DLL load status, and current flowsheet state.
    Run this first to confirm DWSIM is ready before starting a simulation.
    """
    return _dwsim.dwsim_status()


@mcp.tool()
def create_flowsheet(
    compounds: Annotated[list[str], Field(
        description=(
            "List of compound names to include (must match DWSIM database). "
            "Example: ['Ethylene', 'Water', 'Ethanol']"
        )
    )],
    thermo_model: Annotated[str, Field(
        description=(
            "Thermodynamic model name. Options: 'Peng-Robinson', 'SRK', 'NRTL', "
            "'UNIQUAC', 'UNIFAC', 'Steam Tables', 'CoolProp', 'PRSV2'."
        )
    )] = "Peng-Robinson",
) -> dict:
    """
    Create a new DWSIM flowsheet with the specified compounds and property package.

    This must be called before adding any unit operations or streams.
    Returns success flag, list of compounds added, and any missing compounds.
    """
    return _dwsim.create_flowsheet(compounds, thermo_model)


@mcp.tool()
def add_unit_operation(
    op_type: Annotated[str, Field(
        description=(
            "Type of unit operation. Supported values: "
            "MaterialStream, EnergyStream, Mixer, Splitter, Heater, Cooler, "
            "HeatExchanger, Valve, Pump, Compressor, Expander, Pipe, "
            "Flash, Vessel, Tank, ShortcutColumn, DistillationColumn, "
            "AbsorptionColumn, ConversionReactor, EquilibriumReactor, "
            "GibbsReactor, CSTR, PFR, ComponentSeparator."
        )
    )],
    tag: Annotated[str, Field(
        description="Unique tag/name for this object (e.g. 'H-101', 'S-01')."
    )],
    x: Annotated[int, Field(description="Canvas X coordinate (cosmetic).")] = 100,
    y: Annotated[int, Field(description="Canvas Y coordinate (cosmetic).")] = 100,
) -> dict:
    """
    Add a single unit operation or stream to the current flowsheet.

    Returns success flag and the tag that was registered.
    Must call create_flowsheet first.
    """
    return _dwsim.add_unit_operation(op_type, tag, x, y)


@mcp.tool()
def set_stream_conditions(
    tag: Annotated[str, Field(description="Tag of the material stream to configure.")],
    temperature_K: Annotated[float | None, Field(
        description="Temperature in Kelvin (e.g. 298.15 for 25°C)."
    )] = None,
    pressure_Pa: Annotated[float | None, Field(
        description="Pressure in Pascal (e.g. 101325 for 1 atm, 7000000 for 70 bar)."
    )] = None,
    mass_flow_kg_s: Annotated[float | None, Field(
        description="Mass flow rate in kg/s (divide kg/hr by 3600)."
    )] = None,
    composition_mole_fracs: Annotated[list[float] | None, Field(
        description=(
            "Mole fractions for each compound in the order they were added to the flowsheet. "
            "Must sum to 1.0. Example for [Ethylene, Water, Ethanol]: [0.99, 0.01, 0.0]"
        )
    )] = None,
) -> dict:
    """
    Set temperature, pressure, flow rate and composition on a material stream.

    All values in SI units (K, Pa, kg/s, mole fractions).
    Only the parameters you provide are updated; omit others to leave unchanged.
    """
    return _dwsim.set_stream_conditions(
        tag=tag,
        temperature_K=temperature_K,
        pressure_Pa=pressure_Pa,
        mass_flow_kg_s=mass_flow_kg_s,
        composition_mole_fracs=composition_mole_fracs,
    )


@mcp.tool()
def connect_objects(
    from_tag: Annotated[str, Field(description="Tag of the source object (stream or unit op).")],
    to_tag: Annotated[str, Field(description="Tag of the destination object.")],
) -> dict:
    """
    Connect two objects in the flowsheet.

    Streams flow from → to. For example, to feed stream 'S-01' into heater 'H-101':
      connect_objects(from_tag='S-01', to_tag='H-101')

    Uses automatic port selection (-1, -1).
    Returns success flag.
    """
    return _dwsim.connect_objects(from_tag, to_tag)


@mcp.tool()
def run_simulation(
    timeout_seconds: Annotated[int, Field(
        description="Maximum solver time in seconds before giving up."
    )] = 120,
) -> dict:
    """
    Solve (calculate) the current flowsheet.

    Runs DWSIM's sequential-modular solver. Returns success flag and any
    solver errors. Check stream and unit-op results after this succeeds.
    """
    return _dwsim.run_simulation(timeout_seconds)


@mcp.tool()
def get_stream_results(
    tags: Annotated[list[str] | None, Field(
        description=(
            "List of stream tags to query. Pass null/omit to get all streams. "
            "Example: ['S-01', 'S-02', 'outlet']"
        )
    )] = None,
) -> dict:
    """
    Read simulation results from material streams.

    Returns temperature (K and °C), pressure (Pa and bar),
    mass flow (kg/s and kg/hr), molar flow, mole fractions,
    and mass fractions for each requested stream.
    """
    return _dwsim.get_stream_results(tags)


@mcp.tool()
def get_unit_op_results(
    tags: Annotated[list[str] | None, Field(
        description=(
            "List of unit op tags to query. Pass null/omit to get all objects. "
            "Example: ['H-101', 'K-101']"
        )
    )] = None,
) -> dict:
    """
    Read simulation results from unit operations.

    Returns available properties such as:
    - duty_kW (heater/cooler/pump energy)
    - delta_P_Pa (pressure change across valve/pump/compressor)
    - outlet_T_K (outlet temperature)
    - conversion (reactor conversion)
    """
    return _dwsim.get_unit_op_results(tags)


@mcp.tool()
def save_flowsheet(
    file_path: Annotated[str, Field(
        description=(
            "Absolute path where the flowsheet will be saved. "
            "Use .dwxmz extension for compressed format (recommended), "
            "or .dwxml for plain XML."
        )
    )],
    compressed: Annotated[bool, Field(
        description="True (default) saves as compressed .dwxmz; False saves as .dwxml."
    )] = True,
) -> dict:
    """
    Save the current flowsheet to a file.

    The file can be opened in the DWSIM GUI for visual inspection and further editing.
    Returns success flag and the path where the file was saved.
    """
    return _dwsim.save_flowsheet(file_path, compressed)


@mcp.tool()
def export_flowsheet_image(
    output_path: Annotated[str | None, Field(
        description=(
            "Destination file path for the exported image (.png or .svg). "
            "Defaults to outputs/flowsheet_pfd.png. "
            "Call save_flowsheet first so the Xvfb strategy has a file to work from."
        )
    )] = None,
) -> dict:
    """
    Export the current DWSIM flowsheet as an image (PNG preferred, SVG fallback).

    Tries three strategies in order:
    1. Native DWSIM FlowsheetSurface.SaveAsBitmap (requires GUI surface)
    2. Xvfb headless screenshot via subprocess (Linux / Docker worker)
    3. SVG fallback rendered from registered object positions

    Returns image_path (show this to the user) and strategy used.
    Always call save_flowsheet before this tool so the file is persisted.
    """
    return _dwsim.export_flowsheet_image(output_path)


@mcp.tool()
def build_process_from_library(
    chemical: Annotated[str, Field(
        description=(
            "Name of the chemical to simulate. Must be in the built-in library. "
            "Run list_available_processes to see valid options."
        )
    )],
    output_dir: Annotated[str | None, Field(
        description=(
            "Directory where the .dwxmz file will be saved. "
            "Defaults to the 'outputs/' folder in the project directory."
        )
    )] = None,
) -> dict:
    """
    One-shot tool: build, run and save a complete DWSIM simulation from the library.

    This single call:
    1. Looks up the process blueprint for the chemical
    2. Creates a DWSIM flowsheet with correct compounds and thermo model
    3. Adds all unit operations
    4. Adds and configures all feed streams
    5. Wires up all connections
    6. Runs the simulation
    7. Collects stream and unit-op results
    8. Saves the flowsheet to disk

    Returns a comprehensive result dict with all step outcomes and numerical results.
    Perfect for quickly generating a first-draft simulation for a CPD assignment.
    """
    process_data = _lib.lookup_process(chemical)
    if not process_data.get("found"):
        return {
            "success": False,
            "error": f"Chemical '{chemical}' not found in library.",
            "available": _lib.list_available_processes(),
        }

    default_output = output_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "outputs"
    )
    return _dwsim.build_process_from_library(process_data, default_output)


@mcp.tool()
def modify_dwsim_file(
    file_path: Annotated[str, Field(
        description=(
            "Absolute path to the existing .dwxmz or .dwxml file to modify. "
            "Example: '/home/user/my_process.dwxmz'"
        )
    )],
    add_unit_ops: Annotated[list[dict] | None, Field(
        description=(
            "List of unit operations to add. Each dict must have 'type' and 'name'. "
            "Optional: 'x', 'y' for canvas position. "
            "Valid types: Mixer, Splitter, Heater, Cooler, HeatExchanger, Valve, "
            "Pump, Compressor, Flash, DistillationColumn, ConversionReactor, PFR, CSTR, etc."
            "Example: [{'type': 'DistillationColumn', 'name': 'T-01', 'x': 300, 'y': 100}]"
        )
    )] = None,
    add_connections: Annotated[list[list[str]] | None, Field(
        description=(
            "List of [from_tag, to_tag] pairs to wire. Tags must exist in the file "
            "(existing or newly added). "
            "Example: [['S-FEED', 'T-01'], ['T-01', 'S-DIST']]"
        )
    )] = None,
    output_path: Annotated[str | None, Field(
        description=(
            "Where to save the modified file. Omit to overwrite the original. "
            "Use a new path to keep the original intact."
        )
    )] = None,
) -> dict:
    """
    Load an existing DWSIM flowsheet, add unit operations and/or connections, and save.

    This is the DWSIM file modification workflow:
    1. Student uploads their existing .dwxmz file
    2. Call this tool with the file path and what to add
    3. The tool loads the file, lists what's already there, adds the requested
       units and connections, then saves the result
    4. Student opens the updated file in DWSIM GUI

    Scope: adds unit ops and connections only. Does not modify existing objects.
    For complex changes (reconfigure existing unit ops), use load_dwsim_file +
    configure_unit_operation + save_flowsheet separately.

    Returns:
    - existing_objects: tags already present before modification
    - unit_ops_added: tags successfully added
    - connections_added: connections successfully wired
    - saved_to: path of the output file
    """
    return _dwsim.modify_dwsim_file(
        file_path=file_path,
        add_unit_ops=add_unit_ops,
        add_connections=[tuple(c) for c in add_connections] if add_connections else None,
        output_path=output_path,
    )


@mcp.tool()
def load_dwsim_file(
    file_path: Annotated[str, Field(
        description=(
            "Absolute path to the .dwxmz or .dwxml file the student wants to modify. "
            "Example: '/home/user/my_process.dwxmz'"
        )
    )],
) -> dict:
    """
    Load an existing DWSIM flowsheet file and list every object inside it.

    Use this as the first step when a student uploads their own .dwxmz file
    and asks Claude to add or modify unit operations inside it.

    Returns:
    - loaded_from: path of the file loaded
    - count: number of objects found
    - objects: list of {tag, type, x, y} for every unit op and stream
    - tags: flat list of all tags (for quick reference)

    After this call the flowsheet is active — you can immediately call
    add_unit_operation, connect_objects, configure_unit_operation, and
    save_flowsheet to modify it.
    """
    r_load = _dwsim.load_flowsheet(file_path)
    if not r_load.get("success"):
        return r_load
    r_list = _dwsim.list_existing_objects()
    return {**r_load, **r_list}


@mcp.tool()
def list_flowsheet_objects() -> dict:
    """
    List all objects in the currently active DWSIM flowsheet.

    Re-enumerates the flowsheet and refreshes the internal object registry.
    Useful after load_dwsim_file or after manually adding objects to confirm
    what is present before making further changes.

    Returns count, objects list ({tag, type, x, y}), and flat tags list.
    """
    return _dwsim.list_existing_objects()



@mcp.tool()
def add_energy_stream_to_unit_op(
    unit_op_tag: Annotated[str, Field(
        description=(
            "Tag of the unit operation that needs an energy stream connected "
            "(e.g. 'H-04', 'R-05'). Must already exist in the active flowsheet."
        )
    )],
    energy_tag: Annotated[str | None, Field(
        description=(
            "Optional tag for the new EnergyStream. Defaults to 'ES-<unit_op_tag>'. "
            "Example: 'ES-H-04', 'STEAM-01', 'CW-06'."
        )
    )] = None,
) -> dict:
    """
    Create an EnergyStream and connect it to the energy port of a unit operation.

    IMPORTANT — when to use this vs configure_unit_operation:
    - If the user says 'set outlet temperature to X' → use configure_unit_operation
      with outlet_T_C.  That sets the unit op to isothermal mode, which does NOT
      require an energy stream.
    - Only call this tool when the user specifically wants to model a utility
      connection (e.g. 'connect a steam stream to HEX 01') or when DWSIM
      reports 'energy stream required' after you have already tried isothermal mode.

    The energy stream is placed on the canvas near the unit op and connected to
    its energy port.  DWSIM tries port index 2 first (standard energy port for
    heaters/reactors), then falls back to auto-detect.
    """
    return _dwsim.add_energy_stream_to_unit_op(unit_op_tag, energy_tag)


@mcp.tool()
def configure_unit_operation(
    tag: Annotated[str, Field(
        description=(
            "Tag of the unit operation to configure (e.g. 'H-101', 'T-101', 'K-101'). "
            "Must already exist in the active flowsheet."
        )
    )],
    specs: Annotated[dict, Field(
        description=(
            "Dict of spec key → value. Works for ANY unit op in ANY flowsheet.\n"
            "Heater/Cooler:      outlet_T_C, duty_kW, delta_P_bar\n"
            "Compressor/Pump:    outlet_P_bar, efficiency\n"
            "Valve:              outlet_P_bar\n"
            "Flash/Vessel:       P_bar, T_C, vapor_frac\n"
            "ConversionReactor:  outlet_T_C  ← sets isothermal mode (no energy stream needed!)\n"
            "Splitter:           split_fraction  (fraction to first outlet; second = 1-f)\n"
            "ShortcutColumn/DistillationColumn:\n"
            "  light_key, heavy_key, light_key_recovery, heavy_key_recovery,\n"
            "  reflux_ratio, num_stages, condenser_P_bar, reboiler_P_bar, condenser_type\n"
            "Example reactor: {\"outlet_T_C\": 200}\n"
            "Example column:  {\"reflux_ratio\": 1.5, \"light_key\": \"Ethanol\", "
            "\"heavy_key\": \"Water\", \"light_key_recovery\": 0.99}"
        )
    )],
) -> dict:
    """
    Set operating specs on any unit operation — library process or custom.

    KEY BEHAVIOUR for ConversionReactor:
    Providing outlet_T_C automatically sets the reactor to isothermal mode
    (CalcMode=1), which removes the 'energy stream required' error that DWSIM
    raises in its default heat-balance mode.  Always set outlet_T_C on reactors
    before running the simulation.

    Use this whenever the user specifies operating parameters in their prompt:
    e.g. 'use reflux ratio 2.0', 'set outlet temperature 350°C',
    'condenser pressure 1.5 bar', 'compressor efficiency 80%'.
    """
    return _dwsim.configure_unit_operation(tag, specs)


@mcp.tool()
def configure_multiple_unit_ops(
    unit_op_specs: Annotated[dict, Field(
        description=(
            "Dict of {tag: {spec_key: value}} to configure in one call. "
            "Example: {\"H-101\": {\"outlet_T_C\": 300}, "
            "\"T-101\": {\"reflux_ratio\": 1.5, \"light_key\": \"Ethanol\", "
            "\"heavy_key\": \"Water\", \"light_key_recovery\": 0.99, "
            "\"heavy_key_recovery\": 0.01}}"
        )
    )],
) -> dict:
    """
    Configure multiple unit operations at once.

    Equivalent to calling configure_unit_operation for each tag.
    Use this when the user specifies conditions for several pieces of equipment
    in one prompt, or to apply a full set of operating specs before running
    the simulation.
    """
    return _dwsim.configure_all_unit_ops(unit_op_specs)


@mcp.tool()
def get_manual_reaction_instructions(
    process_data: Annotated[dict, Field(
        description=(
            "Process data dict (from library, build_custom_process, or validate_pfd_data). "
            "Must have 'reactions' and 'unit_operations' keys."
        )
    )],
) -> dict:
    """
    Generate step-by-step GUI instructions for the student to add reactions manually in DWSIM.

    Use this when:
    - The student says they want to add reactions themselves
    - Automatic reaction setup failed
    - The process has complex kinetics (Arrhenius, multi-step) that auto-setup handles poorly

    Returns a clear numbered guide: open Reactions Manager → add each reaction →
    create Reaction Set → assign to reactor → press Solve.

    The instructions are always correct regardless of DWSIM version or reaction complexity.
    """
    return _dwsim.get_manual_reaction_instructions(process_data)


@mcp.tool()
def configure_reactions(
    process_data: Annotated[dict, Field(
        description=(
            "Process data dict with 'reactions' and 'unit_operations' keys. "
            "From library lookup, build_custom_process, or validate_pfd_data."
        )
    )],
    mode: Annotated[str, Field(
        description=(
            "How to handle reaction setup:\n"
            "  'auto'   — Claude tries setup_reactions() automatically. "
            "             Falls back to manual instructions if it fails.\n"
            "  'manual' — Skip auto setup; return GUI instructions immediately.\n"
            "  'ask'    — Return the question to ask the student, plus both options."
        )
    )] = "ask",
) -> dict:
    """
    Flexible reaction configuration with student-choice UX.

    This is the recommended tool for ALL reaction setup. It supports three modes:

    'ask' (default):
      Returns a formatted question to show the student and structured data for
      both options. Claude should display this question, wait for the student's
      answer, then call configure_reactions again with mode='auto' or mode='manual'.

    'auto':
      Tries automatic reaction setup via setup_reactions(). If it succeeds, done.
      If it fails, automatically falls back and returns manual instructions so the
      student is never left stuck.

    'manual':
      Skips auto setup entirely and returns the step-by-step GUI guide.
      Use when the student says they prefer to configure reactions themselves,
      or when dealing with complex kinetics (Arrhenius, multi-step, catalytic).

    Returns differ by mode — always includes manual_instructions so the student
    can fall back at any point.
    """
    if mode == "ask":
        reactions = process_data.get("reactions", [])
        manual = _dwsim.get_manual_reaction_instructions(process_data)
        rxn_summary = "\n".join(
            f"  • {r.get('equation', 'unknown')}  "
            f"(T={r.get('temperature_C', '?')}°C, "
            f"conv={int((r.get('conversion') or 0) * 100)}%)"
            for r in reactions
        )
        question = (
            f"This process has {len(reactions)} reaction(s):\n{rxn_summary}\n\n"
            "How would you like to handle reaction setup?\n\n"
            "**Option A — Claude does it automatically**\n"
            "  I'll try to configure the reactions programmatically. "
            "Works well for simple stoichiometric reactions. "
            "If it fails, I'll give you the manual steps instead.\n\n"
            "**Option B — You add the reactions yourself in DWSIM**\n"
            "  I'll give you step-by-step instructions. "
            "Takes about 30 seconds in the GUI and always works.\n\n"
            "Which do you prefer? (Reply 'auto' or 'manual')"
        )
        return {
            "mode": "ask",
            "question_for_student": question,
            "reactions": reactions,
            "reactor_tags": manual["reactor_tags"],
            "manual_instructions": manual["instructions"],
            "next_step": "Call configure_reactions again with mode='auto' or mode='manual' based on student reply.",
        }

    if mode == "manual":
        result = _dwsim.get_manual_reaction_instructions(process_data)
        result["mode"] = "manual"
        result["message"] = (
            "Here are the step-by-step instructions to add reactions in the DWSIM GUI."
        )
        return result

    if mode == "auto":
        return _dwsim.configure_reactions_with_fallback(process_data)

    return {
        "error": f"Unknown mode '{mode}'. Use 'ask', 'auto', or 'manual'.",
        "valid_modes": ["ask", "auto", "manual"],
    }


@mcp.tool()
def setup_reactions(
    chemical: Annotated[str, Field(
        description=(
            "Chemical name whose reaction definitions should be loaded. "
            "Looks up the process library and creates DWSIM Reaction + ReactionSet objects, "
            "then assigns them to the reactor unit ops in the active flowsheet."
        )
    )],
) -> dict:
    """
    Create reaction sets for the active flowsheet from the process library.

    Call this after create_flowsheet + add_unit_operation but BEFORE run_simulation.
    Without a reaction set, ConversionReactor / EquilibriumReactor cannot converge
    and their blocks stay red (unsolved) in DWSIM.

    Returns success flag, reaction IDs created, and which reactors were assigned.
    """
    process_data = _lib.lookup_process(chemical)
    if not process_data.get("found"):
        return {
            "success": False,
            "error": f"Chemical '{chemical}' not in library.",
            "available": _lib.list_available_processes(),
        }
    return _dwsim.setup_reactions(process_data)


# ─────────────────────────────────────────────
# RESOURCE: process library as JSON
# ─────────────────────────────────────────────

@mcp.resource("cpd://process_library")
def process_library_resource() -> str:
    """
    Full process library as JSON.
    Provides Claude with all 10 chemical process blueprints at once.
    """
    return json.dumps(_lib.PROCESS_LIBRARY, indent=2)


@mcp.resource("cpd://process/{chemical}")
def single_process_resource(chemical: str) -> str:
    """Single chemical process data as JSON (e.g. cpd://process/ethanol)."""
    data = _lib.lookup_process(chemical)
    return json.dumps(data, indent=2)


# ─────────────────────────────────────────────
# PROMPT TEMPLATES
# ─────────────────────────────────────────────

@mcp.prompt(title="Design Chemical Process")
def design_process_prompt(chemical: str, production_rate_kg_hr: str = "1000") -> str:
    """Generate a structured prompt to guide Claude through a full CPD assignment."""
    return f"""Design a chemical process plant to produce {chemical} at {production_rate_kg_hr} kg/hr.

Please follow these steps:

1. **Look up the process blueprint**: Use `lookup_chemical_process("{chemical}")` to get the standard industrial route, reactions, unit operations, and feed stream data.

2. **Summarise the process**: Call `get_process_summary("{chemical}")` and explain the chemistry and process to me in plain language suitable for a CPD undergraduate student.

3. **Check DWSIM availability**: Run `dwsim_status()` to confirm the simulator is ready.

4. **Build the simulation**:
   a. Use `build_process_from_library("{chemical}")` for a quick first run, OR
   b. Build step-by-step using `create_flowsheet`, `add_unit_operation`, `set_stream_conditions`, `connect_objects`, `run_simulation`.

5. **Report the results**:
   - Call `get_stream_results()` and `get_unit_op_results()` to extract key numbers.
   - Present results in a clear table: stream name, T (°C), P (bar), flow (kg/hr), composition.
   - Report energy duties for heaters, coolers, pumps, compressors.

6. **Engineering analysis**:
   - Comment on the major energy consumers.
   - Note where recycle streams improve economics.
   - Suggest one process improvement a student could investigate.

Target production rate: {production_rate_kg_hr} kg/hr of {chemical}.
"""


@mcp.prompt(title="Configure Reactions")
def configure_reactions_prompt(chemical: str = "") -> str:
    """Guide Claude through the reaction setup decision workflow."""
    chem_hint = f" for {chemical}" if chemical else ""
    lookup_hint = (
        f'Call `lookup_chemical_process("{chemical}")` to get the reaction definitions.'
        if chemical
        else "Use the process_data dict already available from the previous step."
    )
    return f"""Set up reactions{chem_hint} in the DWSIM simulation.

Follow this workflow:

1. **Get process data**
   {lookup_hint}

2. **Ask the student** (always do this first)
   Call `configure_reactions(process_data, mode="ask")` and show the returned
   `question_for_student` to the student verbatim.
   Wait for their reply before proceeding.

3a. **If student chooses 'auto':**
    Call `configure_reactions(process_data, mode="auto")`.
    - If `mode` in result is `"auto"` and `success` is True → reactions are set up.
      Tell the student "Reactions configured. Run the simulation now."
    - If `mode` is `"manual_fallback"` → auto failed.
      Show the `manual_instructions` from the result and explain what happened.

3b. **If student chooses 'manual':**
    Call `configure_reactions(process_data, mode="manual")`.
    Display the `instructions` field to the student.
    Tell them: "Follow these steps in the DWSIM GUI, then come back and press Solve."

4. **After reactions are configured:**
   Call `run_simulation()` and report results.
   If the reactor stays red (unsolved), offer to show manual instructions again.
"""


@mcp.prompt(title="Compare Two Processes")
def compare_processes_prompt(chemical_a: str, chemical_b: str) -> str:
    """Generate a prompt to compare two CPD processes."""
    return f"""Compare the industrial production processes for {chemical_a} and {chemical_b}.

For each chemical:
1. Call `lookup_chemical_process` to get the blueprint.
2. Summarise the synthesis route, key reactions, and unit operations.

Then compare:
- Reaction conditions (T, P, conversion)
- Number of unit operations
- Recommended thermodynamic model and why
- Key separation challenges
- Environmental considerations (waste streams, byproducts)
- Typical scale of industrial production

Conclude with which process you think is more complex from a CPD standpoint, and why.
"""


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import io

    # ── Protect the MCP JSON-RPC stream from .NET console output ──
    #
    # DWSIM loads .NET assemblies via pythonnet which may write diagnostic
    # messages directly to file descriptor 1 (stdout) via Console.Out.
    # The MCP stdio transport also uses stdout for JSON-RPC framing.
    # If .NET writes even a single byte, the client sees corrupted JSON
    # and raises "Unexpected token … is not valid JSON".
    #
    # Fix: move the real stdout pipe to a new file descriptor, redirect
    # fd 1 to stderr (harmless sink), then point Python's sys.stdout at
    # the saved descriptor so FastMCP's writes still reach the client.
    _saved_fd = os.dup(1)          # duplicate the real stdout pipe
    os.dup2(2, 1)                  # fd 1 now points to stderr
    sys.stdout = io.TextIOWrapper(
        os.fdopen(_saved_fd, "wb", buffering=0),
        encoding="utf-8",
        write_through=True,
    )

    mcp.run()   # defaults to stdio transport (correct for Claude Desktop / Code)
