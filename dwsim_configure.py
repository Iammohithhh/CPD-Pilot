"""
dwsim_configure.py — Unit operation configuration and reaction setup.

Covers:
  - configure_unit_operation()
  - configure_all_unit_ops()
  - add_energy_stream_to_unit_op()
  - setup_reactions()
  - get_manual_reaction_instructions()
  - configure_reactions_with_fallback()
"""

from __future__ import annotations

import importlib
import traceback
import uuid

import dwsim_state as _st
from dwsim_loader import _suppress_native_stdout
from dwsim_flowsheet import add_unit_operation


# ── Unit operation configuration ─────────────────────────────────────────────

def configure_unit_operation(tag: str, specs: dict) -> dict:
    """
    Apply operating specs to any unit operation in the active flowsheet.

    Supported spec keys
    ───────────────────
    Heater / Cooler
        outlet_T_C, outlet_T_K, duty_kW, delta_P_bar

    Compressor / Pump / Expander
        outlet_P_bar, outlet_P_Pa, efficiency

    Valve
        outlet_P_bar, outlet_P_Pa

    Flash / Vessel
        P_bar, T_C, vapor_frac

    ShortcutColumn / DistillationColumn / AbsorptionColumn
        light_key, heavy_key, light_key_recovery, heavy_key_recovery,
        reflux_ratio, num_stages, condenser_type, condenser_P_bar, reboiler_P_bar

    ConversionReactor / EquilibriumReactor / CSTR / PFR
        outlet_T_C, outlet_T_K, outlet_P_bar

    Splitter
        split_fraction
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if tag not in _st._object_registry:
        return {"success": False, "error": f"Tag '{tag}' not found in flowsheet."}

    obj = _st._object_registry[tag]
    applied: list[str] = []
    skipped: list[str] = []

    def _try_set(attr_names, value, label: str) -> bool:
        for a in attr_names:
            try:
                setattr(obj, a, value)
                applied.append(f"{label} → {a}={value}")
                return True
            except Exception:
                pass
        skipped.append(f"{label}: none of {attr_names} accepted value {value}")
        return False

    obj_type = ""
    try:
        obj_type = obj.GraphicObject.ObjectType.ToString()
    except Exception:
        try:
            obj_type = type(obj).__name__
        except Exception:
            pass

    # ── Heater / Cooler ───────────────────────────────────────────────────────
    if "eater" in obj_type or "ooler" in obj_type or obj_type in ("Heater", "Cooler"):
        if "outlet_T_C" in specs or "outlet_T_K" in specs:
            T_K = (specs["outlet_T_K"] if "outlet_T_K" in specs
                   else specs["outlet_T_C"] + 273.15)
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
    elif any(k in obj_type for k in ("ompressor", "ump", "xpander")):
        if "outlet_P_bar" in specs or "outlet_P_Pa" in specs:
            P_Pa = (specs["outlet_P_Pa"] if "outlet_P_Pa" in specs
                    else specs["outlet_P_bar"] * 1e5)
            _try_set(["CalcMode"], 0, "CalcMode=OutletPressure")
            _try_set(["POut", "OutletPressure", "Pout"], P_Pa, "outlet_P_Pa")
        if "efficiency" in specs:
            _try_set(
                ["AdiabaticEfficiency", "Eficiencia",
                 "IsentropicEfficiency", "Efficiency"],
                specs["efficiency"], "efficiency",
            )

    # ── Valve ─────────────────────────────────────────────────────────────────
    elif "alve" in obj_type or obj_type == "Valve":
        if "outlet_P_bar" in specs or "outlet_P_Pa" in specs:
            P_Pa = (specs["outlet_P_Pa"] if "outlet_P_Pa" in specs
                    else specs["outlet_P_bar"] * 1e5)
            _try_set(["CalcMode", "CalculationMode"], 0, "CalcMode=OutletPressure")
            _try_set(["POut", "OutletPressure", "Pout"], P_Pa, "outlet_P_Pa")

    # ── Flash / Vessel ────────────────────────────────────────────────────────
    elif any(k in obj_type for k in ("essel", "lash", "eparator", "Tank")):
        if "P_bar" in specs:
            _try_set(
                ["FlashPressure", "Pressure", "OperatingPressure"],
                specs["P_bar"] * 1e5, "P_Pa",
            )
        if "T_C" in specs:
            _try_set(["FlashType", "CalculationMode"], 1, "FlashType=PT")
            _try_set(
                ["FlashTemperature", "Temperature", "OperatingTemperature"],
                specs["T_C"] + 273.15, "T_K",
            )
        elif "vapor_frac" in specs:
            _try_set(["FlashType", "CalculationMode"], 0, "FlashType=PV")
            _try_set(["VaporFraction", "VF"], specs["vapor_frac"], "vapor_frac")

    # ── Columns ───────────────────────────────────────────────────────────────
    elif any(k in obj_type for k in ("Column", "hortcut", "istillation", "bsorption")):
        if "light_key" in specs:
            _try_set(["LightKeyCompound", "LightKey", "ReferenceComponent"],
                     specs["light_key"], "light_key")
        if "heavy_key" in specs:
            _try_set(["HeavyKeyCompound", "HeavyKey"], specs["heavy_key"], "heavy_key")
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
            _try_set(["RefluxRatio", "ActualRefluxRatio", "RR"],
                     specs["reflux_ratio"], "reflux_ratio")
        if "num_stages" in specs:
            _try_set(
                ["NumberOfStages", "NumberOfTheoreticalStages", "N"],
                int(specs["num_stages"]), "num_stages",
            )
        if "condenser_type" in specs:
            _try_set(["CondenserType"], int(specs["condenser_type"]), "condenser_type")
        if "condenser_P_bar" in specs:
            _try_set(["CondenserPressure", "Pcondens", "Pcond"],
                     specs["condenser_P_bar"] * 1e5, "condenser_P_Pa")
        if "reboiler_P_bar" in specs:
            _try_set(["ReboilerPressure", "Preboiler", "Preb"],
                     specs["reboiler_P_bar"] * 1e5, "reboiler_P_Pa")

    # ── Reactors ──────────────────────────────────────────────────────────────
    elif any(k in obj_type for k in (
        "RCT_Conversion", "RCT_Equilibrium", "RCT_Gibbs", "RCT_CSTR", "RCT_PFR",
        "Reactor", "CSTR", "PFR",
    )):
        if "outlet_T_C" in specs or "outlet_T_K" in specs:
            T_K = (specs["outlet_T_K"] if "outlet_T_K" in specs
                   else specs["outlet_T_C"] + 273.15)
            # CalcMode 1 = isothermal — removes energy-stream requirement
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
            _try_set(
                ["OutletPressure", "POut", "ReactionPressure"],
                specs["outlet_P_bar"] * 1e5, "outlet_P_Pa",
            )

    # ── Splitter ──────────────────────────────────────────────────────────────
    elif "plitter" in obj_type or obj_type in ("NodeOut", "Splitter"):
        if "split_fraction" in specs:
            frac = float(specs["split_fraction"])
            ratio_set = False
            try:
                out_tags = []
                for conn in obj.GraphicObject.OutputConnectors:
                    try:
                        if conn.IsAttached:
                            attached_go = conn.AttachedConnector.AttachedFrom
                            for stag, sobj in _st._object_registry.items():
                                try:
                                    if sobj.GraphicObject is attached_go:
                                        out_tags.append(stag)
                                        break
                                except Exception:
                                    pass
                    except Exception:
                        pass

                if len(out_tags) >= 2:
                    for stag, ratio in {out_tags[0]: frac,
                                        out_tags[1]: 1.0 - frac}.items():
                        try:
                            obj.Ratios[stag] = ratio
                        except Exception:
                            pass
                    applied.append(f"Ratios: {out_tags[0]}={frac}, "
                                   f"{out_tags[1]}={1-frac}")
                    ratio_set = True
                elif len(out_tags) == 1:
                    try:
                        obj.Ratios[out_tags[0]] = frac
                        applied.append(f"Ratio set for {out_tags[0]}: {frac}")
                    except Exception:
                        pass
            except Exception as e:
                skipped.append(f"outlet-connector scan failed: {e}")

            if not ratio_set:
                _try_set(["SplitRatios"], [frac, 1.0 - frac], "split_fractions_list")

    else:
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
    """Apply a full {tag: specs} dict to the active flowsheet."""
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


# ── Energy stream helper ──────────────────────────────────────────────────────

def add_energy_stream_to_unit_op(unit_op_tag: str,
                                  energy_tag: str | None = None) -> dict:
    """
    Create an EnergyStream and connect it to the energy port of a unit operation.

    Only needed when the unit op is in EnergyStream CalcMode.
    For the common case (specify outlet temperature), use configure_unit_operation
    with outlet_T_C instead.
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if unit_op_tag not in _st._object_registry:
        return {"success": False, "error": f"Unit op '{unit_op_tag}' not found."}

    if energy_tag is None:
        energy_tag = f"ES-{unit_op_tag}"

    unit_obj = _st._object_registry[unit_op_tag]
    try:
        ex = int(unit_obj.GraphicObject.X) + 60
        ey = int(unit_obj.GraphicObject.Y) - 60
    except Exception:
        ex, ey = 300, 100

    r = add_unit_operation("EnergyStream", energy_tag, ex, ey)
    if not r.get("success"):
        return r

    e_obj = _st._object_registry[energy_tag]

    for src_port, dst_port in [(0, 2), (0, -1), (-1, -1)]:
        try:
            with _suppress_native_stdout():
                _st._interf.ConnectObjects(
                    _st._sim,
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
            f"EnergyStream '{energy_tag}' created but could not connect to "
            f"energy port of '{unit_op_tag}'. "
            "Use configure_unit_operation with outlet_T_C to avoid needing an energy stream."
        ),
    }


