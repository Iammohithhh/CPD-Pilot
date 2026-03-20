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


# ─────────────────────────────────────────────
# 3. Mermaid diagram generation
# ─────────────────────────────────────────────

def generate_mermaid_pfd(process_data: dict) -> str:
    """
    Generate a Mermaid flowchart string for the process.

    Paste the returned string in a ```mermaid code block and it will
    render as a diagram in GitHub, VS Code, Notion, and many other tools.
    """
    name = process_data.get("name", "Chemical Process")
    lines: list[str] = [
        "```mermaid",
        "flowchart LR",
        f"  %% {name}",
        "",
    ]

    def _safe(tag: str) -> str:
        return tag.replace("-", "").replace(" ", "_")

    # Equipment type → Mermaid shape
    _shapes = {
        "Mixer":              ("{", "}"),
        "Splitter":           ("{", "}"),
        "Heater":             ("[", "]"),
        "Cooler":             ("[", "]"),
        "HeatExchanger":      ("[", "]"),
        "Pump":               ("(", ")"),
        "Compressor":         ("(", ")"),
        "Expander":           ("(", ")"),
        "Flash":              ("([", "])"),
        "Vessel":             ("([", "])"),
        "Tank":               ("([", "])"),
        "ShortcutColumn":     ("[[", "]]"),
        "DistillationColumn": ("[[", "]]"),
        "AbsorptionColumn":   ("[[", "]]"),
        "ConversionReactor":  ("{{", "}}"),
        "EquilibriumReactor": ("{{", "}}"),
        "GibbsReactor":       ("{{", "}}"),
        "CSTR":               ("{{", "}}"),
        "PFR":                ("{{", "}}"),
        "Filter":             ("[/", "/]"),
        "ComponentSeparator": ("[/", "/]"),
        "Valve":              (">", "]"),
    }

    # Feed stream nodes
    feeds = process_data.get("streams", [])
    for s in feeds:
        sid = _safe(s["name"])
        label = f"{s['name']}\\n{s.get('description', '')}\\nT={s.get('T_C',25)}°C"
        lines.append(f"  {sid}[\"{label}\"]:::feed")

    # Unit operation nodes
    for op in process_data.get("unit_operations", []):
        oid = _safe(op["name"])
        lopen, lclose = _shapes.get(op["type"], ("[", "]"))
        label = f"{op['name']}\\n{op['type']}"
        lines.append(f"  {oid}{lopen}\"{label}\"{lclose}:::unit")

    lines.append("")

    # Edges
    for src, dst in process_data.get("connections", []):
        lines.append(f"  {_safe(src)} --> {_safe(dst)}")

    lines.append("")
    lines.append("  classDef feed fill:#BBDEFB,stroke:#1565C0,color:#000")
    lines.append("  classDef unit fill:#E8F5E9,stroke:#2E7D32,color:#000")
    lines.append("```")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 4. SVG PFD generation (no external dependencies)
# ─────────────────────────────────────────────

_SVG_COLORS = {
    "Heater":             "#FF8A80",
    "Cooler":             "#80D8FF",
    "HeatExchanger":      "#FFD180",
    "Pump":               "#CCFF90",
    "Compressor":         "#CCFF90",
    "Expander":           "#CCFF90",
    "ConversionReactor":  "#FF80AB",
    "EquilibriumReactor": "#FF80AB",
    "GibbsReactor":       "#FF80AB",
    "CSTR":               "#FF80AB",
    "PFR":                "#FF80AB",
    "Flash":              "#EA80FC",
    "Vessel":             "#EA80FC",
    "Tank":               "#EA80FC",
    "ShortcutColumn":     "#B9F6CA",
    "DistillationColumn": "#B9F6CA",
    "AbsorptionColumn":   "#B9F6CA",
    "Mixer":              "#CFD8DC",
    "Splitter":           "#CFD8DC",
}

_BOX_W = 110
_BOX_H = 60
_X_GAP = 60   # horizontal gap between boxes
_Y_MARGIN = 80


