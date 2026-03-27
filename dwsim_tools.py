"""
dwsim_tools.py — DWSIM Automation wrapper for MCP tools.

Provides helper functions to:
  1. Load DWSIM DLLs via pythonnet
  2. Create / load / save flowsheets
  3. Add compounds, property packages, unit ops, streams, connections
  4. Run simulations and read results

All functions return plain Python dicts so they are JSON-serialisable and
can be returned directly from MCP tool handlers.

DWSIM is an optional dependency.  If it is not installed, every function
returns {"error": "DWSIM not available", "detail": <reason>} so the MCP
server degrades gracefully.
"""

from __future__ import annotations

import contextlib
import os
import sys
import json
import traceback
import uuid
from pathlib import Path
from typing import Any


@contextlib.contextmanager
def _suppress_native_stdout():
    """
    Temporarily redirect OS-level file descriptor 1 (stdout) to devnull.

    .NET code loaded by pythonnet may call Console.WriteLine which writes
    directly to fd 1, bypassing Python's sys.stdout.  When running under
    the MCP stdio transport this corrupts the JSON-RPC framing.

    This context manager redirects fd 1 to /dev/null (or NUL on Windows)
    for the duration of the block, then restores it.  Python's sys.stdout
    is untouched and continues to work normally.
    """
    try:
        _saved = os.dup(1)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.close(devnull)
        yield
    except Exception:
        yield  # if dup fails, just run without redirect
    else:
        os.dup2(_saved, 1)
        os.close(_saved)

# ─────────────────────────────────────────────
# 1. Locate DWSIM installation
# ─────────────────────────────────────────────

def _find_dwsim_path() -> str | None:
    """Return the DWSIM installation directory, or None if not found."""
    candidates: list[str] = []

    # Environment variable override
    env_path = os.environ.get("DWSIM_PATH")
    if env_path:
        candidates.append(env_path)

    # Common Windows locations
    candidates += [
        r"C:\Users\{}\AppData\Local\DWSIM".format(os.environ.get("USERNAME", "")),
        r"C:\Program Files\DWSIM",
        r"C:\Program Files (x86)\DWSIM",
    ]
    # Common Linux / macOS locations (Flatpak, snap, manual install)
    candidates += [
        "/opt/dwsim",
        "/usr/local/dwsim",
        os.path.expanduser("~/dwsim"),
    ]

    for p in candidates:
        if p and os.path.isfile(os.path.join(p, "DWSIM.Automation.dll")):
            return p

    return None


DWSIM_PATH = _find_dwsim_path()

# ─────────────────────────────────────────────
# 2. Load DLLs (lazy, once)
# ─────────────────────────────────────────────

_dwsim_loaded: bool = False
_dwsim_error: str | None = None

# These will be populated after successful load
Automation3 = None
ObjectType = None
PropertyPackages = None
UnitOperations = None
Settings = None


def _load_dwsim() -> bool:
    """
    Attempt to load DWSIM assemblies via pythonnet.
    Returns True on success, False on failure.
    Sets module-level _dwsim_error on failure.
    """
    global _dwsim_loaded, _dwsim_error
    global Automation3, ObjectType, PropertyPackages, UnitOperations, Settings

    if _dwsim_loaded:
        return True
    if _dwsim_error:
        return False

    if DWSIM_PATH is None:
        _dwsim_error = (
            "DWSIM installation not found. Set the DWSIM_PATH environment variable "
            "to the directory containing DWSIM.Automation.dll."
        )
        return False

    try:
        # Windows COM initialisation
        if sys.platform == "win32":
            try:
                import pythoncom  # type: ignore
                pythoncom.CoInitialize()
            except ImportError:
                pass

        # Add DWSIM_PATH to OS PATH so Windows finds native DLLs
        # (libSkiaSharp, CoolProp, etc.) during P/Invoke calls.
        _path_env = os.environ.get("PATH", "")
        if DWSIM_PATH not in _path_env.split(os.pathsep):
            os.environ["PATH"] = DWSIM_PATH + os.pathsep + _path_env

        # Load .NET runtime.
        #
        # DWSIM.Thermodynamics.dll references System.Windows.Forms 4.0.0.0,
        # which in .NET 8 is provided by Microsoft.WindowsDesktop.App — NOT
        # the base Microsoft.NETCore.App that "coreclr" loads by default.
        # Without WindowsDesktop, Assembly.GetExportedTypes() throws
        # ReflectionTypeLoadException; pythonnet swallows it silently and
        # returns an empty namespace → "No module named 'DWSIM.Thermodynamics'".
        #
        # DWSIM.UI.Desktop.runtimeconfig.json mistakenly requests NETCore.App,
        # so we generate a small runtimeconfig.json that correctly asks for
        # Microsoft.WindowsDesktop.App (which IS installed at 8.0.11).
        try:
            import json as _json
            from pythonnet import load as _pn_load  # type: ignore

            _rtconfig_path = os.path.join(
                os.environ.get("TEMP", os.path.expanduser("~")),
                "dwsim_windesktop.runtimeconfig.json",
            )
            with open(_rtconfig_path, "w") as _rf:
                _json.dump(
                    {
                        "runtimeOptions": {
                            "tfm": "net8.0-windows",
                            "framework": {
                                "name": "Microsoft.WindowsDesktop.App",
                                "version": "8.0.0",
                            },
                            "rollForward": "LatestPatch",
                        }
                    },
                    _rf,
                )
            _pn_load("coreclr", runtime_config=_rtconfig_path)
        except Exception:
            pass  # older pythonnet auto-loads, or runtime already initialised

        # Suppress .NET console output during assembly loading to avoid
        # corrupting the MCP JSON-RPC stream on stdout.
        import clr  # type: ignore
        import System  # type: ignore  (always available with coreclr)

        # Register an AssemblyResolve handler BEFORE loading DWSIM assemblies.
        #
        # When pythonnet enumerates types in a freshly-loaded assembly it calls
        # Assembly.GetExportedTypes().  If any transitive dependency of that
        # assembly is not yet in the load context, .NET raises a
        # ReflectionTypeLoadException.  Pythonnet catches this silently and
        # returns an empty type list, so the CLR namespace importer finds
        # nothing and raises "No module named 'DWSIM.Thermodynamics'".
        #
        # The handler below resolves any unknown assembly to a DLL in
        # DWSIM_PATH, turning transitive-dependency failures into successful
        # loads so the type enumeration succeeds.
        def _resolve_dwsim_assembly(sender, args):  # noqa: ANN001
            short = args.Name.split(",")[0].strip()
            candidate = os.path.join(DWSIM_PATH, short + ".dll")
            if os.path.isfile(candidate):
                return System.Reflection.Assembly.LoadFrom(candidate)
            return None  # let .NET fall through to its normal search

        System.AppDomain.CurrentDomain.AssemblyResolve += _resolve_dwsim_assembly

        with _suppress_native_stdout():
            required_dlls = [
                "CapeOpen.dll",
                "DWSIM.Automation.dll",
                "DWSIM.Interfaces.dll",
                "DWSIM.GlobalSettings.dll",
                "DWSIM.SharedClasses.dll",
                "DWSIM.Thermodynamics.dll",
                "DWSIM.UnitOperations.dll",
                "DWSIM.Inspector.dll",
                "DWSIM.MathOps.dll",
            ]
            for dll in required_dlls:
                full_path = os.path.join(DWSIM_PATH, dll)
                if os.path.isfile(full_path):
                    clr.AddReference(full_path)

            # Import DWSIM namespaces via the CLR import hook
            from DWSIM.Automation import Automation3 as _A3  # type: ignore
            from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType as _OT  # type: ignore
            from DWSIM.Thermodynamics import PropertyPackages as _PP  # type: ignore
            from DWSIM.UnitOperations import UnitOperations as _UO  # type: ignore
            from DWSIM.GlobalSettings import Settings as _S  # type: ignore

            Automation3 = _A3
            ObjectType = _OT
            PropertyPackages = _PP
            UnitOperations = _UO
            Settings = _S

        _dwsim_loaded = True
        return True

    except Exception as exc:
        _dwsim_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return False


# ─────────────────────────────────────────────
# 3. DWSIM ObjectType name → enum mapping
# ─────────────────────────────────────────────

# Map the string names used in process_library.py to DWSIM ObjectType enum values.
# Evaluated lazily after DLLs are loaded.
def _ot(attr: str):
    """Return ObjectType.attr, falling back to ObjectType.OT_attr if needed."""
    val = getattr(ObjectType, attr, None)
    if val is not None:
        return val
    val = getattr(ObjectType, f"OT_{attr}", None)
    if val is not None:
        return val
    raise AttributeError(f"ObjectType has no attribute '{attr}' or 'OT_{attr}'")