# ── Reaction setup ────────────────────────────────────────────────────────────

def setup_reactions(process_data: dict) -> dict:
    """
    Create DWSIM Reaction + ReactionSet objects and assign to reactors.

    Without this, ConversionReactor cannot converge and all downstream
    objects stay red.
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}

    reactions_data = process_data.get("reactions", [])
    if not reactions_data:
        return {"success": True, "message": "No reactions defined — skipping.", "added": 0}

    compounds = process_data.get("compounds", [])
    unit_ops  = process_data.get("unit_operations", [])
    _reactor_types = {
        "ConversionReactor", "EquilibriumReactor", "GibbsReactor", "CSTR", "PFR",
    }
    reactors = [op for op in unit_ops if op["type"] in _reactor_types]

    try:
        # ── Import reaction classes ───────────────────────────────────────────
        _Rxn = _RStoich = _RxnSet = None

        for mod_path, cls_name in [
            ("DWSIM.Thermodynamics.Reactions", "Reaction"),
            ("DWSIM.SharedClasses.Utility",    "Reaction"),
            ("DWSIM.SharedClasses",            "Reaction"),
        ]:
            try:
                mod = importlib.import_module(mod_path)
                _Rxn = getattr(mod, cls_name)
                break
            except Exception:
                pass

        if _Rxn is None:
            try:
                from DWSIM.Thermodynamics.Reactions import Reaction as _Rxn  # type: ignore
            except Exception:
                pass

        for mod_path, cls_name in [
            ("DWSIM.Thermodynamics.Reactions", "ReactionStoichimetry"),
            ("DWSIM.SharedClasses.Utility",    "ReactionStoichimetry"),
        ]:
            try:
                mod = importlib.import_module(mod_path)
                _RStoich = getattr(mod, cls_name)
                break
            except Exception:
                pass

        if _RStoich is None:
            try:
                from DWSIM.Thermodynamics.Reactions import ReactionStoichimetry as _RStoich  # type: ignore
            except Exception:
                pass

        for mod_path, cls_name in [
            ("DWSIM.SharedClasses.Utility", "ReactionSet"),
            ("DWSIM.SharedClasses",         "ReactionSet"),
        ]:
            try:
                mod = importlib.import_module(mod_path)
                _RxnSet = getattr(mod, cls_name)
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

        # ── Build ReactionSet ─────────────────────────────────────────────────
        rxnset = _RxnSet()
        rxnset_id   = str(uuid.uuid4())
        rxnset.ID   = rxnset_id
        rxnset.Name = f"{process_data.get('chemical', 'Process')} Reactions"

        added = []

        for i, rxn_data in enumerate(reactions_data):
            try:
                rxn = _Rxn()
                rxn_id   = str(uuid.uuid4())
                rxn.ID   = rxn_id
                rxn.Name = rxn_data.get("equation", f"Reaction {i+1}")

                rxn_type = rxn_data.get("type", "ConversionReactor")
                if rxn_type == "ConversionReactor":
                    try:
                        from DWSIM.Thermodynamics.Reactions import ReactionType as _RT  # type: ignore
                        rxn.ReactionType = _RT.Conversion
                    except Exception:
                        try:
                            rxn.ReactionType = 0
                        except Exception:
                            pass

                conversion = float(rxn_data.get("conversion", 0.05))
                for attr in ("Spec", "XFix", "ConversionSpec", "X_Conversion"):
                    try:
                        setattr(rxn, attr, conversion)
                    except Exception:
                        pass

                equation = rxn_data.get("equation", "")
                reactant_str, product_str = "", ""
                for sep in ["→", "->"]:
                    if sep in equation:
                        reactant_str, product_str = equation.split(sep, 1)
                        break

                base_set = False

                def _add_stoich(term_str: str, sign: int) -> None:
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
                                break

                if reactant_str:
                    _add_stoich(reactant_str, -1)
                if product_str:
                    _add_stoich(product_str, +1)

                _st._sim.Reactions.Add(rxn_id, rxn)
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

        _st._sim.ReactionSets.Add(rxnset_id, rxnset)

        assigned_to = []
        for reactor_op in reactors:
            tag = reactor_op["name"]
            obj = _st._object_registry.get(tag)
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
    Generate step-by-step GUI instructions for adding reactions in DWSIM.
    Always works regardless of DWSIM version or reaction complexity.
    """
    reactions   = process_data.get("reactions", [])
    unit_ops    = process_data.get("unit_operations", [])
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

    lines: list[str] = ["═" * 60, "  MANUAL REACTION SETUP — DWSIM GUI", "═" * 60, ""]
    lines += [
        "Step 1 — Open the Reactions Manager",
        "  In DWSIM menu: Data → Reactions",
        "  (Or press Ctrl+R in some versions)",
        "",
        "Step 2 — Add each reaction:",
        "",
    ]

    for i, rxn in enumerate(reactions, 1):
        eq       = rxn.get("equation", "")
        rxn_type = rxn.get("type", "ConversionReactor")
        t_c      = rxn.get("temperature_C", "")
        p_bar    = rxn.get("pressure_bar", "")
        conv     = rxn.get("conversion")
        catalyst = rxn.get("catalyst", "")

        if "Conversion" in rxn_type or rxn_type == "ConversionReactor":
            gui_type = "Conversion Reaction"
        elif "Equilibrium" in rxn_type:
            gui_type = "Equilibrium Reaction"
        elif "Gibbs" in rxn_type:
            gui_type = "Gibbs Reaction"
        else:
            gui_type = "Kinetic Reaction"

        lines += [
            f"  Reaction {i}: {eq}",
            f"    a) Click 'Add Reaction' → choose '{gui_type}'",
            f"    b) Enter equation: {eq}",
        ]
        if conv is not None:
            lines.append(f"    c) Set conversion to: {conv * 100:.0f}%")
        if t_c:
            lines.append(f"    d) Temperature: {t_c} °C")
        if p_bar:
            lines.append(f"    e) Pressure: {p_bar} bar")
        if catalyst:
            lines.append(f"    f) Note catalyst: {catalyst}")
        lines.append("")

    lines += [
        "Step 3 — Create a Reaction Set",
        "  In the Reactions Manager: click 'Add Reaction Set'",
        "  Tick all the reactions you just created",
        "  Name it (e.g. 'RXN-SET-01') → click OK",
        "",
        "Step 4 — Assign the Reaction Set to the reactor(s)",
    ]
    for rtag in reactor_tags:
        lines += [
            f"  Double-click reactor '{rtag}'",
            f"  → 'Reaction Set' dropdown → select 'RXN-SET-01'",
            f"  → click OK",
        ]
    lines += ["", "Step 5 — Press Solve (F5) and check results", "═" * 60]

    return {
        "instructions": "\n".join(lines),
        "reactions": reactions,
        "reactor_tags": reactor_tags,
        "reaction_count": len(reactions),
    }


def configure_reactions_with_fallback(process_data: dict) -> dict:
    """
    Try to set up reactions automatically; fall back to manual instructions.

    Returns mode="auto" on success or mode="manual_fallback" on failure.
    """
    manual = get_manual_reaction_instructions(process_data)

    if _st._sim is None:
        return {
            "mode": "manual_fallback",
            "success": False,
            "reason": "No active flowsheet.",
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
                "Use the manual instructions below — takes ~30 seconds in the DWSIM GUI."
            ),
        }
