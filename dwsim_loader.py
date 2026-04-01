"""
dwsim_loader.py — DWSIM DLL discovery, loading, and Automation3 initialisation.

Handles:
  - Locating the DWSIM installation directory
  - Loading .NET assemblies via pythonnet / clr
  - Exposing ObjectType / PropertyPackage factory helpers
  - initialize_dwsim() entry point

All heavy state lives in dwsim_state so every other module shares it.
"""

from __future__ import annotations

import contextlib
import os
import sys
import json
import traceback

import dwsim_state as _st


@contextlib.contextmanager
def _suppress_native_stdout():
    """
    Temporarily redirect OS-level fd-1 (stdout) to /dev/null.

    .NET code loaded by pythonnet may call Console.WriteLine which writes
    directly to fd 1, bypassing Python's sys.stdout.  Under the MCP stdio
    transport this corrupts JSON-RPC framing.  We redirect fd 1 to devnull
    for the duration of the block, then restore it.
    """
    try:
        _saved = os.dup(1)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.close(devnull)
        yield
    except Exception:
        yield
    else:
        os.dup2(_saved, 1)
        os.close(_saved)


# ── Locate DWSIM installation ─────────────────────────────────────────────────

def _find_dwsim_path() -> str | None:
    """Return the DWSIM installation directory, or None if not found."""
    candidates: list[str] = []

    env_path = os.environ.get("DWSIM_PATH")
    if env_path:
        candidates.append(env_path)

    candidates += [
        r"C:\Users\{}\AppData\Local\DWSIM".format(os.environ.get("USERNAME", "")),
        r"C:\Program Files\DWSIM",
        r"C:\Program Files (x86)\DWSIM",
        "/opt/dwsim",
        "/usr/local/dwsim",
        os.path.expanduser("~/dwsim"),
    ]

    for p in candidates:
        if p and os.path.isfile(os.path.join(p, "DWSIM.Automation.dll")):
            return p
    return None


DWSIM_PATH = _find_dwsim_path()


# ── Load DLLs (lazy, once) ────────────────────────────────────────────────────