def _obj_type(name: str):
    """Resolve a unit-op type name string to an ObjectType enum member."""
    if ObjectType is None:
        raise RuntimeError("DWSIM not loaded")

    _MAP = {
        "MaterialStream":    _ot("MaterialStream"),
        "EnergyStream":      _ot("EnergyStream"),
        "Mixer":             _ot("NodeIn"),
        "Splitter":          _ot("NodeOut"),
        "Heater":            _ot("Heater"),
        "Cooler":            _ot("Cooler"),
        "HeatExchanger":     _ot("HeatExchanger"),
        "Valve":             _ot("Valve"),
        "Pump":              _ot("Pump"),
        "Compressor":        _ot("Compressor"),
        "Expander":          _ot("Expander"),
        "Pipe":              _ot("Pipe"),
        "Flash":             _ot("Vessel"),
        "Vessel":            _ot("Vessel"),
        "Tank":              _ot("Tank"),
        "Filter":            _ot("Filter"),
        "ShortcutColumn":    _ot("ShortcutColumn"),
        "DistillationColumn":_ot("DistillationColumn"),
        "AbsorptionColumn":  _ot("AbsorptionColumn"),
        "ConversionReactor": _ot("RCT_Conversion"),
        "EquilibriumReactor":_ot("RCT_Equilibrium"),
        "GibbsReactor":      _ot("RCT_Gibbs"),
        "CSTR":              _ot("RCT_CSTR"),
        "PFR":               _ot("RCT_PFR"),
        "ComponentSeparator":_ot("ComponentSeparator"),
        "Recycle":           _ot("Recycle"),
    }
    if name not in _MAP:
        raise ValueError(f"Unknown unit operation type: '{name}'. "
                         f"Available: {list(_MAP.keys())}")
    return _MAP[name]


# ─────────────────────────────────────────────
# 4. Property-package factory
# ─────────────────────────────────────────────

def _make_property_package(model_name: str):
    """Create and return a DWSIM property package instance."""
    if PropertyPackages is None:
        raise RuntimeError("DWSIM not loaded")

    _PP_MAP = {
        "Peng-Robinson": PropertyPackages.PengRobinsonPropertyPackage,
        "PR": PropertyPackages.PengRobinsonPropertyPackage,
        "SRK": PropertyPackages.SRKPropertyPackage,
        "NRTL": PropertyPackages.NRTLPropertyPackage,
        "UNIQUAC": PropertyPackages.UNIQUACPropertyPackage,
        "UNIFAC": PropertyPackages.UNIFACPropertyPackage,
        "Steam Tables": PropertyPackages.SteamTablesPropertyPackage,
        "CoolProp": PropertyPackages.CoolPropPropertyPackage,
        "PRSV2": PropertyPackages.PRSV2PropertyPackage,
    }
    cls = _PP_MAP.get(model_name)
    if cls is None:
        # Fallback to Peng-Robinson
        cls = PropertyPackages.PengRobinsonPropertyPackage
    return cls()


# ─────────────────────────────────────────────
# 5. High-level API
# ─────────────────────────────────────────────

# Module-level handle to the current simulation so tools can share state.
_interf = None
_sim = None
_object_registry: dict[str, Any] = {}   # tag → simulation object


def initialize_dwsim() -> dict:
    """
    Load DWSIM DLLs and create the Automation3 interface.
    Must be called before any other simulation functions.
    """
    global _interf
    if not _load_dwsim():
        return {"success": False, "error": _dwsim_error}
    try:
        _interf = Automation3()
        return {"success": True, "message": "DWSIM Automation3 initialised.",
                "dwsim_path": DWSIM_PATH}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def create_flowsheet(compounds: list[str], thermo_model: str) -> dict:
    """
    Create a new empty DWSIM flowsheet, add compounds and property package.

    Args:
        compounds:    list of compound names (must match DWSIM database)
        thermo_model: name of thermodynamic model (e.g. "Peng-Robinson", "NRTL")

    Returns dict with success flag and info.
    """
    global _sim, _object_registry

    if _interf is None:
        r = initialize_dwsim()
        if not r["success"]:
            return r

    try:
        with _suppress_native_stdout():
            _sim = _interf.CreateFlowsheet()
            _object_registry = {}

            # Add compounds
            added = []
            missing = []
            for cname in compounds:
                try:
                    _sim.AddCompound(cname)
                    added.append(cname)
                except Exception:
                    # Try AvailableCompounds dict
                    try:
                        comp = _sim.AvailableCompounds[cname]
                        _sim.SelectedCompounds.Add(comp.Name, comp)
                        added.append(cname)
                    except Exception:
                        missing.append(cname)

            # Add property package
            pp = _make_property_package(thermo_model)
            _sim.AddPropertyPackage(pp)

        return {
            "success": True,
            "compounds_added": added,
            "compounds_missing": missing,
            "thermo_model": thermo_model,
            "message": f"Flowsheet created with {len(added)} compounds.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc),
                "traceback": traceback.format_exc()}


def add_unit_operation(op_type: str, tag: str, x: int = 100, y: int = 100) -> dict:
    """
    Add a unit operation (or stream) to the current flowsheet.

    Args:
        op_type: type string (e.g. "Heater", "MaterialStream", "Flash")
        tag:     unique tag / name (e.g. "H-101", "S-01")
        x, y:    canvas coordinates (cosmetic)

    Returns dict with success flag and tag.
    """
    global _object_registry

    if _sim is None:
        return {"success": False, "error": "No flowsheet active. Call create_flowsheet first."}

    try:
        ot = _obj_type(op_type)
        with _suppress_native_stdout():
            obj_wrapper = _sim.AddObject(ot, x, y, tag)
            obj = obj_wrapper.GetAsObject()
        _object_registry[tag] = obj
        return {"success": True, "tag": tag, "type": op_type}
    except Exception as exc:
        return {"success": False, "tag": tag, "error": str(exc)}


def add_all_unit_operations(unit_ops: list[dict],
                            connections: list | None = None) -> dict:
    """
    Batch-add unit operations from the process_library structure.

    If *connections* is provided, unit ops are laid out in a process-flow
    arrangement (left-to-right, multi-row for branches).  Otherwise falls
    back to a grid layout.

    Args:
        unit_ops:    list of dicts with keys 'type', 'name', 'purpose'
        connections: optional list of (from_tag, to_tag) tuples/lists used
                     to compute a topological layout

    Returns summary dict.
    """
    positions = _compute_layout(unit_ops, connections)

    results = []
    for op in unit_ops:
        tag = op["name"]
        px, py = positions.get(tag, (100, 100))
        r = add_unit_operation(op["type"], tag, px, py)
        results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    return {
        "success": fail_count == 0,
        "added": success_count,
        "failed": fail_count,
        "details": results,
    }


