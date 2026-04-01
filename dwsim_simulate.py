"""
dwsim_simulate.py — Run the DWSIM solver and retrieve stream/unit-op results.

Covers:
  - run_simulation()
  - get_stream_results()
  - get_unit_op_results()
"""

from __future__ import annotations

import traceback
from typing import Any

import dwsim_state as _st
from dwsim_loader import _suppress_native_stdout


def run_simulation(timeout_seconds: int = 120) -> dict:
    """
    Calculate (solve) the current flowsheet.
    Returns a dict with success flag and any solver errors.
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if _st._interf is None:
        return {"success": False, "error": "DWSIM interface not initialised."}

    try:
        with _suppress_native_stdout():
            _st._sim.AutoLayout()
            _st.Settings.SolverMode = 0   # synchronous

            if timeout_seconds and timeout_seconds > 0:
                try:
                    _st._interf.CalculateFlowsheet3(_st._sim, timeout_seconds)
                except Exception:
                    pass

            errors = _st._interf.CalculateFlowsheet4(_st._sim)

        error_list: list[str] = []
        if errors is not None:
            try:
                for e in errors:
                    error_list.append(str(e))
            except Exception:
                pass

        return {
            "success": len(error_list) == 0,
            "solver_errors": error_list,
            "message": (
                "Simulation complete." if not error_list
                else f"Simulation finished with {len(error_list)} error(s)."
            ),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def get_stream_results(tags: list[str] | None = None) -> dict:
    """
    Retrieve T, P, flow, and composition for material streams.

    Args:
        tags: stream tags to query; None = all registered objects

    Returns nested dict: {tag: {T_K, T_C, P_Pa, P_bar, mass_flow_kg_s, ...}}
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}

    query_tags = tags if tags is not None else list(_st._object_registry.keys())
    results: dict[str, Any] = {}

    for tag in query_tags:
        obj = _st._object_registry.get(tag)
        if obj is None:
            results[tag] = {"error": "Tag not found."}
            continue
        try:
            entry: dict[str, Any] = {}
            for getter, keys in [
                (lambda o: o.GetTemperature(), ("T_K",)),
                (lambda o: o.GetPressure(),    ("P_Pa",)),
                (lambda o: o.GetMassFlow(),    ("mass_flow_kg_s",)),
                (lambda o: o.GetMolarFlow(),   ("molar_flow_mol_s",)),
            ]:
                try:
                    val = getter(obj)
                    for k in keys:
                        entry[k] = val
                except Exception:
                    pass

            if "T_K" in entry:
                entry["T_C"] = entry["T_K"] - 273.15
            if "P_Pa" in entry:
                entry["P_bar"] = entry["P_Pa"] / 1e5
            if "mass_flow_kg_s" in entry:
                entry["mass_flow_kg_hr"] = entry["mass_flow_kg_s"] * 3600

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
    Retrieve key results from unit operations (duty, ΔP, conversion, etc.).
    Returns nested dict: {tag: {duty_kW, delta_P_Pa, outlet_T_K, ...}}
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}

    query_tags = tags if tags is not None else list(_st._object_registry.keys())
    results: dict[str, Any] = {}

    for tag in query_tags:
        obj = _st._object_registry.get(tag)
        if obj is None:
            results[tag] = {"error": "Tag not found."}
            continue
        entry: dict[str, Any] = {}
        for attr_name, key in [
            ("DeltaQ",           "duty_kW"),
            ("DeltaP",           "delta_P_Pa"),
            ("Pout",             "outlet_P_Pa"),
            ("OutletTemperature","outlet_T_K"),
            ("ConversionSpec",   "conversion"),
            ("EnergyBalance",    "energy_balance_kW"),
        ]:
            try:
                val = getattr(obj, attr_name, None)
                if val is not None:
                    entry[key] = float(val)
            except Exception:
                pass
        results[tag] = entry

    return {"success": True, "unit_ops": results}
