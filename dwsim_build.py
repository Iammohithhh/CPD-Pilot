"""
dwsim_build.py — High-level flowsheet builders.

Covers:
  - build_flowsheet_no_sim()  ← V1 entry point: topology only, no solver
  - build_process_from_library()
  - modify_dwsim_file()
"""

from __future__ import annotations

import os

import dwsim_state as _st
from dwsim_loader import initialize_dwsim, DWSIM_PATH
from dwsim_flowsheet import (
    create_flowsheet,
    add_all_unit_operations,
    add_material_streams,
    set_stream_conditions,
    connect_all,
    save_flowsheet,
    load_flowsheet,
    list_existing_objects,
    add_unit_operation,
    connect_objects,
    _compute_layout,
)
from dwsim_simulate import run_simulation, get_stream_results, get_unit_op_results
from dwsim_configure import (
    configure_all_unit_ops,
    setup_reactions,
    configure_reactions_with_fallback,
)


# ── V1: topology-only build (user fills values manually) ─────────────────────

def build_flowsheet_no_sim(
    process_data: dict,
    output_dir: str | None = None,
) -> dict:
    """
    Build a DWSIM flowsheet topology WITHOUT running the solver.

    This is the V1 workflow:
      1. Initialise DWSIM
      2. Create flowsheet (compounds + thermo model)
      3. Add unit operations
      4. Add feed / intermediate streams
      5. Wire all connections
      6. Save .dwxmz

    The student opens the saved file in the DWSIM GUI, enters stream
    conditions (T, P, flow, composition), then presses Solve themselves.

    Args:
        process_data: process_library-compatible dict with at minimum:
                      compounds, thermo_model, unit_operations, streams,
                      connections.
        output_dir:   output directory (default: outputs/ next to this file)

    Returns result dict including file_path and topology_summary.
    """
    steps: list[dict] = []

    # 1. Initialise
    r = initialize_dwsim()
    steps.append({"step": "initialise_dwsim", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # 2. Create flowsheet
    compounds    = process_data.get("compounds", [])
    thermo_model = process_data.get("thermo_model", "Peng-Robinson")
    r = create_flowsheet(compounds=compounds, thermo_model=thermo_model)
    steps.append({"step": "create_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    # 3. Add unit operations (graph-based layout)
    unit_ops    = process_data.get("unit_operations", [])
    connections = process_data.get("connections", [])
    r = add_all_unit_operations(unit_ops, connections)
    steps.append({"step": "add_unit_operations", **r})
    if r.get("added", 0) == 0 and unit_ops:
        return {"success": False, "error": "All unit operations failed to add.",
                "steps": steps}

    # 4. Add streams
    unit_positions = _compute_layout(unit_ops, connections)
    streams = process_data.get("streams", [])
    r = add_material_streams(streams, connections, unit_positions)
    steps.append({"step": "add_streams", **r})

    # 5. Wire connections
    conn_result = connect_all(connections)
    steps.append({"step": "connect_objects", **conn_result})

    # 6. Save (no simulation)
    out_dir = output_dir or os.path.join(os.path.dirname(__file__), "outputs")
    chem_name = (
        process_data.get("chemical", "process")
        .replace(" ", "_").replace("/", "_")
    )
    save_path = os.path.join(out_dir, f"{chem_name}_topology.dwxmz")
    r = save_flowsheet(save_path)
    steps.append({"step": "save_flowsheet", **r})

    # Build human-readable topology summary
    unit_summary   = [{"tag": u.get("name",""), "type": u.get("type",""),
                        "purpose": u.get("purpose","")} for u in unit_ops]
    stream_summary = [{"tag": s.get("name",""), "type": s.get("type","material")}
                      for s in streams]
    conn_lines     = [f"  {c[0]} → {c[1]}" if len(c) >= 2 else str(c)
                      for c in connections]

    topology_text = (
        f"Compounds : {', '.join(compounds)}\n"
        f"Thermo    : {thermo_model}\n"
        f"Units     : {len(unit_ops)}\n"
        + "\n".join(f"  [{u['type']}] {u['tag']}  — {u['purpose']}"
                    for u in unit_summary)
        + f"\nStreams   : {len(stream_summary)}\n"
        + "\n".join(f"  {s['tag']} ({s['type']})" for s in stream_summary)
        + "\nConnections:\n"
        + "\n".join(conn_lines)
    )

    save_ok      = r.get("success", False)
    conn_failed  = conn_result.get("failed", 0)
    conn_total   = conn_result.get("connected", 0) + conn_failed
    conn_warning = ""
    if conn_failed > 0:
        failed_details = [
            d for d in conn_result.get("details", []) if not d.get("success")
        ]
        failed_summary = "; ".join(
            f"{d.get('from','?')}→{d.get('to','?')}: {d.get('error','unknown')}"
            for d in failed_details[:5]
        )
        conn_warning = (
            f"\n\nWARNING: {conn_failed}/{conn_total} connections failed. "
            f"Details: {failed_summary}"
        )

    return {
        "success": save_ok,
        "file_path": save_path if save_ok else None,
        "connections_wired": conn_result.get("connected", 0),
        "connections_failed": conn_failed,
        "connection_warning": conn_warning or None,
        "topology_summary": topology_text + conn_warning,
        "unit_operations": unit_summary,
        "streams": stream_summary,
        "connections": connections,
        "steps": steps,
        "next_steps": (
            "Topology saved. Open the .dwxmz file in DWSIM. "
            "Double-click each feed stream to enter T, P, flow, and composition, "
            "then press Solve (F5) to run the simulation."
        ),
    }


# ── Full simulation build from library ───────────────────────────────────────

def build_process_from_library(
    process_data: dict,
    output_dir: str | None = None,
) -> dict:
    """
    High-level: build and run a complete simulation from a process_library entry.

    Steps: initialise → create flowsheet → add unit ops → add streams →
           set stream conditions → wire connections → setup reactions →
           configure unit ops → run solver → collect results → save.
    """
    if not process_data.get("found", False):
        return {"success": False, "error": "Process not found in library.",
                "detail": process_data}

    steps: list[dict] = []

    r = initialize_dwsim()
    steps.append({"step": "initialise_dwsim", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    r = create_flowsheet(
        compounds=process_data["compounds"],
        thermo_model=process_data["thermo_model"],
    )
    steps.append({"step": "create_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    connections = process_data.get("connections", [])

    r = add_all_unit_operations(process_data["unit_operations"], connections)
    steps.append({"step": "add_unit_operations", **r})

    unit_positions = _compute_layout(process_data["unit_operations"], connections)
    r = add_material_streams(process_data["streams"], connections, unit_positions)
    steps.append({"step": "add_streams", **r})

    compounds = process_data["compounds"]
    for stream in process_data["streams"]:
        tag = stream["name"]
        comp_dict = stream.get("composition", {})
        frac_list = [comp_dict.get(c, 0.0) for c in compounds]
        total = sum(frac_list) or 1.0
        frac_list = [f / total for f in frac_list]

        r = set_stream_conditions(
            tag=tag,
            temperature_K=stream.get("T_C", 25) + 273.15,
            pressure_Pa=stream.get("P_bar", 1.0) * 1e5,
            mass_flow_kg_s=stream.get("total_flow_kg_hr", 100) / 3600.0,
            composition_mole_fracs=frac_list,
        )
        steps.append({"step": f"set_conditions_{tag}", **r})

    r = connect_all(connections)
    steps.append({"step": "connect_objects", **r})

    r = setup_reactions(process_data)
    steps.append({"step": "setup_reactions", **r})

    unit_op_specs = process_data.get("unit_op_specs", {})
    if unit_op_specs:
        r = configure_all_unit_ops(unit_op_specs)
        steps.append({"step": "configure_unit_ops", **r})

    r = run_simulation()
    steps.append({"step": "run_simulation", **r})
    sim_ok = r.get("success", False)

    stream_results = get_stream_results()
    unit_results   = get_unit_op_results()

    out_dir   = output_dir or os.path.join(os.path.dirname(__file__), "outputs")
    chem_name = process_data.get("chemical", "process").replace(" ", "_")
    save_path = os.path.join(out_dir, f"{chem_name}_simulation.dwxmz")
    r = save_flowsheet(save_path)
    steps.append({"step": "save_flowsheet", **r})

    return {
        "success": sim_ok,
        "chemical":      process_data.get("chemical"),
        "process_name":  process_data.get("name"),
        "route":         process_data.get("route"),
        "thermo_model":  process_data.get("thermo_model"),
        "stream_results":  stream_results.get("streams", {}),
        "unit_op_results": unit_results.get("unit_ops", {}),
        "saved_to": save_path if sim_ok else None,
        "steps": steps,
    }


# ── Modify an existing flowsheet file ────────────────────────────────────────

def modify_dwsim_file(
    file_path: str,
    add_unit_ops: list[dict] | None = None,
    add_connections: list[tuple] | None = None,
    output_path: str | None = None,
) -> dict:
    """
    Load an existing .dwxmz file, add unit ops/connections, and save.

    Args:
        file_path:       path to existing .dwxmz / .dwxml
        add_unit_ops:    list of {type, name, x (opt), y (opt)}
        add_connections: list of (from_tag, to_tag) tuples
        output_path:     save path (defaults to file_path)
    """
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    steps: list[dict] = []

    r = load_flowsheet(file_path)
    steps.append({"step": "load_flowsheet", **r})
    if not r["success"]:
        return {"success": False, "steps": steps}

    r = list_existing_objects()
    steps.append({"step": "list_existing_objects", **r})
    existing_tags = r.get("tags", [])

    added_ops: list[dict] = []
    if add_unit_ops:
        for op in add_unit_ops:
            op_type = op.get("type", "")
            tag     = op.get("name", op.get("tag", ""))
            x       = int(op.get("x", 100))
            y       = int(op.get("y", 100))
            if not op_type or not tag:
                added_ops.append({"error": f"Missing type or name in {op}"})
                continue
            added_ops.append(add_unit_operation(op_type, tag, x, y))
        steps.append({"step": "add_unit_operations", "results": added_ops})

    conn_results: list[dict] = []
    if add_connections:
        for conn in add_connections:
            if len(conn) >= 2:
                conn_results.append(connect_objects(str(conn[0]), str(conn[1])))
        steps.append({"step": "add_connections", "results": conn_results})

    save_to = output_path or file_path
    r = save_flowsheet(save_to)
    steps.append({"step": "save_flowsheet", **r})

    return {
        "success": r.get("success", False),
        "loaded_from":       file_path,
        "saved_to":          save_to,
        "existing_objects":  existing_tags,
        "unit_ops_added":    [o.get("tag") for o in added_ops if o.get("success")],
        "connections_added": [
            f"{c.get('from')} → {c.get('to')}"
            for c in conn_results if c.get("success")
        ],
        "steps": steps,
    }
