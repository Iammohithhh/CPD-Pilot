"""
dwsim_flowsheet.py — Flowsheet creation, object management, and connections.

Covers:
  - create_flowsheet()
  - add_unit_operation() / add_all_unit_operations()
  - _compute_layout()
  - add_material_streams() / set_stream_conditions()
  - _is_stream()   ← BUG FIX: now handles OT_ enum prefix correctly
  - connect_objects() / connect_all()
  - save_flowsheet() / load_flowsheet() / list_existing_objects()
"""

from __future__ import annotations

import traceback
from collections import defaultdict
from typing import Any

import dwsim_state as _st
from dwsim_loader import (
    _suppress_native_stdout,
    _obj_type,
    _make_property_package,
    initialize_dwsim,
)


# ── Flowsheet creation ────────────────────────────────────────────────────────

def create_flowsheet(compounds: list[str], thermo_model: str) -> dict:
    """
    Create a new empty DWSIM flowsheet, add compounds and property package.

    Args:
        compounds:    list of compound names (must match DWSIM database)
        thermo_model: e.g. "Peng-Robinson", "NRTL"
    """
    if _st._interf is None:
        r = initialize_dwsim()
        if not r["success"]:
            return r

    try:
        with _suppress_native_stdout():
            _st._sim = _st._interf.CreateFlowsheet()
            _st._object_registry = {}

            added, missing = [], []
            for cname in compounds:
                try:
                    _st._sim.AddCompound(cname)
                    added.append(cname)
                except Exception:
                    try:
                        comp = _st._sim.AvailableCompounds[cname]
                        _st._sim.SelectedCompounds.Add(comp.Name, comp)
                        added.append(cname)
                    except Exception:
                        missing.append(cname)

            pp = _make_property_package(thermo_model)
            _st._sim.AddPropertyPackage(pp)

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


# ── Add a single object ───────────────────────────────────────────────────────

def add_unit_operation(op_type: str, tag: str, x: int = 100, y: int = 100) -> dict:
    """
    Add a unit operation or stream to the current flowsheet.

    Args:
        op_type: type string e.g. "Heater", "MaterialStream", "Flash"
        tag:     unique tag / name e.g. "H-101", "S-01"
        x, y:    canvas coordinates
    """
    if _st._sim is None:
        return {"success": False,
                "error": "No flowsheet active. Call create_flowsheet first."}

    try:
        ot = _obj_type(op_type)
        with _suppress_native_stdout():
            obj_wrapper = _st._sim.AddObject(ot, x, y, tag)
            obj = obj_wrapper.GetAsObject()
        _st._object_registry[tag] = obj

        try:
            go = obj.GraphicObject
            go.X = int(x)
            go.Y = int(y)
        except Exception:
            pass

        return {"success": True, "tag": tag, "type": op_type}
    except Exception as exc:
        return {"success": False, "tag": tag, "error": str(exc)}


# ── Layout computation ────────────────────────────────────────────────────────

def _compute_layout(
    unit_ops: list[dict],
    connections: list | None = None,
) -> dict[str, tuple[int, int]]:
    """
    Compute canvas positions based on connection topology (BFS/DFS).
    Falls back to a grid when no connections provided.
    Returns {tag: (x, y)}.
    """
    all_tags = [op["name"] for op in unit_ops]

    if not connections:
        positions = {}
        cols = 5
        x_step, y_step = 150, 120
        for i, tag in enumerate(all_tags):
            col = i % cols
            row = i // cols
            positions[tag] = (60 + col * x_step, 60 + row * y_step)
        return positions

    tag_set = set(all_tags)
    successors:   dict[str, list[str]] = {t: [] for t in all_tags}
    predecessors: dict[str, list[str]] = {t: [] for t in all_tags}

    for conn in connections:
        if len(conn) < 2:
            continue
        src, dst = str(conn[0]), str(conn[1])
        if src in tag_set and dst in tag_set:
            successors[src].append(dst)
            predecessors[dst].append(src)

    sources = [t for t in all_tags if len(predecessors[t]) == 0] or [all_tags[0]]

    column: dict[str, int] = {}
    _visiting: set[str] = set()

    def _dfs(node: str, depth: int) -> None:
        if node in _visiting:
            return
        if node in column and column[node] >= depth:
            return
        column[node] = max(column.get(node, 0), depth)
        _visiting.add(node)
        for nxt in successors.get(node, []):
            _dfs(nxt, depth + 1)
        _visiting.discard(node)

    for s in sources:
        _dfs(s, 0)

    max_col = max(column.values()) if column else 0
    for t in all_tags:
        if t not in column:
            max_col += 1
            column[t] = max_col

    col_groups: dict[int, list[str]] = defaultdict(list)
    for t in all_tags:
        col_groups[column[t]].append(t)

    x_step, y_step = 160, 100
    x_start, y_start = 60, 60
    positions = {}
    for col_idx in sorted(col_groups.keys()):
        members = col_groups[col_idx]
        total_height = (len(members) - 1) * y_step
        y_offset = y_start + max(0, (200 - total_height) // 2)
        for row_idx, tag in enumerate(members):
            positions[tag] = (x_start + col_idx * x_step, y_offset + row_idx * y_step)

    return positions


# ── Batch add unit operations ─────────────────────────────────────────────────

def add_all_unit_operations(
    unit_ops: list[dict],
    connections: list | None = None,
) -> dict:
    """
    Batch-add unit operations from process_library structure.
    Uses graph-based layout when connections are provided.
    """
    positions = _compute_layout(unit_ops, connections)
    results = []
    for op in unit_ops:
        tag = op["name"]
        px, py = positions.get(tag, (100, 100))
        results.append(add_unit_operation(op["type"], tag, px, py))

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": (len(results) - success_count) == 0,
        "added": success_count,
        "failed": len(results) - success_count,
        "details": results,
    }


