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

import os
import sys
import json
import traceback
from pathlib import Path
from typing import Any

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
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()

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
def _obj_type(name: str):
    """Resolve a unit-op type name string to an ObjectType enum member."""
    if ObjectType is None:
        raise RuntimeError("DWSIM not loaded")

    _MAP = {
        "MaterialStream": ObjectType.MaterialStream,
        "EnergyStream": ObjectType.EnergyStream,
        "Mixer": ObjectType.NodeIn,         # legacy name for Mixer
        "Splitter": ObjectType.NodeOut,     # legacy name for Splitter
        "Heater": ObjectType.Heater,
        "Cooler": ObjectType.Cooler,
        "HeatExchanger": ObjectType.HeatExchanger,
        "Valve": ObjectType.Valve,
        "Pump": ObjectType.Pump,
        "Compressor": ObjectType.Compressor,
        "Expander": ObjectType.Expander,
        "Pipe": ObjectType.Pipe,
        "Flash": ObjectType.Vessel,         # Flash separator = Vessel
        "Vessel": ObjectType.Vessel,
        "Tank": ObjectType.Tank,
        "Filter": ObjectType.Filter,
        "ShortcutColumn": ObjectType.ShortcutColumn,
        "DistillationColumn": ObjectType.DistillationColumn,
        "AbsorptionColumn": ObjectType.AbsorptionColumn,
        "ConversionReactor": ObjectType.RCT_Conversion,
        "EquilibriumReactor": ObjectType.RCT_Equilibrium,
        "GibbsReactor": ObjectType.RCT_Gibbs,
        "CSTR": ObjectType.RCT_CSTR,
        "PFR": ObjectType.RCT_PFR,
        "ComponentSeparator": ObjectType.ComponentSeparator,
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
        obj_wrapper = _sim.AddObject(ot, x, y, tag)
        obj = obj_wrapper.GetAsObject()
        _object_registry[tag] = obj
        return {"success": True, "tag": tag, "type": op_type}
    except Exception as exc:
        return {"success": False, "tag": tag, "error": str(exc)}


def add_all_unit_operations(unit_ops: list[dict]) -> dict:
    """
    Batch-add unit operations from the process_library structure.

    Args:
        unit_ops: list of dicts with keys 'type', 'name', 'purpose'

    Returns summary dict.
    """
    results = []
    x, y = 50, 50
    x_step, y_step = 120, 0

    for i, op in enumerate(unit_ops):
        r = add_unit_operation(op["type"], op["name"], x + i * x_step, y + i * y_step)
        results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    return {
        "success": fail_count == 0,
        "added": success_count,
        "failed": fail_count,
        "details": results,
    }


def add_material_streams(streams: list[dict]) -> dict:
    """
    Add material/energy streams from the process_library stream list.

    Each stream dict has keys: name, type, T_C, P_bar, total_flow_kg_hr, composition
    """
    results = []
    x, y = 50, 200

    for i, s in enumerate(streams):
        stream_type = "MaterialStream" if s.get("type", "material") == "material" else "EnergyStream"
        r = add_unit_operation(stream_type, s["name"], x + i * 120, y)
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


def connect_objects(from_tag: str, to_tag: str) -> dict:
    """
    Connect two objects in the flowsheet (auto port selection).
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
        _sim.ConnectObjects(from_obj.GraphicObject, to_obj.GraphicObject, -1, -1)
        return {"success": True, "from": from_tag, "to": to_tag}
    except Exception as exc:
        return {"success": False, "from": from_tag, "to": to_tag, "error": str(exc)}


def connect_all(connections: list[tuple[str, str]]) -> dict:
    """
    Connect all object pairs from the process_library connections list.
    """
    results = []
    for (from_tag, to_tag) in connections:
        r = connect_objects(from_tag, to_tag)
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

    # Step 3: add unit operations
    r = add_all_unit_operations(process_data["unit_operations"])
    steps.append({"step": "add_unit_operations", **r})

    # Step 4: add inlet streams
    r = add_material_streams(process_data["streams"])
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