def _layout_nodes(process_data: dict) -> dict[str, tuple[int, int]]:
    """
    Assign (cx, cy) centre coordinates to every node (unit op + stream).
    Simple left-to-right topological layout based on the connections list.
    Returns {tag: (cx, cy)}.
    """
    unit_ops = process_data.get("unit_operations", [])
    feeds    = process_data.get("streams", [])
    conns    = process_data.get("connections", [])

    # Build adjacency (predecessor count → topological order)
    all_nodes = [op["name"] for op in unit_ops] + [s["name"] for s in feeds]
    in_degree: dict[str, int] = {n: 0 for n in all_nodes}
    successors: dict[str, list[str]] = {n: [] for n in all_nodes}

    for src, dst in conns:
        if dst in in_degree:
            in_degree[dst] += 1
        if src in successors:
            successors[src].append(dst)

    # Kahn's algorithm for column assignment
    from collections import deque
    col: dict[str, int] = {}
    queue = deque(n for n in all_nodes if in_degree[n] == 0)
    while queue:
        n = queue.popleft()
        col[n] = col.get(n, 0)
        for m in successors.get(n, []):
            col[m] = max(col.get(m, 0), col[n] + 1)
            in_degree[m] -= 1
            if in_degree[m] == 0:
                queue.append(m)

    # Group nodes by column
    by_col: dict[int, list[str]] = {}
    for n, c in col.items():
        by_col.setdefault(c, []).append(n)

    # Centre coordinates: x by column, y by row within column
    positions: dict[str, tuple[int, int]] = {}
    col_x_step = _BOX_W + _X_GAP
    for c, nodes in sorted(by_col.items()):
        cx = 60 + c * col_x_step + _BOX_W // 2
        row_h = _BOX_H + 30
        total_h = len(nodes) * row_h
        start_y = _Y_MARGIN + _BOX_H // 2
        for r, n in enumerate(nodes):
            positions[n] = (cx, start_y + r * row_h)

    return positions


def generate_svg_pfd(process_data: dict) -> str:
    """
    Generate a standalone SVG string representing the PFD.

    The SVG can be saved as a .svg file and opened in any browser,
    or embedded directly in HTML/Word documents.
    No external libraries required.
    """
    name     = process_data.get("name", "Chemical Process")
    unit_ops = process_data.get("unit_operations", [])
    feeds    = process_data.get("streams", [])
    conns    = process_data.get("connections", [])

    positions = _layout_nodes(process_data)

    # Canvas size
    max_cx = max((p[0] for p in positions.values()), default=400)
    max_cy = max((p[1] for p in positions.values()), default=300)
    W = max_cx + _BOX_W // 2 + 40
    H = max_cy + _BOX_H // 2 + 80

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Arial,Helvetica,sans-serif">',
        # background
        f'  <rect width="{W}" height="{H}" fill="#FAFAFA"/>',
        # title
        f'  <text x="{W//2}" y="28" text-anchor="middle" font-size="16" '
        f'font-weight="bold" fill="#333">{_xml_escape(name)}</text>',
        f'  <text x="{W//2}" y="46" text-anchor="middle" font-size="11" '
        f'fill="#666">Process Flow Diagram</text>',
        # arrowhead marker
        '  <defs>',
        '    <marker id="arr" markerWidth="8" markerHeight="6" '
        'refX="6" refY="3" orient="auto">',
        '      <polygon points="0 0, 8 3, 0 6" fill="#555"/>',
        '    </marker>',
        '  </defs>',
    ]

    # ── Draw edges FIRST (behind boxes) ────────────────────────────────────
    for src, dst in conns:
        if src not in positions or dst not in positions:
            continue
        sx, sy = positions[src]
        dx, dy = positions[dst]
        # Simple straight line from right edge of src to left edge of dst
        x1 = sx + _BOX_W // 2
        x2 = dx - _BOX_W // 2
        svg.append(
            f'  <line x1="{x1}" y1="{sy}" x2="{x2}" y2="{dy}" '
            f'stroke="#555" stroke-width="2" marker-end="url(#arr)"/>'
        )
        # stream label at midpoint
        mx, my = (x1 + x2) // 2, (sy + dy) // 2 - 6
        svg.append(
            f'  <text x="{mx}" y="{my}" text-anchor="middle" '
            f'font-size="9" fill="#777">{_xml_escape(src)}→{_xml_escape(dst)}</text>'
        )

    # ── Draw feed stream nodes ──────────────────────────────────────────────
    for s in feeds:
        tag = s["name"]
        if tag not in positions:
            continue
        cx, cy = positions[tag]
        x = cx - _BOX_W // 2
        y = cy - _BOX_H // 2
        svg.append(
            f'  <rect x="{x}" y="{y}" width="{_BOX_W}" height="{_BOX_H}" '
            f'rx="4" fill="#BBDEFB" stroke="#1565C0" stroke-width="1.5"/>'
        )
        svg.append(
            f'  <text x="{cx}" y="{cy - 8}" text-anchor="middle" '
            f'font-size="10" font-weight="bold" fill="#0D47A1">'
            f'{_xml_escape(tag)}</text>'
        )
        desc = s.get("description", "")[:20]
        svg.append(
            f'  <text x="{cx}" y="{cy + 6}" text-anchor="middle" '
            f'font-size="9" fill="#1565C0">{_xml_escape(desc)}</text>'
        )
        cond = f"T={s.get('T_C',25)}°C  P={s.get('P_bar',1)}bar"
        svg.append(
            f'  <text x="{cx}" y="{cy + 18}" text-anchor="middle" '
            f'font-size="8" fill="#555">{_xml_escape(cond)}</text>'
        )

    # ── Draw unit operation nodes ───────────────────────────────────────────
    op_type_map = {op["name"]: op["type"] for op in unit_ops}
    for op in unit_ops:
        tag = op["name"]
        if tag not in positions:
            continue
        cx, cy = positions[tag]
        x = cx - _BOX_W // 2
        y = cy - _BOX_H // 2
        color = _SVG_COLORS.get(op["type"], "#E8E8E8")
        svg.append(
            f'  <rect x="{x}" y="{y}" width="{_BOX_W}" height="{_BOX_H}" '
            f'rx="6" fill="{color}" stroke="#444" stroke-width="1.5"/>'
        )
        svg.append(
            f'  <text x="{cx}" y="{cy - 10}" text-anchor="middle" '
            f'font-size="11" font-weight="bold" fill="#222">'
            f'{_xml_escape(tag)}</text>'
        )
        svg.append(
            f'  <text x="{cx}" y="{cy + 4}" text-anchor="middle" '
            f'font-size="9" fill="#333">{_xml_escape(op["type"])}</text>'
        )
        purpose = op.get("purpose", "")[:22]
        svg.append(
            f'  <text x="{cx}" y="{cy + 16}" text-anchor="middle" '
            f'font-size="8" fill="#555">{_xml_escape(purpose)}</text>'
        )

    # ── Legend ──────────────────────────────────────────────────────────────
    lx, ly = 10, H - 50
    legend_items = [
        ("#FF80AB", "Reactor"), ("#FF8A80", "Heater/Cooler"),
        ("#EA80FC", "Separator"), ("#B9F6CA", "Column"),
        ("#BBDEFB", "Feed Stream"),
    ]
    svg.append(f'  <text x="{lx}" y="{ly}" font-size="9" fill="#666">Legend:</text>')
    for i, (col, label) in enumerate(legend_items):
        bx = lx + i * 110
        by = ly + 6
        svg.append(
            f'  <rect x="{bx}" y="{by}" width="12" height="10" '
            f'fill="{col}" stroke="#888" stroke-width="1"/>'
        )
        svg.append(
            f'  <text x="{bx+15}" y="{by+9}" font-size="9" fill="#444">'
            f'{label}</text>'
        )

    svg.append('</svg>')
    return "\n".join(svg)