def _compute_layout(
    unit_ops: list[dict],
    connections: list | None = None,
) -> dict[str, tuple[int, int]]:
    """
    Compute canvas positions for unit operations based on connection topology.

    Uses a simple BFS-based topological layout:
      1. Build a directed graph from connections.
      2. Find source nodes (no incoming edges) — these start at column 0.
      3. BFS assigns each node to the column after its predecessor.
      4. Columns become X positions, rows within each column become Y positions.

    Falls back to a grid layout when no connections are provided.

    Returns dict of {tag: (x, y)}.
    """
    all_tags = [op["name"] for op in unit_ops]

    if not connections or len(connections) == 0:
        # Grid layout: 5 columns, wrap to next row
        positions = {}
        cols = 5
        x_step, y_step = 150, 120
        for i, tag in enumerate(all_tags):
            col = i % cols
            row = i // cols
            positions[tag] = (60 + col * x_step, 60 + row * y_step)
        return positions

    # Build adjacency data — only for tags that are unit ops (not streams)
    tag_set = set(all_tags)
    successors: dict[str, list[str]] = {t: [] for t in all_tags}
    predecessors: dict[str, list[str]] = {t: [] for t in all_tags}

    for conn in connections:
        if len(conn) < 2:
            continue
        src, dst = str(conn[0]), str(conn[1])
        # Only include edges between unit-op tags we know about.
        # Streams in the connection list that are also unit ops get counted.
        if src in tag_set and dst in tag_set:
            successors[src].append(dst)
            predecessors[dst].append(src)

    # Identify source nodes (no predecessors that are unit ops)
    sources = [t for t in all_tags if len(predecessors[t]) == 0]
    if not sources:
        # Cycle or all nodes have predecessors — pick first as source
        sources = [all_tags[0]]

    # DFS to assign columns.  Chemical processes often have recycle loops
    # (cycles in the graph).  DFS naturally handles these: if we encounter
    # a node that's already on the current DFS stack, it's a back-edge
    # (recycle) and we skip it rather than looping infinitely.
    column: dict[str, int] = {}
    _visiting: set[str] = set()  # nodes on the active DFS path

    def _dfs(node: str, depth: int) -> None:
        if node in _visiting:
            return  # back-edge (recycle loop) — skip to avoid cycle
        if node in column and column[node] >= depth:
            return  # already placed at same or deeper column
        column[node] = max(column.get(node, 0), depth)
        _visiting.add(node)
        for nxt in successors.get(node, []):
            _dfs(nxt, depth + 1)
        _visiting.discard(node)

    for s in sources:
        _dfs(s, 0)

    # Any unreached nodes get placed in the last column + 1
    max_col = max(column.values()) if column else 0
    for t in all_tags:
        if t not in column:
            max_col += 1
            column[t] = max_col

    # Group by column, then assign row within column
    from collections import defaultdict
    col_groups: dict[int, list[str]] = defaultdict(list)
    for t in all_tags:
        col_groups[column[t]].append(t)

    # Compute positions
    x_step = 160   # horizontal spacing between columns
    y_step = 100   # vertical spacing within a column
    x_start = 60
    y_start = 60

    positions = {}
    for col_idx in sorted(col_groups.keys()):
        members = col_groups[col_idx]
        # Center the column vertically
        total_height = (len(members) - 1) * y_step
        y_offset = y_start + max(0, (200 - total_height) // 2)  # center around y=200
        for row_idx, tag in enumerate(members):
            positions[tag] = (x_start + col_idx * x_step, y_offset + row_idx * y_step)

    return positions


def add_material_streams(streams: list[dict],
                         connections: list | None = None,
                         unit_op_positions: dict | None = None) -> dict:
    """
    Add material/energy streams from the process_library stream list.

    If connections and unit_op_positions are provided, feed streams are placed
    to the left of the unit op they connect to.  Otherwise uses a grid layout.

    Each stream dict has keys: name, type, T_C, P_bar, total_flow_kg_hr, composition
    """
    # Build a map of stream_tag → destination unit from connections
    stream_dest: dict[str, str] = {}
    if connections:
        stream_names = {s["name"] for s in streams}
        for conn in connections:
            if len(conn) >= 2 and str(conn[0]) in stream_names:
                stream_dest[str(conn[0])] = str(conn[1])

    results = []
    grid_x, grid_y = 50, 400  # fallback grid position (below unit ops)

    for i, s in enumerate(streams):
        tag = s["name"]
        stream_type = "MaterialStream" if s.get("type", "material") == "material" else "EnergyStream"

        # Try to position left of the destination unit op
        dest_tag = stream_dest.get(tag)
        if dest_tag and unit_op_positions and dest_tag in unit_op_positions:
            ux, uy = unit_op_positions[dest_tag]
            sx, sy = max(10, ux - 80), uy + 30  # slightly left and below
        else:
            # Grid fallback: 6 columns
            col = i % 6
            row = i // 6
            sx, sy = grid_x + col * 130, grid_y + row * 80

        r = add_unit_operation(stream_type, tag, sx, sy)
        results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": success_count == len(results),
        "added": success_count,
        "details": results,
    }


def set_stream_conditions(
    tag: str,
    temperature_K: float | None = None,
    pressure_Pa: float | None = None,
    mass_flow_kg_s: float | None = None,
    composition_mole_fracs: list[float] | None = None,
) -> dict:
    """
    Set operating conditions on a material stream.

    All values in SI units (K, Pa, kg/s).
    """
    if tag not in _object_registry:
        return {"success": False, "error": f"Tag '{tag}' not found in registry."}

    obj = _object_registry[tag]
    try:
        if temperature_K is not None:
            obj.SetTemperature(float(temperature_K))
        if pressure_Pa is not None:
            obj.SetPressure(float(pressure_Pa))
        if mass_flow_kg_s is not None:
            obj.SetMassFlow(float(mass_flow_kg_s))
        if composition_mole_fracs is not None:
            from System import Array  # type: ignore
            arr = Array[float](composition_mole_fracs)
            obj.SetOverallComposition(arr)

        return {"success": True, "tag": tag,
                "set": {k: v for k, v in {
                    "T_K": temperature_K,
                    "P_Pa": pressure_Pa,
                    "flow_kg_s": mass_flow_kg_s,
                }.items() if v is not None}}
    except Exception as exc:
        return {"success": False, "tag": tag, "error": str(exc)}


def _is_stream(tag: str) -> bool:
    """Check whether a registered object is a Material or Energy stream."""
    obj = _object_registry.get(tag)
    if obj is None:
        return False
    try:
        type_name = obj.GraphicObject.ObjectType.ToString()
        return type_name in ("MaterialStream", "EnergyStream")
    except Exception:
        # Fallback: stream tags often start with "S-"
        return tag.startswith("S-")


def connect_objects(from_tag: str, to_tag: str) -> dict:
    """
    Connect two objects in the flowsheet.

    DWSIM requires MaterialStream objects between unit operations.
    If both from_tag and to_tag are unit operations (not streams),
    an intermediate MaterialStream is created automatically.
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}

    if from_tag not in _object_registry:
        return {"success": False, "error": f"Source tag '{from_tag}' not found."}
    if to_tag not in _object_registry:
        return {"success": False, "error": f"Destination tag '{to_tag}' not found."}

    try:
        from_obj = _object_registry[from_tag]
        to_obj = _object_registry[to_tag]

        from_is_stream = _is_stream(from_tag)
        to_is_stream = _is_stream(to_tag)

        if from_is_stream or to_is_stream:
            # At least one side is a stream — direct connection is fine.
            # ConnectObjects is a method on _interf (Automation3), NOT on _sim.
            with _suppress_native_stdout():
                _interf.ConnectObjects(
                    _sim,
                    from_obj.GraphicObject, to_obj.GraphicObject, -1, -1
                )
            return {"success": True, "from": from_tag, "to": to_tag}
        else:
            # Both sides are unit operations — create an intermediate stream.
            # Use a clean sequential name to avoid DWSIM API issues with
            # hyphens in auto-generated tags (e.g. _S-S72-LIQ-VALVE2 breaks).
            _auto_stream_counter = getattr(connect_objects, "_counter", 0) + 1
            connect_objects._counter = _auto_stream_counter
            mid_tag = f"_AUTO_S{_auto_stream_counter:03d}"

            # Compute canvas position as midpoint between the two units
            try:
                fx = from_obj.GraphicObject.X
                fy = from_obj.GraphicObject.Y
                tx = to_obj.GraphicObject.X
                ty = to_obj.GraphicObject.Y
                mx, my = int((fx + tx) / 2), int((fy + ty) / 2)
            except Exception:
                mx, my = 200, 200

            r = add_unit_operation("MaterialStream", mid_tag, mx, my)
            if not r.get("success"):
                return {
                    "success": False,
                    "from": from_tag,
                    "to": to_tag,
                    "error": f"Could not create intermediate stream '{mid_tag}': {r.get('error')}",
                }

            mid_obj = _object_registry[mid_tag]

            # Connect: source unit → intermediate stream → destination unit
            # Both calls must go through _interf.ConnectObjects(_sim, ...).
            with _suppress_native_stdout():
                _interf.ConnectObjects(
                    _sim,
                    from_obj.GraphicObject, mid_obj.GraphicObject, -1, -1
                )
                _interf.ConnectObjects(
                    _sim,
                    mid_obj.GraphicObject, to_obj.GraphicObject, -1, -1
                )
            return {
                "success": True,
                "from": from_tag,
                "to": to_tag,
                "intermediate_stream": mid_tag,
            }
    except Exception as exc:
        return {"success": False, "from": from_tag, "to": to_tag, "error": str(exc)}


def connect_all(connections: list) -> dict:
    """
    Connect all object pairs from the connections list.

    Supports two formats:
      - Pair:   [from_tag, to_tag]  — direct connection (at least one must be a stream)
      - Triplet: [from_tag, stream_tag, to_tag] — expanded automatically into two pairs:
                  (from_tag → stream_tag) and (stream_tag → to_tag)

    DWSIM requires a MaterialStream between every two unit operations.
    Always route through named stream tags rather than connecting unit-op to unit-op.
    """
    results = []
    for conn in connections:
        if len(conn) == 3:
            # Triplet: unit_op → stream → unit_op — expand into two pair calls
            r1 = connect_objects(str(conn[0]), str(conn[1]))
            results.append(r1)
            r2 = connect_objects(str(conn[1]), str(conn[2]))
            results.append(r2)
        elif len(conn) >= 2:
            r = connect_objects(str(conn[0]), str(conn[1]))
            results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": success_count == len(results),
        "connected": success_count,
        "failed": len(results) - success_count,
        "details": results,
    }


def run_simulation(timeout_seconds: int = 120) -> dict:
    """
    Calculate (solve) the current flowsheet.

    Returns a dict with success flag and any solver errors.
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if _interf is None:
        return {"success": False, "error": "DWSIM interface not initialised."}

    try:
        with _suppress_native_stdout():
            # Auto-layout for cleaner flowsheet
            _sim.AutoLayout()

            Settings.SolverMode = 0  # synchronous

            if timeout_seconds and timeout_seconds > 0:
                try:
                    _interf.CalculateFlowsheet3(_sim, timeout_seconds)
                except Exception:
                    pass  # fall through to CalculateFlowsheet4

            errors = _interf.CalculateFlowsheet4(_sim)

        error_list = []
        if errors is not None:
            try:
                for e in errors:
                    error_list.append(str(e))
            except Exception:
                pass

        return {
            "success": len(error_list) == 0,
            "solver_errors": error_list,
            "message": "Simulation complete." if not error_list else
                       f"Simulation finished with {len(error_list)} error(s).",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc),
                "traceback": traceback.format_exc()}


