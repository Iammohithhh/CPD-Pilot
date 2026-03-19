"""
balance_reporter.py — Mass and energy balance reporters.

Takes DWSIM simulation results (or process_library data) and produces
formatted engineering tables for:
  1. Overall mass balance (every stream: flow, composition, T, P)
  2. Component mass balance (each compound across all streams)
  3. Energy balance (duties on every unit operation)
  4. Summary report (key metrics, closure check)

Output formats:
  - Plain text tables (for terminal / chat)
  - Dict/JSON (for programmatic use)
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────
# 1. Mass balance table
# ─────────────────────────────────────────────

def format_mass_balance(
    stream_results: dict[str, dict],
    compounds: list[str] | None = None,
    title: str = "MASS BALANCE",
) -> str:
    """
    Format a mass balance table from simulation stream results.

    Args:
        stream_results: dict of {tag: {T_K, T_C, P_Pa, P_bar,
                        mass_flow_kg_s, mass_flow_kg_hr,
                        mole_fractions, mass_fractions, ...}}
        compounds:      list of compound names (for column headers)
        title:          table title

    Returns:
        Formatted text table.
    """
    if not stream_results:
        return f"\n{title}\n{'='*40}\nNo stream data available.\n"

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 90)
    lines.append(f"  {title}")
    lines.append("=" * 90)
    lines.append("")

    # Header row
    header = f"{'Stream':<12} {'T (°C)':>8} {'P (bar)':>8} {'Flow (kg/hr)':>13}"
    if compounds:
        for c in compounds:
            short = c[:8]
            header += f" {short:>9}"
        header += "  (mole fractions)"
    lines.append(header)
    lines.append("-" * len(header))

    total_in = 0.0
    total_out = 0.0

    for tag, data in stream_results.items():
        if isinstance(data, dict) and "error" not in data:
            t_c = data.get("T_C", data.get("T_K", 0) - 273.15 if "T_K" in data else "—")
            p_bar = data.get("P_bar", data.get("P_Pa", 0) / 1e5 if "P_Pa" in data else "—")
            flow = data.get("mass_flow_kg_hr",
                           data.get("mass_flow_kg_s", 0) * 3600 if "mass_flow_kg_s" in data else "—")

            if isinstance(t_c, (int, float)):
                t_str = f"{t_c:>8.1f}"
            else:
                t_str = f"{'—':>8}"

            if isinstance(p_bar, (int, float)):
                p_str = f"{p_bar:>8.2f}"
            else:
                p_str = f"{'—':>8}"

            if isinstance(flow, (int, float)):
                f_str = f"{flow:>13.2f}"
                # Track totals
                if flow > 0:
                    total_in += flow  # simplified: positive = exists
            else:
                f_str = f"{'—':>13}"

            row = f"{tag:<12} {t_str} {p_str} {f_str}"

            # Add composition
            fracs = data.get("mole_fractions", [])
            if fracs and compounds:
                for i, c in enumerate(compounds):
                    if i < len(fracs):
                        row += f" {fracs[i]:>9.4f}"
                    else:
                        row += f" {'—':>9}"

            lines.append(row)
        else:
            lines.append(f"{tag:<12} {'(no data or error)':>40}")

    lines.append("-" * len(header) if header else "-" * 50)
    lines.append("")

    return "\n".join(lines)


def format_component_balance(
    stream_results: dict[str, dict],
    compounds: list[str],
    title: str = "COMPONENT MASS BALANCE",
) -> str:
    """
    Format a component-by-component mass balance table.

    Shows mass flow of each compound in each stream.
    """
    if not stream_results or not compounds:
        return f"\n{title}\n{'='*40}\nNo data available.\n"

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  {title}")
    lines.append("=" * 80)
    lines.append("")

    # Header
    header = f"{'Compound':<20}"
    tags = list(stream_results.keys())
    for tag in tags:
        header += f" {tag:>12}"
    header += f" {'Total':>12}"
    lines.append(header)
    lines.append("-" * len(header))

    # For each compound
    for i, compound in enumerate(compounds):
        row = f"{compound:<20}"
        total = 0.0
        for tag in tags:
            data = stream_results.get(tag, {})
            flow = data.get("mass_flow_kg_hr",
                           data.get("mass_flow_kg_s", 0) * 3600 if isinstance(data, dict) else 0)
            fracs = data.get("mass_fractions", []) if isinstance(data, dict) else []

            if isinstance(flow, (int, float)) and i < len(fracs):
                comp_flow = flow * fracs[i]
                row += f" {comp_flow:>12.2f}"
                total += comp_flow
            else:
                row += f" {'—':>12}"

        row += f" {total:>12.2f}"
        lines.append(row)

    lines.append("-" * len(header))
    lines.append("  (All flows in kg/hr)")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 2. Energy balance table
# ─────────────────────────────────────────────

def format_energy_balance(
    unit_op_results: dict[str, dict],
    process_data: dict | None = None,
    title: str = "ENERGY BALANCE",
) -> str:
    """
    Format an energy balance table from unit operation results.

    Args:
        unit_op_results: dict of {tag: {duty_kW, delta_P_Pa, ...}}
        process_data:    optional process_library dict for names/purposes
        title:           table title

    Returns:
        Formatted text table.
    """
    if not unit_op_results:
        return f"\n{title}\n{'='*40}\nNo unit operation data available.\n"

    # Build lookup for purposes
    purpose_map: dict[str, str] = {}
    type_map: dict[str, str] = {}
    if process_data:
        for op in process_data.get("unit_operations", []):
            purpose_map[op["name"]] = op.get("purpose", "")
            type_map[op["name"]] = op.get("type", "")

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 90)
    lines.append(f"  {title}")
    lines.append("=" * 90)
    lines.append("")

    header = (
        f"{'Equipment':<12} {'Type':<20} {'Duty (kW)':>12} "
        f"{'ΔP (bar)':>10} {'Purpose'}"
    )
    lines.append(header)
    lines.append("-" * max(len(header), 80))

    total_heating = 0.0
    total_cooling = 0.0
    total_work = 0.0

    for tag, data in unit_op_results.items():
        if not isinstance(data, dict) or "error" in data:
            continue

        eq_type = type_map.get(tag, "")
        duty = data.get("duty_kW")
        delta_p = data.get("delta_P_Pa")
        purpose = purpose_map.get(tag, "")[:35]

        duty_str = f"{duty:>12.2f}" if duty is not None else f"{'—':>12}"
        dp_str = f"{delta_p/1e5:>10.2f}" if delta_p is not None else f"{'—':>10}"

        lines.append(f"{tag:<12} {eq_type:<20} {duty_str} {dp_str} {purpose}")

        # Categorise duties
        if duty is not None:
            if eq_type in ("Cooler",):
                total_cooling += abs(duty)
            elif eq_type in ("Pump", "Compressor"):
                total_work += abs(duty)
            elif eq_type in ("Expander",):
                total_work -= abs(duty)  # recovered
            else:
                # Heaters, reactors, and anything else
                if duty > 0:
                    total_heating += duty
                else:
                    total_cooling += abs(duty)

    lines.append("-" * max(len(header), 80))
    lines.append("")
    lines.append("  ENERGY SUMMARY:")
    lines.append(f"    Total heating duty:  {total_heating:>12.2f} kW")
    lines.append(f"    Total cooling duty:  {total_cooling:>12.2f} kW")
    lines.append(f"    Total shaft work:    {total_work:>12.2f} kW")
    lines.append(f"    Net energy input:    {total_heating + total_work:>12.2f} kW")

    if total_heating > 0 and total_cooling > 0:
        recovery_potential = min(total_heating, total_cooling)
        lines.append(
            f"    Heat integration potential: up to {recovery_potential:.1f} kW "
            f"({recovery_potential / max(total_heating, 1) * 100:.0f}% of heating)"
        )
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 3. Summary report
# ─────────────────────────────────────────────

def format_summary_report(
    process_data: dict,
    stream_results: dict[str, dict] | None = None,
    unit_op_results: dict[str, dict] | None = None,
) -> str:
    """
    Generate a comprehensive summary report combining process info,
    mass balance, and energy balance.

    Can work with:
    - Just process_data (pre-simulation summary)
    - With simulation results (post-simulation report)
    """
    lines: list[str] = []

    # ─── Header ───
    lines.append("")
    lines.append("╔" + "═" * 88 + "╗")
    name = process_data.get("name", "Chemical Process")
    lines.append(f"║  PROCESS SIMULATION REPORT: {name:<57} ║")
    lines.append("╠" + "═" * 88 + "╣")

    # ─── Process overview ───
    lines.append(f"║  Route:        {process_data.get('route', 'N/A'):<71} ║")
    lines.append(f"║  Thermo Model: {process_data.get('thermo_model', 'N/A'):<71} ║")
    compounds = process_data.get("compounds", [])
    comp_str = ", ".join(compounds[:6])
    if len(compounds) > 6:
        comp_str += f" (+{len(compounds)-6} more)"
    lines.append(f"║  Compounds:    {comp_str:<71} ║")
    lines.append("╠" + "═" * 88 + "╣")

    # ─── Reactions ───
    lines.append(f"║  {'REACTIONS':^86} ║")
    lines.append("╠" + "─" * 88 + "╣")
    for rxn in process_data.get("reactions", []):
        eq = rxn.get("equation", "")[:60]
        lines.append(f"║  {eq:<86} ║")
        details = f"  Type: {rxn.get('type', '?')}  |  T: {rxn.get('temperature_C', '?')}°C  |  P: {rxn.get('pressure_bar', '?')} bar"
        if "conversion" in rxn:
            details += f"  |  Conv: {rxn['conversion']*100:.0f}%"
        lines.append(f"║  {details:<86} ║")
        lines.append(f"║  {'Catalyst: ' + rxn.get('catalyst', 'N/A'):<86} ║")
        lines.append("║" + " " * 88 + "║")

    lines.append("╠" + "═" * 88 + "╣")

    # ─── Unit Operations ───
    lines.append(f"║  {'UNIT OPERATIONS':^86} ║")
    lines.append("╠" + "─" * 88 + "╣")
    for op in process_data.get("unit_operations", []):
        op_line = f"{op['name']:<10} [{op['type']:<22}]  {op.get('purpose', '')}"
        lines.append(f"║  {op_line:<86} ║")

    lines.append("╠" + "═" * 88 + "╣")

    # ─── Feed streams ───
    lines.append(f"║  {'FEED STREAMS':^86} ║")
    lines.append("╠" + "─" * 88 + "╣")
    for s in process_data.get("streams", []):
        comp = s.get("composition", {})
        comp_parts = [f"{k}: {v*100:.0f}%" for k, v in comp.items() if v > 0]
        comp_str = ", ".join(comp_parts) if comp_parts else "not specified"
        s_line = (
            f"{s['name']:<8} T={s.get('T_C', 25):>6.0f}°C  "
            f"P={s.get('P_bar', 1):>6.1f} bar  "
            f"Flow={s.get('total_flow_kg_hr', '?'):>8} kg/hr"
        )
        lines.append(f"║  {s_line:<86} ║")
        lines.append(f"║    Composition: {comp_str:<70} ║")

    lines.append("╠" + "═" * 88 + "╣")

    # ─── Simulation results (if available) ───
    if stream_results:
        lines.append(f"║  {'SIMULATION RESULTS - STREAM TABLE':^86} ║")
        lines.append("╠" + "─" * 88 + "╣")

        for tag, data in stream_results.items():
            if isinstance(data, dict) and "error" not in data:
                t_c = data.get("T_C", "—")
                p_bar = data.get("P_bar", "—")
                flow_hr = data.get("mass_flow_kg_hr", "—")

                t_str = f"{t_c:.1f}" if isinstance(t_c, (int, float)) else str(t_c)
                p_str = f"{p_bar:.2f}" if isinstance(p_bar, (int, float)) else str(p_bar)
                f_str = f"{flow_hr:.2f}" if isinstance(flow_hr, (int, float)) else str(flow_hr)

                s_line = f"{tag:<12} T={t_str:>8}°C  P={p_str:>8} bar  Flow={f_str:>10} kg/hr"
                lines.append(f"║  {s_line:<86} ║")

                fracs = data.get("mole_fractions", [])
                if fracs and compounds:
                    frac_parts = []
                    for i, c in enumerate(compounds):
                        if i < len(fracs) and fracs[i] > 0.001:
                            frac_parts.append(f"{c}: {fracs[i]:.4f}")
                    if frac_parts:
                        frac_line = "    x: " + ", ".join(frac_parts)
                        # Split if too long
                        while frac_line:
                            chunk = frac_line[:84]
                            lines.append(f"║  {chunk:<86} ║")
                            frac_line = frac_line[84:]

        lines.append("╠" + "═" * 88 + "╣")

    if unit_op_results:
        lines.append(f"║  {'SIMULATION RESULTS - EQUIPMENT DUTIES':^86} ║")
        lines.append("╠" + "─" * 88 + "╣")

        total_q = 0.0
        for tag, data in unit_op_results.items():
            if isinstance(data, dict) and data:
                duty = data.get("duty_kW")
                dp = data.get("delta_P_Pa")

                parts = [f"{tag:<12}"]
                if duty is not None:
                    parts.append(f"Q = {duty:>10.2f} kW")
                    total_q += duty
                if dp is not None:
                    parts.append(f"ΔP = {dp/1e5:>8.2f} bar")

                if len(parts) > 1:
                    eq_line = "  ".join(parts)
                    lines.append(f"║  {eq_line:<86} ║")

        lines.append("║" + " " * 88 + "║")
        lines.append(f"║  {'Total energy duty: ' + f'{total_q:.2f} kW':<86} ║")

    # ─── Notes ───
    notes = process_data.get("notes", "")
    if notes:
        lines.append("╠" + "═" * 88 + "╣")
        lines.append(f"║  {'PROCESS NOTES':^86} ║")
        lines.append("╠" + "─" * 88 + "╣")
        # Word wrap
        words = notes.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 84:
                current_line += (" " if current_line else "") + word
            else:
                lines.append(f"║  {current_line:<86} ║")
                current_line = word
        if current_line:
            lines.append(f"║  {current_line:<86} ║")

    # ─── Footer ───
    lines.append("╚" + "═" * 88 + "╝")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 4. JSON / dict versions for programmatic use
# ─────────────────────────────────────────────

def compute_mass_balance_data(
    stream_results: dict[str, dict],
    compounds: list[str],
) -> dict:
    """
    Compute a structured mass balance dict.

    Returns:
        {
            "streams": {tag: {total_kg_hr, component_flows: {compound: kg_hr}}},
            "totals": {compound: total_kg_hr},
            "total_flow_kg_hr": float,
        }
    """
    result: dict[str, Any] = {"streams": {}, "totals": {}, "total_flow_kg_hr": 0.0}

    compound_totals: dict[str, float] = {c: 0.0 for c in compounds}
    grand_total = 0.0

    for tag, data in stream_results.items():
        if not isinstance(data, dict) or "error" in data:
            continue

        flow = data.get("mass_flow_kg_hr",
                       data.get("mass_flow_kg_s", 0) * 3600 if "mass_flow_kg_s" in data else 0)
        mass_fracs = data.get("mass_fractions", [])

        stream_entry: dict[str, Any] = {
            "total_kg_hr": flow,
            "component_flows": {},
        }

        for i, compound in enumerate(compounds):
            if i < len(mass_fracs):
                comp_flow = flow * mass_fracs[i]
            else:
                comp_flow = 0.0
            stream_entry["component_flows"][compound] = comp_flow
            compound_totals[compound] = compound_totals.get(compound, 0) + comp_flow

        grand_total += flow
        result["streams"][tag] = stream_entry

    result["totals"] = compound_totals
    result["total_flow_kg_hr"] = grand_total

    return result


def compute_energy_balance_data(
    unit_op_results: dict[str, dict],
    process_data: dict | None = None,
) -> dict:
    """
    Compute a structured energy balance dict.

    Returns:
        {
            "equipment": {tag: {type, duty_kW, delta_P_bar}},
            "summary": {total_heating_kW, total_cooling_kW, total_work_kW,
                        net_energy_kW, heat_integration_potential_kW},
        }
    """
    type_map: dict[str, str] = {}
    if process_data:
        for op in process_data.get("unit_operations", []):
            type_map[op["name"]] = op.get("type", "")

    equipment: dict[str, Any] = {}
    total_heating = 0.0
    total_cooling = 0.0
    total_work = 0.0

    for tag, data in unit_op_results.items():
        if not isinstance(data, dict) or "error" in data:
            continue

        eq_type = type_map.get(tag, "")
        duty = data.get("duty_kW")
        dp = data.get("delta_P_Pa")

        equipment[tag] = {
            "type": eq_type,
            "duty_kW": duty,
            "delta_P_bar": dp / 1e5 if dp is not None else None,
        }

        if duty is not None:
            if eq_type in ("Cooler",):
                total_cooling += abs(duty)
            elif eq_type in ("Pump", "Compressor"):
                total_work += abs(duty)
            elif eq_type in ("Expander",):
                total_work -= abs(duty)
            else:
                if duty > 0:
                    total_heating += duty
                else:
                    total_cooling += abs(duty)

    return {
        "equipment": equipment,
        "summary": {
            "total_heating_kW": total_heating,
            "total_cooling_kW": total_cooling,
            "total_work_kW": total_work,
            "net_energy_input_kW": total_heating + total_work,
            "heat_integration_potential_kW": min(total_heating, total_cooling),
        },
    }