def _xml_escape(s: str) -> str:
    """Escape special XML characters for safe embedding in SVG."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("°", "&#176;")
    )


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
# 5. Combined PFD generation
# ─────────────────────────────────────────────

def generate_pfd(process_data: dict, output_dir: str | None = None) -> dict:
    """
    Generate text, Mermaid, SVG, and Graphviz PFDs for a process.

    Args:
        process_data: process_library-format dict
        output_dir:   directory for output files (default: outputs/)

    Returns:
        dict with:
          text_pfd    – ASCII art (always present, show in a code block)
          mermaid_pfd – Mermaid flowchart (paste in ```mermaid block to render)
          svg_pfd     – SVG source (save as .svg and open in browser)
          svg_path    – path to saved .svg file (if output_dir given)
          dot_source  – Graphviz DOT source
          dot_path    – path to saved .dot file
          png_path    – path to rendered PNG (only if graphviz installed)
    """
    text_pfd    = generate_text_pfd(process_data)
    mermaid_pfd = generate_mermaid_pfd(process_data)
    svg_pfd     = generate_svg_pfd(process_data)

    result: dict[str, Any] = {
        "text_pfd":    text_pfd,
        "mermaid_pfd": mermaid_pfd,
        "svg_pfd":     svg_pfd,
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        chem = process_data.get("chemical", "process").replace(" ", "_")

        # Save SVG (always works — no external deps)
        svg_path = os.path.join(output_dir, f"{chem}_pfd.svg")
        try:
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(svg_pfd)
            result["svg_path"] = svg_path
        except Exception as exc:
            result["svg_path_error"] = str(exc)

        # Save + try to render Graphviz DOT
        dot_path = os.path.join(output_dir, f"{chem}_pfd.dot")
        dot_result = save_dot(process_data, dot_path)
        result.update({k: v for k, v in dot_result.items() if k != "success"})

    return result