def get_stream_results(tags: list[str] | None = None) -> dict:
    """
    Retrieve temperature, pressure, flow and composition for streams.

    Args:
        tags: list of stream tags to query; None = all registered streams

    Returns nested dict: {tag: {T_K, P_Pa, mass_flow_kg_s, molar_flow_mol_s, composition}}
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}

    query_tags = tags if tags is not None else list(_object_registry.keys())
    results: dict[str, Any] = {}

    for tag in query_tags:
        obj = _object_registry.get(tag)
        if obj is None:
            results[tag] = {"error": "Tag not found."}
            continue
        try:
            entry: dict[str, Any] = {}
            try:
                entry["T_K"] = obj.GetTemperature()
                entry["T_C"] = entry["T_K"] - 273.15
            except Exception:
                pass
            try:
                entry["P_Pa"] = obj.GetPressure()
                entry["P_bar"] = entry["P_Pa"] / 1e5
            except Exception:
                pass
            try:
                entry["mass_flow_kg_s"] = obj.GetMassFlow()
                entry["mass_flow_kg_hr"] = entry["mass_flow_kg_s"] * 3600
            except Exception:
                pass
            try:
                entry["molar_flow_mol_s"] = obj.GetMolarFlow()
            except Exception:
                pass
            try:
                comp_array = obj.GetOverallComposition()
                entry["mole_fractions"] = [float(c) for c in comp_array]
            except Exception:
                pass
            try:
                mass_comp = obj.GetOverallMassComposition()
                entry["mass_fractions"] = [float(c) for c in mass_comp]
            except Exception:
                pass
            results[tag] = entry
        except Exception as exc:
            results[tag] = {"error": str(exc)}

    return {"success": True, "streams": results}


def get_unit_op_results(tags: list[str] | None = None) -> dict:
    """
    Retrieve key results from unit operations (e.g. duty, ΔP, conversion).

    Returns nested dict: {tag: {duty_kW, delta_P_Pa, ...}}
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}

    query_tags = tags if tags is not None else list(_object_registry.keys())
    results: dict[str, Any] = {}

    for tag in query_tags:
        obj = _object_registry.get(tag)
        if obj is None:
            results[tag] = {"error": "Tag not found."}
            continue
        entry: dict[str, Any] = {}
        # Generic attributes — try each silently
        for attr_name, key in [
            ("DeltaQ", "duty_kW"),
            ("DeltaP", "delta_P_Pa"),
            ("Pout", "outlet_P_Pa"),
            ("OutletTemperature", "outlet_T_K"),
            ("ConversionSpec", "conversion"),
            ("EnergyBalance", "energy_balance_kW"),
        ]:
            try:
                val = getattr(obj, attr_name, None)
                if val is not None:
                    entry[key] = float(val)
            except Exception:
                pass
        results[tag] = entry

    return {"success": True, "unit_ops": results}


