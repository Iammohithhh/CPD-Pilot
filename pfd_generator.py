"""
pfd_generator.py — Generate Process Flow Diagrams.

Two output formats:
  1. Text-based PFD (ASCII art) — always available, no dependencies
  2. Graphviz DOT file — can be rendered to PNG/SVG if graphviz is installed

The text PFD is suitable for terminal / chat output.
The DOT file can be rendered using `dot -Tpng output.dot -o output.png`.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any


# ─────────────────────────────────────────────
# 1. Text-based PFD (ASCII art)
# ─────────────────────────────────────────────

# Unit operation box symbols for ASCII art
_SYMBOLS = {
    "Mixer":              "[MIX]",
    "Splitter":           "[SPL]",
    "Heater":             "[HTR]",
    "Cooler":             "[CLR]",
    "HeatExchanger":      "[HEX]",
    "Valve":              "[VLV]",
    "Pump":               "[PMP]",
    "Compressor":         "[CMP]",
    "Expander":           "[EXP]",
    "Pipe":               "[PIP]",
    "Flash":              "[FLS]",
    "Vessel":             "[VES]",
    "Tank":               "[TNK]",
    "ShortcutColumn":     "[COL]",
    "DistillationColumn": "[DST]",
    "AbsorptionColumn":   "[ABS]",
    "ConversionReactor":  "[RXN]",
    "EquilibriumReactor": "[EQR]",
    "GibbsReactor":       "[GBR]",
    "CSTR":               "[CST]",
    "PFR":                "[PFR]",
    "ComponentSeparator": "[SEP]",
    "Filter":             "[FLT]",
    "MaterialStream":     "---→",
    "EnergyStream":       "···→",
}


def generate_text_pfd(process_data: dict) -> str:
    """
    Generate a text-based Process Flow Diagram from process library data.

    Returns a multi-line string showing the process flow with
    equipment tags, types, and stream connections.
    """
    lines: list[str] = []
    name = process_data.get("name", "Chemical Process")
    route = process_data.get("route", "")

    # Header
    lines.append("=" * 72)
    lines.append(f"  PROCESS FLOW DIAGRAM: {name}")
    if route:
        lines.append(f"  Route: {route}")
    lines.append("=" * 72)
    lines.append("")

    # Feed streams
    feeds = process_data.get("streams", [])
    if feeds:
        lines.append("  FEED STREAMS:")
        for s in feeds:
            comp_str = ""
            comp = s.get("composition", {})
            if comp:
                parts = [f"{k}: {v*100:.0f}%" for k, v in comp.items() if v > 0]
                comp_str = f" ({', '.join(parts)})"
            lines.append(
                f"    [{s['name']}] {s.get('description', '')}"
                f"  T={s.get('T_C', 25)}°C  P={s.get('P_bar', 1)}bar"
                f"  Flow={s.get('total_flow_kg_hr', '?')}kg/hr{comp_str}"
            )
        lines.append("")

    # Process flow
    lines.append("  PROCESS FLOW:")
    lines.append("")

    unit_ops = process_data.get("unit_operations", [])
    connections = process_data.get("connections", [])

    # Build adjacency: who feeds into whom
    adj: dict[str, list[str]] = {}
    for (src, dst) in connections:
        adj.setdefault(src, []).append(dst)

    # Draw each unit op as a box
    for i, op in enumerate(unit_ops):
        sym = _SYMBOLS.get(op["type"], f"[{op['type'][:3].upper()}]")
        tag = op["name"]
        purpose = op.get("purpose", "")

        box_width = max(len(tag) + 4, len(purpose) + 4, 24)
        border = "+" + "-" * box_width + "+"

        lines.append(f"    {border}")
        lines.append(f"    | {tag:^{box_width-2}} |")
        lines.append(f"    | {sym:^{box_width-2}} |")
        if purpose:
            # Word-wrap purpose if too long
            max_w = box_width - 2
            if len(purpose) <= max_w:
                lines.append(f"    | {purpose:^{max_w}} |")
            else:
                lines.append(f"    | {purpose[:max_w]:^{max_w}} |")
        lines.append(f"    {border}")

        # Arrow to next unit
        if i < len(unit_ops) - 1:
            next_tag = unit_ops[i + 1]["name"]
            # Find what connects them
            conn_label = ""
            for (src, dst) in connections:
                if dst == next_tag and (src == tag or any(
                    s["name"] == src for s in feeds
                )):
                    conn_label = f" ({src} → {dst})"
                    break
            lines.append(f"         |")
            lines.append(f"         | {conn_label}")
            lines.append(f"         ▼")

    lines.append("")

    # Product streams
    lines.append("  PRODUCT / OUTPUT STREAMS:")
    # Identify streams that leave the system (not feeding into any unit)
    all_unit_tags = {op["name"] for op in unit_ops}
    all_feed_tags = {s["name"] for s in feeds}
    product_notes = process_data.get("notes", "")
    if product_notes:
        lines.append(f"    {product_notes}")
    lines.append("")

    # Legend
    lines.append("  LEGEND:")
    lines.append("    [RXN] = Reactor    [COL/DST] = Column      [FLS] = Flash/Separator")
    lines.append("    [HTR] = Heater     [CLR] = Cooler           [HEX] = Heat Exchanger")
    lines.append("    [PMP] = Pump       [CMP] = Compressor       [MIX] = Mixer")
    lines.append("    [VLV] = Valve      [EXP] = Expander         [SPL] = Splitter")
    lines.append("")
    lines.append("=" * 72)

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 2. Graphviz DOT file generation
# ─────────────────────────────────────────────

# Shape mapping for Graphviz
_DOT_SHAPES = {
    "Mixer": "invtriangle",
    "Splitter": "triangle",
    "Heater": "box",
    "Cooler": "box",
    "HeatExchanger": "box",
    "Valve": "diamond",
    "Pump": "circle",
    "Compressor": "circle",
    "Expander": "circle",
    "Flash": "cylinder",
    "Vessel": "cylinder",
    "Tank": "cylinder",
    "ShortcutColumn": "box3d",
    "DistillationColumn": "box3d",
    "AbsorptionColumn": "box3d",
    "ConversionReactor": "hexagon",
    "EquilibriumReactor": "hexagon",
    "GibbsReactor": "hexagon",
    "CSTR": "hexagon",
    "PFR": "hexagon",
    "ComponentSeparator": "trapezium",
    "Filter": "trapezium",
}

_DOT_COLORS = {
    "Heater": "#FF6B6B",
    "Cooler": "#4ECDC4",
    "HeatExchanger": "#FFE66D",
    "Pump": "#A8E6CF",
    "Compressor": "#A8E6CF",
    "ConversionReactor": "#FF8C94",
    "EquilibriumReactor": "#FF8C94",
    "GibbsReactor": "#FF8C94",
    "CSTR": "#FF8C94",
    "PFR": "#FF8C94",
    "Flash": "#DCD6F7",
    "Vessel": "#DCD6F7",
    "ShortcutColumn": "#B5EAD7",
    "DistillationColumn": "#B5EAD7",
    "AbsorptionColumn": "#B5EAD7",
    "Mixer": "#C7CEEA",
    "Splitter": "#C7CEEA",
}


def generate_dot(process_data: dict) -> str:
    """
    Generate a Graphviz DOT representation of the process flow diagram.

    Returns the DOT source as a string.
    """
    name = process_data.get("name", "Process")
    lines: list[str] = []
    lines.append(f'digraph "{name}" {{')
    lines.append('    rankdir=LR;')
    lines.append('    bgcolor="#FAFAFA";')
    lines.append(f'    label="{name}";')
    lines.append('    labelloc=t;')
    lines.append('    fontsize=16;')
    lines.append('    fontname="Helvetica";')
    lines.append('    node [fontname="Helvetica", fontsize=10];')
    lines.append('    edge [fontname="Helvetica", fontsize=9];')
    lines.append('')

    # Feed stream nodes
    feeds = process_data.get("streams", [])
    for s in feeds:
        tag = _dot_safe(s["name"])
        desc = s.get("description", s["name"])
        t = s.get("T_C", 25)
        p = s.get("P_bar", 1)
        flow = s.get("total_flow_kg_hr", "?")
        label = f'{s["name"]}\\n{desc}\\nT={t}°C P={p}bar\\n{flow} kg/hr'
        lines.append(f'    {tag} [shape=plaintext, label="{label}", '
                     f'fontcolor="#2196F3"];')

    lines.append('')

    # Unit operation nodes
    for op in process_data.get("unit_operations", []):
        tag = _dot_safe(op["name"])
        shape = _DOT_SHAPES.get(op["type"], "box")
        color = _DOT_COLORS.get(op["type"], "#E8E8E8")
        label = f'{op["name"]}\\n({op["type"]})'
        if op.get("purpose"):
            # Truncate long purposes
            purpose = op["purpose"][:30]
            label += f'\\n{purpose}'
        lines.append(f'    {tag} [shape={shape}, style=filled, '
                     f'fillcolor="{color}", label="{label}"];')

    lines.append('')

    # Edges (connections)
    for (src, dst) in process_data.get("connections", []):
        src_safe = _dot_safe(src)
        dst_safe = _dot_safe(dst)
        lines.append(f'    {src_safe} -> {dst_safe} [color="#666666"];')

    # Product streams (units with no outgoing connection)
    connected_sources = {c[0] for c in process_data.get("connections", [])}
    unit_tags = {op["name"] for op in process_data.get("unit_operations", [])}
    terminal_units = unit_tags - connected_sources
    for tag in terminal_units:
        prod_node = _dot_safe(tag + "_product")
        lines.append(f'    {prod_node} [shape=plaintext, label="Product\\nfrom {tag}", '
                     f'fontcolor="#4CAF50"];')
        lines.append(f'    {_dot_safe(tag)} -> {prod_node} [color="#4CAF50", style=dashed];')

    lines.append('}')
    return '\n'.join(lines)


def _dot_safe(tag: str) -> str:
    """Make a tag safe for use as a DOT node identifier."""
    return tag.replace("-", "_").replace(" ", "_").replace(".", "_")


def save_dot(process_data: dict, output_path: str) -> dict:
    """
    Save a Graphviz DOT file for the process.

    Args:
        process_data: process_library-format dict
        output_path:  path for the .dot file

    Returns:
        dict with success flag, dot_path, and optional png_path
    """
    dot_source = generate_dot(process_data)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w") as f:
        f.write(dot_source)

    result: dict[str, Any] = {
        "success": True,
        "dot_path": output_path,
        "dot_source": dot_source,
    }

    # Try to render PNG if graphviz is installed
    png_path = output_path.rsplit(".", 1)[0] + ".png"
    try:
        subprocess.run(
            ["dot", "-Tpng", output_path, "-o", png_path],
            check=True, capture_output=True, timeout=30,
        )
        result["png_path"] = png_path
        result["rendered"] = True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result["rendered"] = False
        result["render_note"] = (
            "Graphviz not installed or rendering failed. "
            "Install graphviz and run: dot -Tpng {output_path} -o {png_path}"
        )

    return result


# ─────────────────────────────────────────────
# 3. Combined PFD generation
# ─────────────────────────────────────────────

def generate_pfd(process_data: dict, output_dir: str | None = None) -> dict:
    """
    Generate both text and graphviz PFDs for a process.

    Args:
        process_data: process_library-format dict
        output_dir:   directory for output files (default: outputs/)

    Returns:
        dict with text_pfd, dot_source, and file paths
    """
    text_pfd = generate_text_pfd(process_data)

    result: dict[str, Any] = {
        "text_pfd": text_pfd,
    }

    if output_dir:
        chem = process_data.get("chemical", "process").replace(" ", "_")
        dot_path = os.path.join(output_dir, f"{chem}_pfd.dot")
        dot_result = save_dot(process_data, dot_path)
        result.update(dot_result)

    return result