# ── Add material/energy streams ───────────────────────────────────────────────

def add_material_streams(
    streams: list[dict],
    connections: list | None = None,
    unit_op_positions: dict | None = None,
) -> dict:
    """
    Add material/energy stream objects from process_library stream list.
    Positions feed streams to the left of their destination unit op when possible.
    """
    stream_dest: dict[str, str] = {}
    if connections:
        stream_names = {s["name"] for s in streams}
        for conn in connections:
            if len(conn) >= 2 and str(conn[0]) in stream_names:
                stream_dest[str(conn[0])] = str(conn[1])

    results = []
    grid_x, grid_y = 50, 400

    for i, s in enumerate(streams):
        tag = s["name"]
        stream_type = (
            "MaterialStream"
            if s.get("type", "material") == "material"
            else "EnergyStream"
        )

        dest_tag = stream_dest.get(tag)
        if dest_tag and unit_op_positions and dest_tag in unit_op_positions:
            ux, uy = unit_op_positions[dest_tag]
            sx, sy = max(10, ux - 80), uy + 30
        else:
            col = i % 6
            row = i // 6
            sx, sy = grid_x + col * 130, grid_y + row * 80

        results.append(add_unit_operation(stream_type, tag, sx, sy))

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": success_count == len(results),
        "added": success_count,
        "details": results,
    }


# ── Set stream conditions ─────────────────────────────────────────────────────

def set_stream_conditions(
    tag: str,
    temperature_K: float | None = None,
    pressure_Pa: float | None = None,
    mass_flow_kg_s: float | None = None,
    composition_mole_fracs: list[float] | None = None,
) -> dict:
    """Set operating conditions on a material stream (SI units: K, Pa, kg/s)."""
    if tag not in _st._object_registry:
        return {"success": False, "error": f"Tag '{tag}' not found in registry."}

    obj = _st._object_registry[tag]
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

        return {
            "success": True,
            "tag": tag,
            "set": {k: v for k, v in {
                "T_K": temperature_K,
                "P_Pa": pressure_Pa,
                "flow_kg_s": mass_flow_kg_s,
            }.items() if v is not None},
        }
    except Exception as exc:
        return {"success": False, "tag": tag, "error": str(exc)}


# ── Stream detection ──────────────────────────────────────────────────────────

def _is_stream(tag: str) -> bool:
    """
    Return True if the registered object is a MaterialStream or EnergyStream.

    FIX: DWSIM's ObjectType enum .ToString() returns "OT_MaterialStream" /
    "OT_EnergyStream" (with the OT_ prefix), NOT the bare names.  The old
    check `type_name in ("MaterialStream", "EnergyStream")` therefore always
    returned False, causing every connection to create a spurious intermediate
    auto-stream instead of using the already-registered stream object.

    We now check with `in` (substring match) so both forms are handled.
    """
    obj = _st._object_registry.get(tag)
    if obj is None:
        return False

    # Primary check: DWSIM GraphicObject.ObjectType enum ToString()
    # Returns "OT_MaterialStream" or "MaterialStream" depending on version.
    try:
        ot_str = obj.GraphicObject.ObjectType.ToString()
        if any(s in ot_str for s in ("MaterialStream", "EnergyStream")):
            return True
    except Exception:
        pass

    # Fallback: .NET CLR type name contains "Stream"
    try:
        if "Stream" in type(obj).__name__:
            return True
    except Exception:
        pass

    return False