def save_flowsheet(file_path: str, compressed: bool = True) -> dict:
    """
    Save the current flowsheet to disk.

    Args:
        file_path:  Absolute path; use .dwxmz for compressed, .dwxml for plain.
        compressed: True = .dwxmz (default), False = .dwxml
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if _interf is None:
        return {"success": False, "error": "DWSIM interface not initialised."}

    try:
        dir_part = os.path.dirname(file_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with _suppress_native_stdout():
            _interf.SaveFlowsheet(_sim, file_path, compressed)
        return {"success": True, "saved_to": file_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def load_flowsheet(file_path: str) -> dict:
    """Load an existing DWSIM flowsheet file."""
    global _sim, _object_registry

    if _interf is None:
        r = initialize_dwsim()
        if not r["success"]:
            return r

    try:
        _sim = _interf.LoadFlowsheet(file_path)
        _object_registry = {}
        return {"success": True, "loaded_from": file_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_existing_objects() -> dict:
    """
    Enumerate all objects in the currently active flowsheet and repopulate
    the internal object registry.

    Call this after load_flowsheet() to discover what unit operations and
    streams already exist before adding new ones.

    Returns a list of objects with their tags and types.
    """
    global _object_registry

    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}

    objects: list[dict] = []
    try:
        for kvp in _sim.SimulationObjects:
            try:
                tag = str(kvp.Key)
                obj = kvp.Value
                _object_registry[tag] = obj  # re-register for subsequent ops

                entry: dict = {"tag": tag}
                try:
                    entry["type"] = str(obj.GraphicObject.ObjectType)
                except Exception:
                    pass
                try:
                    entry["x"] = int(obj.GraphicObject.X)
                    entry["y"] = int(obj.GraphicObject.Y)
                except Exception:
                    pass
                objects.append(entry)
            except Exception as inner_exc:
                objects.append({"error": str(inner_exc)})

        return {
            "success": True,
            "count": len(objects),
            "objects": objects,
            "tags": [o["tag"] for o in objects if "tag" in o],
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def modify_dwsim_file(
    file_path: str,
    add_unit_ops: list[dict] | None = None,
    add_connections: list[tuple] | None = None,
    output_path: str | None = None,
) -> dict:
    """
    Load an existing .dwxmz file, add new unit operations and/or connections,
    and save the result.

    Args:
        file_path:       path to the existing .dwxmz / .dwxml file.
        add_unit_ops:    list of dicts with keys: type, name, x (opt), y (opt).
                         Example: [{"type": "DistillationColumn", "name": "T-01"}]
        add_connections: list of (from_tag, to_tag) tuples or [from, to] lists.
        output_path:     where to save the modified file.  Defaults to the
                         same path as file_path (overwrites).

    Returns a summary of what was found, what was added, and where it was saved.
    """
    if not os.path.isfile(file_path):
        return {
            "success": False,
            "error": f"File not found: {file_path}",
        }

    steps: list[dict] = []

    # ── Load ────────────────────────────────────────────────────────────────
    r = load_flowsheet(file_path)
    steps.append({"step": "load_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # ── Inspect existing ─────────────────────────────────────────────────────
    r = list_existing_objects()
    steps.append({"step": "list_existing_objects", **r})
    existing_tags = r.get("tags", [])

    # ── Add unit operations ──────────────────────────────────────────────────
    added_ops: list[dict] = []
    if add_unit_ops:
        for op in add_unit_ops:
            op_type = op.get("type", "")
            tag = op.get("name", op.get("tag", ""))
            x = int(op.get("x", 100))
            y = int(op.get("y", 100))
            if not op_type or not tag:
                added_ops.append({"error": f"Missing type or name in {op}"})
                continue
            r = add_unit_operation(op_type, tag, x, y)
            added_ops.append(r)
        steps.append({"step": "add_unit_operations", "results": added_ops})

    # ── Add connections ──────────────────────────────────────────────────────
    conn_results: list[dict] = []
    if add_connections:
        for conn in add_connections:
            if len(conn) >= 2:
                r = connect_objects(str(conn[0]), str(conn[1]))
                conn_results.append(r)
        steps.append({"step": "add_connections", "results": conn_results})

    # ── Save ─────────────────────────────────────────────────────────────────
    save_to = output_path or file_path
    r = save_flowsheet(save_to)
    steps.append({"step": "save_flowsheet", **r})

    return {
        "success": r.get("success", False),
        "loaded_from": file_path,
        "saved_to": save_to,
        "existing_objects": existing_tags,
        "unit_ops_added": [o.get("tag") for o in added_ops if o.get("success")],
        "connections_added": [
            f"{c.get('from')} → {c.get('to')}"
            for c in conn_results
            if c.get("success")
        ],
        "steps": steps,
    }


def build_flowsheet_no_sim(
    process_data: dict,
    output_dir: str | None = None,
) -> dict:
    """
    Build a DWSIM flowsheet topology from process data WITHOUT running the
    simulation solver.

    Suitable for the PFD-upload workflow where the student wants a pre-wired
    .dwxmz file that they open in the DWSIM GUI, set stream conditions
    themselves, and then press Solve.

    Steps performed:
      1. Initialise DWSIM
      2. Create flowsheet (compounds + thermo model)
      3. Add all unit operations
      4. Add feed / intermediate streams
      5. Wire all connections
      6. Save to .dwxmz

    No simulation is run — convergence issues cannot occur here.

    Args:
        process_data: process_library-compatible dict.  Must contain at
                      minimum: compounds, thermo_model, unit_operations,
                      streams, connections.
        output_dir:   directory for the saved file (default: outputs/).

    Returns a result dict with file_path and a text topology_summary that
    Claude should show the student for confirmation before saving.
    """
    steps: list[dict] = []

    # ── 1. Initialise ───────────────────────────────────────────────────────
    r = initialize_dwsim()
    steps.append({"step": "initialise_dwsim", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # ── 2. Create flowsheet ─────────────────────────────────────────────────
    compounds = process_data.get("compounds", [])
    thermo_model = process_data.get("thermo_model", "Peng-Robinson")
    r = create_flowsheet(compounds=compounds, thermo_model=thermo_model)
    steps.append({"step": "create_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # ── 3. Add unit operations (with graph-based layout) ────────────────────
    unit_ops = process_data.get("unit_operations", [])
    connections = process_data.get("connections", [])
    r = add_all_unit_operations(unit_ops, connections)
    steps.append({"step": "add_unit_operations", **r})
    if r.get("added", 0) == 0 and unit_ops:
        return {"success": False, "error": "All unit operations failed to add.", "steps": steps}

    # Capture positions for stream placement
    unit_positions = _compute_layout(unit_ops, connections)

    # ── 4. Add streams (positioned near their destination unit) ───────────
    streams = process_data.get("streams", [])
    r = add_material_streams(streams, connections, unit_positions)
    steps.append({"step": "add_streams", **r})

    # ── 5. Wire connections ──────────────────────────────────────────────────
    r = connect_all(connections)
    steps.append({"step": "connect_objects", **r})

    # ── 6. Save (no simulation) ──────────────────────────────────────────────
    out_dir = output_dir or os.path.join(os.path.dirname(__file__), "outputs")
    chem_name = (
        process_data.get("chemical", "process")
        .replace(" ", "_")
        .replace("/", "_")
    )
    save_path = os.path.join(out_dir, f"{chem_name}_topology.dwxmz")
    r = save_flowsheet(save_path)
    steps.append({"step": "save_flowsheet", **r})

    # ── Build human-readable topology summary ────────────────────────────────
    unit_summary = [
        {
            "tag": u.get("name", ""),
            "type": u.get("type", ""),
            "purpose": u.get("purpose", ""),
        }
        for u in unit_ops
    ]
    stream_summary = [
        {"tag": s.get("name", ""), "type": s.get("type", "material")}
        for s in streams
    ]
    conn_lines = [
        f"  {c[0]} → {c[1]}" if len(c) >= 2 else str(c)
        for c in connections
    ]
    topology_text = (
        f"Compounds : {', '.join(compounds)}\n"
        f"Thermo    : {thermo_model}\n"
        f"Units     : {len(unit_ops)}\n"
        + "\n".join(f"  [{u['type']}] {u['tag']}  — {u['purpose']}" for u in unit_summary)
        + f"\nStreams   : {len(stream_summary)}\n"
        + "\n".join(f"  {s['tag']} ({s['type']})" for s in stream_summary)
        + f"\nConnections:\n"
        + "\n".join(conn_lines)
    )

    return {
        "success": r.get("success", False),
        "file_path": save_path if r.get("success") else None,
        "topology_summary": topology_text,
        "unit_operations": unit_summary,
        "streams": stream_summary,
        "connections": connections,
        "steps": steps,
        "next_steps": (
            "Topology saved. Open the .dwxmz file in the DWSIM GUI. "
            "Set stream conditions (T, P, flow, composition) as needed, "
            "then press Solve to run the simulation."
        ),
    }


def add_energy_stream_to_unit_op(unit_op_tag: str, energy_tag: str | None = None) -> dict:
    """
    Create an EnergyStream and connect it to the energy port of a unit operation.

    When to use
    ───────────
    You only need this when the unit op is in energy-stream mode:
    - Heater/Cooler with CalcMode = EnergyStream (mode 2): an external
      utility stream (steam, CW) drives the duty.
    - ConversionReactor in heat-balance mode (CalcMode 0): the heat of
      reaction is exported via an energy stream.

    For the common case (CalcMode 0/1 = specify outlet temperature), energy
    streams are NOT required and you should call configure_unit_operation
    with outlet_T_C instead — that is both simpler and more reliable.

    Args:
        unit_op_tag: Tag of the unit op to attach the energy stream to.
        energy_tag:  Tag for the new EnergyStream; defaults to "ES-<unit_op_tag>".

    Returns dict with success, energy stream tag, and connection details.
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if unit_op_tag not in _object_registry:
        return {"success": False, "error": f"Unit op '{unit_op_tag}' not found."}

    if energy_tag is None:
        energy_tag = f"ES-{unit_op_tag}"

    # Place the energy stream near the unit op on the canvas
    unit_obj = _object_registry[unit_op_tag]
    try:
        ex = int(unit_obj.GraphicObject.X) + 60
        ey = int(unit_obj.GraphicObject.Y) - 60
    except Exception:
        ex, ey = 300, 100

    r = add_unit_operation("EnergyStream", energy_tag, ex, ey)
    if not r.get("success"):
        return r

    e_obj = _object_registry[energy_tag]

    # Try explicit energy-port index (usually 2 for heater/cooler, varies by version)
    # then fall back to DWSIM auto-detect (-1).
    # ConnectObjects belongs to _interf (Automation3), not _sim (IFlowsheet).
    for src_port, dst_port in [(0, 2), (0, -1), (-1, -1)]:
        try:
            with _suppress_native_stdout():
                _interf.ConnectObjects(
                    _sim,
                    e_obj.GraphicObject, unit_obj.GraphicObject,
                    src_port, dst_port,
                )
            return {
                "success": True,
                "energy_stream": energy_tag,
                "connected_to": unit_op_tag,
                "port_used": f"{src_port}→{dst_port}",
            }
        except Exception:
            pass

    return {
        "success": False,
        "energy_stream": energy_tag,
        "error": (
            f"EnergyStream '{energy_tag}' was created but could not be connected "
            f"to the energy port of '{unit_op_tag}'. "
            "Use configure_unit_operation with outlet_T_C to avoid needing an energy stream."
        ),
    }


