"""
dwsim_tools.py — Public API re-export wrapper.

server.py imports this module as `_dwsim` and calls functions on it.
Everything now lives in focused sub-modules:

  dwsim_state.py      — shared globals (DLL handles, flowsheet, registry)
  dwsim_loader.py     — DLL loading, ObjectType helpers, property packages
  dwsim_flowsheet.py  — create/save/load flowsheet, add objects, connect
  dwsim_simulate.py   — run solver, read stream/unit-op results
  dwsim_configure.py  — configure unit ops, energy streams, reactions
  dwsim_build.py      — high-level builders (no-sim topology, full simulation)

This file simply re-exports everything so callers using
  import dwsim_tools as _dwsim
  _dwsim.some_function(...)
continue to work without modification.
"""

# ── Loader / initialisation ───────────────────────────────────────────────────
from dwsim_loader import (
    DWSIM_PATH,
    initialize_dwsim,
    _obj_type,
    _make_property_package,
    _suppress_native_stdout,
)

# ── Flowsheet: objects, layout, connections, save/load ────────────────────────
from dwsim_flowsheet import (
    create_flowsheet,
    add_unit_operation,
    add_all_unit_operations,
    add_material_streams,
    set_stream_conditions,
    connect_objects,
    connect_all,
    save_flowsheet,
    load_flowsheet,
    list_existing_objects,
    _compute_layout,
    _is_stream,
)

# ── Simulation: solver + results ──────────────────────────────────────────────
from dwsim_simulate import (
    run_simulation,
    get_stream_results,
    get_unit_op_results,
)

# ── Configuration: unit op specs, reactions ───────────────────────────────────
from dwsim_configure import (
    configure_unit_operation,
    configure_all_unit_ops,
    add_energy_stream_to_unit_op,
    setup_reactions,
    get_manual_reaction_instructions,
    configure_reactions_with_fallback,
)

# ── High-level builders ───────────────────────────────────────────────────────
from dwsim_build import (
    build_flowsheet_no_sim,
    build_process_from_library,
    modify_dwsim_file,
)


# ── Diagnostic ───────────────────────────────────────────────────────────────

def dwsim_status() -> dict:
    """Return current DWSIM availability and runtime state."""
    import dwsim_state as _st
    return {
        "dwsim_path":         DWSIM_PATH,
        "dwsim_found":        DWSIM_PATH is not None,
        "dlls_loaded":        _st._dwsim_loaded,
        "load_error":         _st._dwsim_error,
        "flowsheet_active":   _st._sim is not None,
        "objects_registered": list(_st._object_registry.keys()),
    }