def _load_dwsim() -> bool:
    """
    Load DWSIM assemblies via pythonnet.
    Returns True on success, False on failure.
    Populates dwsim_state module-level namespace references on success.
    """
    if _st._dwsim_loaded:
        return True
    if _st._dwsim_error:
        return False

    if DWSIM_PATH is None:
        _st._dwsim_error = (
            "DWSIM installation not found. Set the DWSIM_PATH environment variable "
            "to the directory containing DWSIM.Automation.dll."
        )
        return False

    try:
        if sys.platform == "win32":
            try:
                import pythoncom  # type: ignore
                pythoncom.CoInitialize()
            except ImportError:
                pass

        _path_env = os.environ.get("PATH", "")
        if DWSIM_PATH not in _path_env.split(os.pathsep):
            os.environ["PATH"] = DWSIM_PATH + os.pathsep + _path_env

        # Generate a runtimeconfig that requests Microsoft.WindowsDesktop.App
        # (DWSIM needs WinForms assemblies that only ship with WindowsDesktop).
        try:
            from pythonnet import load as _pn_load  # type: ignore
            _rtconfig_path = os.path.join(
                os.environ.get("TEMP", os.path.expanduser("~")),
                "dwsim_windesktop.runtimeconfig.json",
            )
            with open(_rtconfig_path, "w") as _rf:
                json.dump(
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
            pass

        import clr       # type: ignore
        import System    # type: ignore

        # AssemblyResolve handler: resolve transitive DWSIM dependencies from
        # DWSIM_PATH so GetExportedTypes() never throws ReflectionTypeLoadException.
        def _resolve_dwsim_assembly(sender, args):  # noqa: ANN001
            short = args.Name.split(",")[0].strip()
            candidate = os.path.join(DWSIM_PATH, short + ".dll")
            if os.path.isfile(candidate):
                return System.Reflection.Assembly.LoadFrom(candidate)
            return None

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

            from DWSIM.Automation import Automation3 as _A3                         # type: ignore
            from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType as _OT     # type: ignore
            from DWSIM.Thermodynamics import PropertyPackages as _PP                # type: ignore
            from DWSIM.UnitOperations import UnitOperations as _UO                  # type: ignore
            from DWSIM.GlobalSettings import Settings as _S                         # type: ignore

            _st.Automation3       = _A3
            _st.ObjectType        = _OT
            _st.PropertyPackages  = _PP
            _st.UnitOperations    = _UO
            _st.Settings          = _S

        _st._dwsim_loaded = True
        return True

    except Exception as exc:
        _st._dwsim_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        return False


# ── ObjectType helpers ────────────────────────────────────────────────────────

def _ot(attr: str):
    """Return ObjectType.attr, falling back to ObjectType.OT_attr if needed."""
    val = getattr(_st.ObjectType, attr, None)
    if val is not None:
        return val
    val = getattr(_st.ObjectType, f"OT_{attr}", None)
    if val is not None:
        return val
    raise AttributeError(f"ObjectType has no attribute '{attr}' or 'OT_{attr}'")


def _obj_type(name: str):
    """Resolve a unit-op type name string to an ObjectType enum member."""
    if _st.ObjectType is None:
        raise RuntimeError("DWSIM not loaded")

    _MAP = {
        "MaterialStream":     _ot("MaterialStream"),
        "EnergyStream":       _ot("EnergyStream"),
        "Mixer":              _ot("NodeIn"),
        "Splitter":           _ot("NodeOut"),
        "Heater":             _ot("Heater"),
        "Cooler":             _ot("Cooler"),
        "HeatExchanger":      _ot("HeatExchanger"),
        "Valve":              _ot("Valve"),
        "Pump":               _ot("Pump"),
        "Compressor":         _ot("Compressor"),
        "Expander":           _ot("Expander"),
        "Pipe":               _ot("Pipe"),
        "Flash":              _ot("Vessel"),
        "Vessel":             _ot("Vessel"),
        "Tank":               _ot("Tank"),
        "Filter":             _ot("Filter"),
        "ShortcutColumn":     _ot("ShortcutColumn"),
        "DistillationColumn": _ot("DistillationColumn"),
        "AbsorptionColumn":   _ot("AbsorptionColumn"),
        "ConversionReactor":  _ot("RCT_Conversion"),
        "EquilibriumReactor": _ot("RCT_Equilibrium"),
        "GibbsReactor":       _ot("RCT_Gibbs"),
        "CSTR":               _ot("RCT_CSTR"),
        "PFR":                _ot("RCT_PFR"),
        "ComponentSeparator": _ot("ComponentSeparator"),
        "Recycle":            _ot("Recycle"),
    }
    if name in _MAP:
        return _MAP[name]

    _ALIASES = {
        "reactor": "ConversionReactor", "distillation": "DistillationColumn",
        "column": "DistillationColumn", "tower": "DistillationColumn",
        "absorber": "AbsorptionColumn", "stripper": "AbsorptionColumn",
        "heat exchanger": "HeatExchanger", "exchanger": "HeatExchanger",
        "separator": "Flash", "flash drum": "Flash", "drum": "Flash",
        "turbine": "Expander", "furnace": "Heater", "condenser": "Cooler",
        "reboiler": "Heater", "tee": "Splitter", "storage": "Tank",
        "filter": "Filter", "plug flow": "PFR", "stirred tank": "CSTR",
        "vaporizer": "Heater", "boiler": "Heater",
        "waste heat boiler": "HeatExchanger", "oxidizer": "ConversionReactor",
    }
    lower = name.lower().strip()
    for alias, canonical in _ALIASES.items():
        if alias in lower or lower in alias:
            return _MAP[canonical]

    raise ValueError(
        f"Unknown unit operation type: '{name}'. Available: {list(_MAP.keys())}"
    )


# ── Property-package factory ──────────────────────────────────────────────────

def _make_property_package(model_name: str):
    """Create and return a DWSIM property package instance."""
    if _st.PropertyPackages is None:
        raise RuntimeError("DWSIM not loaded")

    PP = _st.PropertyPackages
    _PP_MAP = {
        "Peng-Robinson": PP.PengRobinsonPropertyPackage,
        "PR":            PP.PengRobinsonPropertyPackage,
        "SRK":           PP.SRKPropertyPackage,
        "NRTL":          PP.NRTLPropertyPackage,
        "UNIQUAC":       PP.UNIQUACPropertyPackage,
        "UNIFAC":        PP.UNIFACPropertyPackage,
        "Steam Tables":  PP.SteamTablesPropertyPackage,
        "CoolProp":      PP.CoolPropPropertyPackage,
        "PRSV2":         PP.PRSV2PropertyPackage,
    }
    cls = _PP_MAP.get(model_name, PP.PengRobinsonPropertyPackage)
    return cls()


# ── Public initialiser ────────────────────────────────────────────────────────

def initialize_dwsim() -> dict:
    """Load DWSIM DLLs and create the Automation3 interface."""
    if not _load_dwsim():
        return {"success": False, "error": _st._dwsim_error}
    try:
        _st._interf = _st.Automation3()
        return {
            "success": True,
            "message": "DWSIM Automation3 initialised.",
            "dwsim_path": DWSIM_PATH,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