def configure_unit_operation(tag: str, specs: dict) -> dict:
    """
    Set operating specs on any unit operation in the active flowsheet.

    Works for ANY process — library or custom.  Just pass the tag and a flat
    dict of spec keys.  Unknown keys are silently skipped; multiple fallback
    property names are tried for each spec so it stays robust across DWSIM
    versions.

    Supported spec keys
    ───────────────────
    Heater / Cooler
        outlet_T_C   float  Outlet temperature in °C
        outlet_T_K   float  Outlet temperature in K
        duty_kW      float  Heat duty in kW (positive = add heat)
        delta_P_bar  float  Pressure drop across unit in bar

    Compressor / Pump / Expander
        outlet_P_bar float  Outlet pressure in bar
        outlet_P_Pa  float  Outlet pressure in Pa
        efficiency   float  Isentropic efficiency 0–1

    Flash / Vessel / Separator
        P_bar        float  Flash pressure in bar
        T_C          float  Flash temperature in °C (PT flash)
        vapor_frac   float  Vapour fraction 0–1 (PV flash, use instead of T_C)

    Valve
        outlet_P_bar float  Outlet pressure in bar

    ShortcutColumn / DistillationColumn / AbsorptionColumn
        light_key            str    Light-key compound name
        heavy_key            str    Heavy-key compound name
        light_key_recovery   float  Mole-fraction recovery of light key in distillate
        heavy_key_recovery   float  Mole-fraction recovery of heavy key in bottoms
        reflux_ratio         float  Operating reflux ratio (must be > min reflux)
        num_stages           int    Number of theoretical stages
        condenser_P_bar      float  Condenser pressure in bar
        reboiler_P_bar       float  Reboiler pressure in bar
        condenser_type       int    0 = total condenser (default), 1 = partial

    Args:
        tag:   Tag of the unit operation in the active flowsheet.
        specs: Dict of spec key → value (see above).

    Returns dict with success flag, tag, and list of properties applied/failed.
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if tag not in _object_registry:
        return {"success": False, "error": f"Tag '{tag}' not found in flowsheet."}

    obj = _object_registry[tag]
    applied: list[str] = []
    skipped: list[str] = []

    def _try_set(attr_names, value, label: str) -> bool:
        """Try setting `value` on the first matching attribute in attr_names."""
        for a in attr_names:
            try:
                setattr(obj, a, value)
                applied.append(f"{label} → {a}={value}")
                return True
            except Exception:
                pass
        skipped.append(f"{label}: none of {attr_names} accepted value {value}")
        return False

    # ── Detect object type ────────────────────────────────────────────────────
    obj_type = ""
    try:
        obj_type = obj.GraphicObject.ObjectType.ToString()
    except Exception:
        try:
            obj_type = type(obj).__name__
        except Exception:
            pass

    # ── Heater / Cooler ───────────────────────────────────────────────────────
    if obj_type in ("Heater", "Cooler") or "eater" in obj_type or "ooler" in obj_type:
        if "outlet_T_C" in specs or "outlet_T_K" in specs:
            T_K = (specs["outlet_T_K"] if "outlet_T_K" in specs
                   else specs["outlet_T_C"] + 273.15)
            # CalcMode 0 = specify outlet temperature
            _try_set(["CalcMode"], 0, "CalcMode=OutletTemp")
            _try_set(
                ["DefinedTemperature", "OutletTemperature", "Tout", "Temperature"],
                T_K, "outlet_T_K",
            )
        if "duty_kW" in specs:
            _try_set(["CalcMode"], 1, "CalcMode=Duty")
            _try_set(["DeltaQ", "HeatDuty", "Duty"], specs["duty_kW"] * 1000, "duty_W")
        if "delta_P_bar" in specs:
            _try_set(["DeltaP", "PressureDrop"], specs["delta_P_bar"] * 1e5, "delta_P_Pa")

    # ── Compressor / Pump / Expander ──────────────────────────────────────────
    elif obj_type in ("Compressor", "Pump", "Expander") or any(
        k in obj_type for k in ("ompressor", "ump", "xpander")
    ):
        if "outlet_P_bar" in specs or "outlet_P_Pa" in specs:
            P_Pa = (specs["outlet_P_Pa"] if "outlet_P_Pa" in specs
                    else specs["outlet_P_bar"] * 1e5)
            _try_set(["CalcMode"], 0, "CalcMode=OutletPressure")
            _try_set(["POut", "OutletPressure", "Pout"], P_Pa, "outlet_P_Pa")
        if "efficiency" in specs:
            eff = specs["efficiency"]
            _try_set(
                ["AdiabaticEfficiency", "Eficiencia",
                 "IsentropicEfficiency", "Efficiency"],
                eff, "efficiency",
            )

    # ── Valve ─────────────────────────────────────────────────────────────────
    elif obj_type == "Valve" or "alve" in obj_type:
        if "outlet_P_bar" in specs or "outlet_P_Pa" in specs:
            P_Pa = (specs["outlet_P_Pa"] if "outlet_P_Pa" in specs
                    else specs["outlet_P_bar"] * 1e5)
            # CalcMode 0 = outlet pressure (must be set before POut in some builds)
            _try_set(["CalcMode", "CalculationMode"], 0, "CalcMode=OutletPressure")
            _try_set(["POut", "OutletPressure", "Pout"], P_Pa, "outlet_P_Pa")

    # ── Flash / Vessel / Separator ────────────────────────────────────────────
    elif obj_type in ("Vessel", "Tank", "Flash") or any(
        k in obj_type for k in ("essel", "lash", "eparator")
    ):
        if "P_bar" in specs:
            P_Pa = specs["P_bar"] * 1e5
            _try_set(["FlashPressure", "Pressure", "OperatingPressure"], P_Pa, "P_Pa")
        if "T_C" in specs:
            T_K = specs["T_C"] + 273.15
            # PT flash
            _try_set(["FlashType", "CalculationMode"], 1, "FlashType=PT")
            _try_set(["FlashTemperature", "Temperature", "OperatingTemperature"],
                     T_K, "T_K")
        elif "vapor_frac" in specs:
            # PV flash
            _try_set(["FlashType", "CalculationMode"], 0, "FlashType=PV")
            _try_set(["VaporFraction", "VF"], specs["vapor_frac"], "vapor_frac")

    # ── ShortcutColumn / DistillationColumn / AbsorptionColumn ───────────────
    elif any(k in obj_type for k in ("Column", "hortcut", "istillation", "bsorption")):
        if "light_key" in specs:
            _try_set(
                ["LightKeyCompound", "LightKey", "ReferenceComponent"],
                specs["light_key"], "light_key",
            )
        if "heavy_key" in specs:
            _try_set(
                ["HeavyKeyCompound", "HeavyKey"],
                specs["heavy_key"], "heavy_key",
            )
        if "light_key_recovery" in specs:
            _try_set(
                ["LightKeyMoleFractionSpec", "LightKeyRecovery",
                 "ReferenceComponentRecovery", "LKRecovery"],
                specs["light_key_recovery"], "light_key_recovery",
            )
        if "heavy_key_recovery" in specs:
            _try_set(
                ["HeavyKeyMoleFractionSpec", "HeavyKeyRecovery", "HKRecovery"],
                specs["heavy_key_recovery"], "heavy_key_recovery",
            )
        if "reflux_ratio" in specs:
            _try_set(
                ["RefluxRatio", "ActualRefluxRatio", "RR"],
                specs["reflux_ratio"], "reflux_ratio",
            )
        if "num_stages" in specs:
            _try_set(
                ["NumberOfStages", "NumberOfTheoreticalStages", "N"],
                int(specs["num_stages"]), "num_stages",
            )
        if "condenser_type" in specs:
            _try_set(["CondenserType"], int(specs["condenser_type"]), "condenser_type")
        if "condenser_P_bar" in specs:
            P_Pa = specs["condenser_P_bar"] * 1e5
            _try_set(
                ["CondenserPressure", "Pcondens", "Pcond"],
                P_Pa, "condenser_P_Pa",
            )
        if "reboiler_P_bar" in specs:
            P_Pa = specs["reboiler_P_bar"] * 1e5
            _try_set(
                ["ReboilerPressure", "Preboiler", "Preb"],
                P_Pa, "reboiler_P_Pa",
            )

    # ── ConversionReactor / EquilibriumReactor / CSTR / PFR ─────────────────
    #
    # KEY FIX: DWSIM reactors default to heat-balance mode (CalcMode 0), which
    # requires an energy stream to be connected.  Setting CalcMode = 1 switches
    # to "specify outlet temperature" (isothermal) mode, which removes the
    # energy-stream requirement entirely.  Always do this when outlet_T_C is
    # provided; it is the correct engineering assumption for most assignments.
    elif any(k in obj_type for k in (
        "RCT_Conversion", "RCT_Equilibrium", "RCT_Gibbs", "RCT_CSTR", "RCT_PFR",
        "Reactor", "CSTR", "PFR",
    )):
        if "outlet_T_C" in specs or "outlet_T_K" in specs:
            T_K = (specs["outlet_T_K"] if "outlet_T_K" in specs
                   else specs["outlet_T_C"] + 273.15)
            # CalcMode 1 = isothermal (specify outlet temperature)
            # This removes the energy-stream connection requirement.
            _try_set(
                ["CalcMode", "ReactorCalcMode", "OperationMode", "OutletTempMode"],
                1, "CalcMode=Isothermal",
            )
            _try_set(
                ["OutletTemperature", "ReactionTemperature",
                 "IsothermalTemperature", "DefinedTemperature", "Temperature"],
                T_K, "outlet_T_K",
            )
        if "outlet_P_bar" in specs:
            P_Pa = specs["outlet_P_bar"] * 1e5
            _try_set(
                ["OutletPressure", "POut", "ReactionPressure"],
                P_Pa, "outlet_P_Pa",
            )

    # ── Splitter (NodeOut) ────────────────────────────────────────────────────
    elif obj_type in ("NodeOut", "Splitter") or "plitter" in obj_type:
        if "split_fraction" in specs:
            # split_fraction = fraction leaving through the FIRST outlet.
            # Second outlet gets 1 - split_fraction.
            frac = float(specs["split_fraction"])

            # DWSIM's NodeOut.Ratios is Dictionary(Of String, Double) keyed by
            # outlet stream TAG.  Scan the output connectors to find attached tags,
            # then set per-stream ratios.  This is the only reliable method.
            ratio_set = False
            try:
                out_tags = []
                for conn in obj.GraphicObject.OutputConnectors:
                    try:
                        if conn.IsAttached:
                            attached_go = conn.AttachedConnector.AttachedFrom
                            # Find matching tag in registry
                            for stag, sobj in _object_registry.items():
                                try:
                                    if sobj.GraphicObject is attached_go:
                                        out_tags.append(stag)
                                        break
                                except Exception:
                                    pass
                    except Exception:
                        pass

                if len(out_tags) >= 2:
                    ratios = {out_tags[0]: frac, out_tags[1]: 1.0 - frac}
                    for stag, ratio in ratios.items():
                        try:
                            obj.Ratios[stag] = ratio
                        except Exception:
                            pass
                    applied.append(f"Ratios set per outlet stream: {ratios}")
                    ratio_set = True
                elif len(out_tags) == 1:
                    # Only one outlet connected so far — set what we can
                    try:
                        obj.Ratios[out_tags[0]] = frac
                        applied.append(f"Ratio set for single outlet {out_tags[0]}: {frac}")
                    except Exception:
                        pass
            except Exception as e:
                skipped.append(f"outlet-connector scan failed: {e}")

            if not ratio_set:
                # Fallback: try simple attribute-based approaches
                _try_set(["SplitRatios"], [frac, 1.0 - frac], "split_fractions_list")
                for idx, val in enumerate([frac, 1.0 - frac]):
                    _try_set(
                        [f"StreamRatio({idx})", f"StreamRatios[{idx}]",
                         f"SplitRatio_{idx}"],
                        val, f"stream_ratio_{idx}",
                    )

    else:
        # Unknown type — record as skipped
        for key in specs:
            skipped.append(f"{key}: unrecognised unit op type '{obj_type}'")

    return {
        "success": True,
        "tag": tag,
        "unit_op_type": obj_type,
        "applied": applied,
        "skipped": skipped,
    }


def configure_all_unit_ops(unit_op_specs: dict) -> dict:
    """
    Apply a full specs dict {tag: {spec_key: value, ...}} to the active flowsheet.

    Calls configure_unit_operation() for every tag in unit_op_specs.
    Used by build_process_from_library and can also be called directly.

    Args:
        unit_op_specs: e.g. {"H-101": {"outlet_T_C": 300}, "T-101": {...}}

    Returns summary dict.
    """
    results = {}
    for tag, specs in unit_op_specs.items():
        results[tag] = configure_unit_operation(tag, specs)

    success_count = sum(1 for r in results.values() if r.get("success"))
    return {
        "success": success_count == len(results),
        "configured": success_count,
        "failed": len(results) - success_count,
        "details": results,
    }


def setup_reactions(process_data: dict) -> dict:
    """
    Create DWSIM reaction objects from process_library reaction specs and assign
    them to the reactor unit operations in the current flowsheet.

    DWSIM's ConversionReactor requires:
      1. A Reaction object with stoichiometry + conversion spec
      2. A ReactionSet containing that reaction
      3. The reactor's ReactionSetID pointing at that set

    Without this, the reactor cannot converge and all downstream objects stay red.

    Args:
        process_data: dict from process_library with 'reactions', 'compounds',
                      'unit_operations' keys

    Returns dict with success flag and details.
    """
    if _sim is None:
        return {"success": False, "error": "No flowsheet active."}

    reactions_data = process_data.get("reactions", [])
    if not reactions_data:
        return {"success": True, "message": "No reactions defined — skipping.", "added": 0}

    compounds = process_data.get("compounds", [])
    unit_ops   = process_data.get("unit_operations", [])

    _reactor_types = {
        "ConversionReactor", "EquilibriumReactor", "GibbsReactor", "CSTR", "PFR",
    }
    reactors = [op for op in unit_ops if op["type"] in _reactor_types]

    try:
        # ── 1. Import DWSIM reaction classes ──────────────────────────────────
        _Rxn = _RStoich = _RxnSet = None

        for mod_path in [
            ("DWSIM.Thermodynamics.Reactions", "Reaction"),
            ("DWSIM.SharedClasses.Utility",    "Reaction"),
            ("DWSIM.SharedClasses",            "Reaction"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(mod_path[0])
                _Rxn = getattr(mod, mod_path[1])
                break
            except Exception:
                pass

        if _Rxn is None:
            # Last-resort: try direct CLR import
            try:
                from DWSIM.Thermodynamics.Reactions import Reaction as _Rxn  # type: ignore
            except Exception:
                pass

        for mod_path in [
            ("DWSIM.Thermodynamics.Reactions", "ReactionStoichimetry"),
            ("DWSIM.SharedClasses.Utility",    "ReactionStoichimetry"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(mod_path[0])
                _RStoich = getattr(mod, mod_path[1])
                break
            except Exception:
                pass

        if _RStoich is None:
            try:
                from DWSIM.Thermodynamics.Reactions import ReactionStoichimetry as _RStoich  # type: ignore
            except Exception:
                pass

        for mod_path in [
            ("DWSIM.SharedClasses.Utility", "ReactionSet"),
            ("DWSIM.SharedClasses",         "ReactionSet"),
        ]:
            try:
                import importlib
                mod = importlib.import_module(mod_path[0])
                _RxnSet = getattr(mod, mod_path[1])
                break
            except Exception:
                pass

        if _RxnSet is None:
            try:
                from DWSIM.SharedClasses.Utility import ReactionSet as _RxnSet  # type: ignore
            except Exception:
                pass

        if _Rxn is None or _RxnSet is None:
            return {
                "success": False,
                "error": (
                    "Could not import DWSIM reaction classes. "
                    "Reactions not added — simulator may not converge."
                ),
            }

        # ── 2. Build one ReactionSet for all reactions ────────────────────────
        rxnset = _RxnSet()
        rxnset_id = str(uuid.uuid4())
        rxnset.ID   = rxnset_id
        rxnset.Name = f"{process_data.get('chemical', 'Process')} Reactions"

        added = []

        for i, rxn_data in enumerate(reactions_data):
            try:
                rxn = _Rxn()
                rxn_id   = str(uuid.uuid4())
                rxn.ID   = rxn_id
                rxn.Name = rxn_data.get("equation", f"Reaction {i+1}")

                # ── Reaction type ───────────────────────────────────────────
                rxn_type = rxn_data.get("type", "ConversionReactor")
                if rxn_type == "ConversionReactor":
                    try:
                        from DWSIM.Thermodynamics.Reactions import ReactionType as _RT  # type: ignore
                        rxn.ReactionType = _RT.Conversion
                    except Exception:
                        try:
                            rxn.ReactionType = 0          # 0 = Conversion in DWSIM enum
                        except Exception:
                            pass

                # ── Conversion spec ─────────────────────────────────────────
                conversion = float(rxn_data.get("conversion", 0.05))
                for attr in ("Spec", "XFix", "ConversionSpec", "X_Conversion"):
                    try:
                        setattr(rxn, attr, conversion)
                    except Exception:
                        pass

                # ── Stoichiometry ────────────────────────────────────────────
                # Parse "A + B → C + D" style equations
                equation = rxn_data.get("equation", "")
                reactant_str, product_str = "", ""
                for sep in ["→", "->"]:
                    if sep in equation:
                        reactant_str, product_str = equation.split(sep, 1)
                        break

                base_set = False

                def _add_stoich(term_str: str, sign: int) -> None:
                    """Add stoichiometry for one side of the equation."""
                    nonlocal base_set
                    for term in term_str.split("+"):
                        term = term.strip()
                        for cname in compounds:
                            if cname in term:
                                try:
                                    coeff_raw = term.replace(cname, "").strip()
                                    coeff = float(coeff_raw) if coeff_raw else 1.0
                                except ValueError:
                                    coeff = 1.0

                                if _RStoich is not None:
                                    try:
                                        rs = _RStoich()
                                        rs.CompoundName   = cname
                                        rs.StoichCoeff    = sign * coeff
                                        rs.IsBaseReactant = (sign < 0 and not base_set)
                                        if rs.IsBaseReactant:
                                            rxn.BaseReactant = cname
                                            base_set = True
                                        rxn.Components.Add(cname, rs)
                                    except Exception:
                                        pass
                                break  # found compound for this term

                if reactant_str:
                    _add_stoich(reactant_str, -1)
                if product_str:
                    _add_stoich(product_str, +1)

                # ── Add reaction to flowsheet ────────────────────────────────
                _sim.Reactions.Add(rxn_id, rxn)

                # ── Add reaction ID to the reaction set ──────────────────────
                try:
                    rxnset.Reactions.Add(rxn_id, True)
                except Exception:
                    try:
                        rxnset.Reactions[rxn_id] = True
                    except Exception:
                        pass

                added.append({"id": rxn_id, "name": rxn.Name, "conversion": conversion})

            except Exception as exc:
                added.append({"error": str(exc), "rxn_index": i})

        # ── 3. Add reaction set to flowsheet ──────────────────────────────────
        _sim.ReactionSets.Add(rxnset_id, rxnset)

        # ── 4. Assign reaction set to all reactors ────────────────────────────
        assigned_to = []
        for reactor_op in reactors:
            tag = reactor_op["name"]
            obj = _object_registry.get(tag)
            if obj is not None:
                try:
                    obj.ReactionSetID = rxnset_id
                    assigned_to.append(tag)
                except Exception as exc:
                    assigned_to.append(f"{tag} (assign failed: {exc})")

        return {
            "success": True,
            "reaction_set_id": rxnset_id,
            "reactions_added": added,
            "assigned_to_reactors": assigned_to,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def get_manual_reaction_instructions(process_data: dict) -> dict:
    """
    Generate step-by-step manual instructions for adding reactions in the DWSIM GUI.

    Returns plain text instructions the student can follow in ~30 seconds.
    Always works regardless of DWSIM version or reaction complexity.

    Args:
        process_data: process_library-compatible dict with 'reactions' and
                      'unit_operations' keys.

    Returns dict with 'instructions' (string) and structured 'reactions' list.
    """
    reactions = process_data.get("reactions", [])
    unit_ops = process_data.get("unit_operations", [])

    _reactor_types = {
        "ConversionReactor", "EquilibriumReactor", "GibbsReactor", "CSTR", "PFR",
    }
    reactor_tags = [op["name"] for op in unit_ops if op.get("type") in _reactor_types]

    if not reactions:
        return {
            "instructions": "No reactions are defined for this process — nothing to add.",
            "reactions": [],
            "reactor_tags": reactor_tags,
        }

    lines: list[str] = []
    lines.append("═" * 60)
    lines.append("  MANUAL REACTION SETUP — DWSIM GUI")
    lines.append("═" * 60)
    lines.append("")
    lines.append("Step 1 — Open the Reactions Manager")
    lines.append("  In DWSIM menu: Data → Reactions")
    lines.append("  (Or press Ctrl+R in some versions)")
    lines.append("")
    lines.append("Step 2 — Add each reaction:")
    lines.append("")

    for i, rxn in enumerate(reactions, 1):
        eq = rxn.get("equation", "")
        rxn_type = rxn.get("type", "ConversionReactor")
        t_c = rxn.get("temperature_C", "")
        p_bar = rxn.get("pressure_bar", "")
        conv = rxn.get("conversion")
        catalyst = rxn.get("catalyst", "")

        if "Conversion" in rxn_type or rxn_type == "ConversionReactor":
            gui_type = "Conversion Reaction"
        elif "Equilibrium" in rxn_type:
            gui_type = "Equilibrium Reaction"
        elif "Gibbs" in rxn_type:
            gui_type = "Gibbs Reaction"
        elif rxn_type in ("CSTR", "PFR"):
            gui_type = "Kinetic Reaction"
        else:
            gui_type = "Conversion Reaction"

        lines.append(f"  Reaction {i}: {eq}")
        lines.append(f"    a) Click 'Add Reaction' → choose '{gui_type}'")
        lines.append(f"    b) Enter equation: {eq}")
        if conv is not None:
            lines.append(f"    c) Set conversion to: {conv * 100:.0f}%")
        if t_c:
            lines.append(f"    d) Temperature: {t_c} °C")
        if p_bar:
            lines.append(f"    e) Pressure: {p_bar} bar")
        if catalyst:
            lines.append(f"    f) Note catalyst: {catalyst}")
        lines.append("")

    lines.append("Step 3 — Create a Reaction Set")
    lines.append("  In the Reactions Manager: click 'Add Reaction Set'")
    lines.append("  Tick all the reactions you just created")
    lines.append("  Name it (e.g. 'RXN-SET-01') → click OK")
    lines.append("")
    lines.append("Step 4 — Assign the Reaction Set to the reactor(s)")
    for rtag in reactor_tags:
        lines.append(f"  Double-click reactor '{rtag}'")
        lines.append(f"  → 'Reaction Set' dropdown → select 'RXN-SET-01'")
        lines.append(f"  → click OK")
    lines.append("")
    lines.append("Step 5 — Press Solve (F5) and check results")
    lines.append("═" * 60)

    return {
        "instructions": "\n".join(lines),
        "reactions": reactions,
        "reactor_tags": reactor_tags,
        "reaction_count": len(reactions),
    }


def configure_reactions_with_fallback(process_data: dict) -> dict:
    """
    Try to set up reactions automatically; if it fails return manual instructions.

    This is the recommended entry point for reaction setup:
    - Auto mode: calls setup_reactions(), which works well for simple stoichiometric
      reactions from the process library.
    - On failure: returns manual step-by-step GUI instructions so the student is
      never blocked.

    Args:
        process_data: process_library-compatible dict.

    Returns:
        {
          "mode": "auto" | "manual_fallback",
          "success": bool,
          "auto_result": {...},          # present if auto was tried
          "manual_instructions": str,   # always present
          "reactions": [...],
          "reactor_tags": [...],
        }
    """
    manual = get_manual_reaction_instructions(process_data)

    if _sim is None:
        return {
            "mode": "manual_fallback",
            "success": False,
            "reason": "No active flowsheet — cannot run auto setup.",
            "manual_instructions": manual["instructions"],
            "reactions": manual["reactions"],
            "reactor_tags": manual["reactor_tags"],
        }

    auto_result = setup_reactions(process_data)

    if auto_result.get("success"):
        return {
            "mode": "auto",
            "success": True,
            "auto_result": auto_result,
            "manual_instructions": manual["instructions"],
            "reactions": manual["reactions"],
            "reactor_tags": manual["reactor_tags"],
            "message": (
                "Reactions configured automatically. "
                "If the reactor stays red after Solve, use the manual instructions below."
            ),
        }
    else:
        return {
            "mode": "manual_fallback",
            "success": False,
            "auto_result": auto_result,
            "reason": auto_result.get("error", "Auto setup failed."),
            "manual_instructions": manual["instructions"],
            "reactions": manual["reactions"],
            "reactor_tags": manual["reactor_tags"],
            "message": (
                "Automatic reaction setup failed. "
                "Use the manual instructions below — it takes about 30 seconds in the DWSIM GUI."
            ),
        }


def build_process_from_library(process_data: dict, output_dir: str | None = None) -> dict:
    """
    High-level function: build and run a complete simulation from a
    process_library entry.

    Args:
        process_data: dict from process_library.lookup_process()
        output_dir:   directory to save .dwxmz file (default: outputs/)

    Returns comprehensive result dict.
    """
    if not process_data.get("found", False):
        return {"success": False, "error": "Process not found in library.",
                "detail": process_data}

    steps: list[dict] = []

    # Step 1: initialise
    r = initialize_dwsim()
    steps.append({"step": "initialise_dwsim", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # Step 2: create flowsheet
    r = create_flowsheet(
        compounds=process_data["compounds"],
        thermo_model=process_data["thermo_model"],
    )
    steps.append({"step": "create_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # Step 3: add unit operations (with graph-based layout)
    connections = process_data.get("connections", [])
    r = add_all_unit_operations(process_data["unit_operations"], connections)
    steps.append({"step": "add_unit_operations", **r})

    # Step 4: add inlet streams
    unit_positions = _compute_layout(process_data["unit_operations"], connections)
    r = add_material_streams(process_data["streams"], connections, unit_positions)
    steps.append({"step": "add_streams", **r})

    # Step 5: set stream conditions
    compounds = process_data["compounds"]
    for stream in process_data["streams"]:
        tag = stream["name"]
        comp_dict = stream.get("composition", {})

        # Build mole fraction array aligned to compound order
        frac_list = [comp_dict.get(c, 0.0) for c in compounds]
        # Normalise (should already sum to 1 but just in case)
        total = sum(frac_list) or 1.0
        frac_list = [f / total for f in frac_list]

        T_K = (stream.get("T_C", 25) + 273.15)
        P_Pa = (stream.get("P_bar", 1.0) * 1e5)
        flow_kg_s = stream.get("total_flow_kg_hr", 100) / 3600.0

        r = set_stream_conditions(
            tag=tag,
            temperature_K=T_K,
            pressure_Pa=P_Pa,
            mass_flow_kg_s=flow_kg_s,
            composition_mole_fracs=frac_list,
        )
        steps.append({"step": f"set_conditions_{tag}", **r})

    # Step 6: wire up connections
    r = connect_all(process_data["connections"])
    steps.append({"step": "connect_objects", **r})

    # Step 6b: create reaction sets and assign to reactors
    r = setup_reactions(process_data)
    steps.append({"step": "setup_reactions", **r})

    # Step 6c: apply unit operation specs (outlet temps, reflux ratios, pressures…)
    unit_op_specs = process_data.get("unit_op_specs", {})
    if unit_op_specs:
        r = configure_all_unit_ops(unit_op_specs)
        steps.append({"step": "configure_unit_ops", **r})

    # Step 7: run simulation
    r = run_simulation()
    steps.append({"step": "run_simulation", **r})
    sim_ok = r.get("success", False)

    # Step 8: collect results
    stream_results = get_stream_results()
    unit_results = get_unit_op_results()

    # Step 9: save
    out_dir = output_dir or os.path.join(
        os.path.dirname(__file__), "outputs"
    )
    chem_name = process_data.get("chemical", "process").replace(" ", "_")
    save_path = os.path.join(out_dir, f"{chem_name}_simulation.dwxmz")
    r = save_flowsheet(save_path)
    steps.append({"step": "save_flowsheet", **r})

    return {
        "success": sim_ok,
        "chemical": process_data.get("chemical"),
        "process_name": process_data.get("name"),
        "route": process_data.get("route"),
        "thermo_model": process_data.get("thermo_model"),
        "stream_results": stream_results.get("streams", {}),
        "unit_op_results": unit_results.get("unit_ops", {}),
        "saved_to": save_path if sim_ok else None,
        "steps": steps,
    }


# ─────────────────────────────────────────────
# 6. Diagnostic helpers
# ─────────────────────────────────────────────

def dwsim_status() -> dict:
    """Return current DWSIM availability and state."""
    return {
        "dwsim_path": DWSIM_PATH,
        "dwsim_found": DWSIM_PATH is not None,
        "dlls_loaded": _dwsim_loaded,
        "load_error": _dwsim_error,
        "flowsheet_active": _sim is not None,
        "objects_registered": list(_object_registry.keys()),
    }
