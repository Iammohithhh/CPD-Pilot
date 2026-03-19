"""
server.py — MCP server for Chemical Process Design (CPD) Pilot.

Exposes the following tools to Claude:

  PROCESS LIBRARY (always available):
    • lookup_chemical_process    — get blueprint for a named chemical
    • list_available_processes   — list all chemicals in the library
    • get_process_summary        — human-readable summary card

  DWSIM SIMULATION (requires DWSIM installation):
    • dwsim_status               — check if DWSIM is available
    • create_flowsheet           — create flowsheet with compounds + thermo model
    • add_unit_operation         — add a single unit operation
    • set_stream_conditions      — set T / P / flow / composition on a stream
    • connect_objects            — connect two simulation objects
    • run_simulation             — solve the flowsheet
    • get_stream_results         — read T, P, flow, composition from streams
    • get_unit_op_results        — read duty, ΔP etc. from unit operations
    • save_flowsheet             — save to .dwxmz file
    • build_process_from_library — one-shot: build + run + save from library

Usage:
    python server.py                  (stdio — for Claude Desktop / Claude Code)
    mcp dev server.py                 (dev mode with MCP Inspector)
"""

from __future__ import annotations

import json
import os
from typing import Annotated

from pydantic import Field
from mcp.server.fastmcp import FastMCP

import process_library as _lib
import dwsim_tools as _dwsim

# ─────────────────────────────────────────────
# Create MCP server instance
# ─────────────────────────────────────────────

mcp = FastMCP(
    "CPD-Pilot",
    instructions=(
        "You are a Chemical Process Design assistant. "
        "Use the process library tools to look up industrial synthesis routes, "
        "then use the DWSIM simulation tools to build and run process simulations. "
        "Always look up the process first, then construct the simulation step by step."
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
    mcp.run()   # defaults to stdio transport (correct for Claude Desktop / Code)