# ── Object connection ─────────────────────────────────────────────────────────

def connect_objects(from_tag: str, to_tag: str) -> dict:
    """
    Connect two objects in the flowsheet.

    Rules:
    - stream → unit_op  : direct ConnectObjects call
    - unit_op → stream  : direct ConnectObjects call
    - unit_op → unit_op : auto-create an intermediate MaterialStream, then
                          connect source → stream and stream → dest

    Uses _interf.ConnectObjects(_sim, from_go, to_go, -1, -1) where -1 means
    "use first available connector port" (DWSIM auto-detect).
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if from_tag not in _st._object_registry:
        return {"success": False, "error": f"Source tag '{from_tag}' not found."}
    if to_tag not in _st._object_registry:
        return {"success": False, "error": f"Destination tag '{to_tag}' not found."}

    try:
        from_obj = _st._object_registry[from_tag]
        to_obj   = _st._object_registry[to_tag]

        from_is_stream = _is_stream(from_tag)
        to_is_stream   = _is_stream(to_tag)

        if from_is_stream or to_is_stream:
            # At least one side is a stream — direct connection.
            with _suppress_native_stdout():
                _st._interf.ConnectObjects(
                    _st._sim,
                    from_obj.GraphicObject,
                    to_obj.GraphicObject,
                    -1, -1,
                )
            return {"success": True, "from": from_tag, "to": to_tag}

        # Both are unit ops — insert intermediate MaterialStream.
        counter = getattr(connect_objects, "_counter", 0) + 1
        connect_objects._counter = counter
        mid_tag = f"_AUTO_S{counter:03d}"

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

        mid_obj = _st._object_registry[mid_tag]

        with _suppress_native_stdout():
            _st._interf.ConnectObjects(
                _st._sim,
                from_obj.GraphicObject, mid_obj.GraphicObject,
                -1, -1,
            )
            _st._interf.ConnectObjects(
                _st._sim,
                mid_obj.GraphicObject, to_obj.GraphicObject,
                -1, -1,
            )
        return {
            "success": True,
            "from": from_tag,
            "to": to_tag,
            "intermediate_stream": mid_tag,
        }

    except Exception as exc:
        return {
            "success": False,
            "from": from_tag,
            "to": to_tag,
            "error": str(exc),
        }


def connect_all(connections: list) -> dict:
    """
    Wire all connection pairs/triplets.

    Formats accepted:
      [from_tag, to_tag]              — direct pair
      [from_tag, stream_tag, to_tag]  — triplet, expanded to two pairs
    """
    results = []
    for conn in connections:
        if len(conn) == 3:
            results.append(connect_objects(str(conn[0]), str(conn[1])))
            results.append(connect_objects(str(conn[1]), str(conn[2])))
        elif len(conn) >= 2:
            results.append(connect_objects(str(conn[0]), str(conn[1])))

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": success_count == len(results),
        "connected": success_count,
        "failed": len(results) - success_count,
        "details": results,
    }


# ── Save / load / list ────────────────────────────────────────────────────────

def save_flowsheet(file_path: str, compressed: bool = True) -> dict:
    """Save the current flowsheet to disk (.dwxmz compressed by default)."""
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}
    if _st._interf is None:
        return {"success": False, "error": "DWSIM interface not initialised."}
    try:
        import os
        dir_part = os.path.dirname(file_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with _suppress_native_stdout():
            _st._interf.SaveFlowsheet(_st._sim, file_path, compressed)
        return {"success": True, "saved_to": file_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def load_flowsheet(file_path: str) -> dict:
    """Load an existing DWSIM flowsheet file."""
    if _st._interf is None:
        r = initialize_dwsim()
        if not r["success"]:
            return r
    try:
        _st._sim = _st._interf.LoadFlowsheet(file_path)
        _st._object_registry = {}
        return {"success": True, "loaded_from": file_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_existing_objects() -> dict:
    """
    Enumerate all objects in the active flowsheet and repopulate the registry.
    Call this after load_flowsheet() before adding new objects.
    """
    if _st._sim is None:
        return {"success": False, "error": "No flowsheet active."}

    objects: list[dict] = []
    try:
        for kvp in _st._sim.SimulationObjects:
            try:
                tag = str(kvp.Key)
                obj = kvp.Value
                _st._object_registry[tag] = obj

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
