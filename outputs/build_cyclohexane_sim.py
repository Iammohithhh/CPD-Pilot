"""
build_cyclohexane_sim.py
========================
Run this script on your LOCAL Windows machine (where DWSIM is installed).

Requirements:
    pip install pythonnet

Usage:
    python build_cyclohexane_sim.py

Output:
    cyclohexane_simulation.dwxmz  (in the same folder as this script)
    Open it directly in DWSIM -> File -> Open

Process: Cyclohexane production via benzene catalytic hydrogenation
         + sulfolane extractive distillation
Target:  1000 kg/hr cyclohexane @ >=99 wt%
Thermo:  Peng-Robinson
"""

import os
import sys
import ctypes

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Locate DWSIM
# ─────────────────────────────────────────────────────────────────────────────

DWSIM_CANDIDATES = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "DWSIM"),
    r"C:\Program Files\DWSIM",
    r"C:\Program Files (x86)\DWSIM",
    os.path.expanduser(r"~\dwsim"),
]

DWSIM_PATH = None
for _p in DWSIM_CANDIDATES:
    if _p and os.path.isfile(os.path.join(_p, "DWSIM.Automation.dll")):
        DWSIM_PATH = _p
        break

if DWSIM_PATH is None:
    env = os.environ.get("DWSIM_PATH")
    if env and os.path.isfile(os.path.join(env, "DWSIM.Automation.dll")):
        DWSIM_PATH = env

if DWSIM_PATH is None:
    print(
        "ERROR: DWSIM not found.\n"
        "Set the DWSIM_PATH environment variable to the folder containing "
        "DWSIM.Automation.dll, e.g.:\n"
        r"  set DWSIM_PATH=C:\Users\YourName\AppData\Local\DWSIM"
    )
    sys.exit(1)

print(f"Found DWSIM at: {DWSIM_PATH}")

# Add DWSIM folder to PATH so native DLLs (SkiaSharp, CoolProp) are found
os.environ["PATH"] = DWSIM_PATH + os.pathsep + os.environ.get("PATH", "")

# ─────────────────────────────────────────────────────────────────────────────
# 2.  Load .NET / DWSIM assemblies via pythonnet
# ─────────────────────────────────────────────────────────────────────────────

try:
    from pythonnet import load as _pn_load  # pythonnet >= 3
    import json as _json, tempfile as _tmp
    _rtcfg = os.path.join(_tmp.gettempdir(), "dwsim_rtcfg.json")
    with open(_rtcfg, "w") as _f:
        _json.dump({
            "runtimeOptions": {
                "tfm": "net8.0-windows",
                "framework": {"name": "Microsoft.WindowsDesktop.App", "version": "8.0.0"},
                "rollForward": "LatestPatch",
            }
        }, _f)
    _pn_load("coreclr", runtime_config=_rtcfg)
except Exception:
    pass  # older pythonnet auto-loads

import clr  # type: ignore
import System  # type: ignore

# AssemblyResolve: let .NET find every DWSIM DLL by name
def _resolve(sender, args):
    short = args.Name.split(",")[0].strip()
    cand = os.path.join(DWSIM_PATH, short + ".dll")
    if os.path.isfile(cand):
        return System.Reflection.Assembly.LoadFrom(cand)
    return None

System.AppDomain.CurrentDomain.AssemblyResolve += _resolve

for dll in [
    "CapeOpen.dll",
    "DWSIM.Automation.dll",
    "DWSIM.Interfaces.dll",
    "DWSIM.GlobalSettings.dll",
    "DWSIM.SharedClasses.dll",
    "DWSIM.Thermodynamics.dll",
    "DWSIM.UnitOperations.dll",
    "DWSIM.Inspector.dll",
    "DWSIM.MathOps.dll",
]:
    full = os.path.join(DWSIM_PATH, dll)
    if os.path.isfile(full):
        clr.AddReference(full)

from DWSIM.Automation import Automation3  # type: ignore
from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType  # type: ignore
from DWSIM.Thermodynamics import PropertyPackages  # type: ignore
from DWSIM.GlobalSettings import Settings  # type: ignore

print("DWSIM assemblies loaded OK")

# ─────────────────────────────────────────────────────────────────────────────
# 3.  Create flowsheet
# ─────────────────────────────────────────────────────────────────────────────

interf = Automation3()
sim = interf.CreateFlowsheet()

# DIAGNOSTIC: find connection-related methods on interf and sim
_interf_connect = sorted([m for m in dir(interf) if 'onnect' in m.lower()])
_sim_connect    = sorted([m for m in dir(sim)    if 'onnect' in m.lower()])
print(f"\nDIAGNOSTIC — interf connect methods: {_interf_connect}")
print(f"DIAGNOSTIC — sim    connect methods: {_sim_connect}\n")

# Compounds  (order matters — composition arrays use this order)
COMPOUNDS = ["Benzene", "Hydrogen", "Cyclohexane", "Sulfolane"]
for c in COMPOUNDS:
    try:
        sim.AddCompound(c)
        print(f"  Added compound: {c}")
    except Exception as e:
        # Try searching by alias
        try:
            comp = sim.AvailableCompounds[c]
            sim.SelectedCompounds.Add(comp.Name, comp)
            print(f"  Added compound (alias): {c}")
        except Exception:
            print(f"  WARNING: compound '{c}' not found — {e}")

# Peng-Robinson property package
pp = PropertyPackages.PengRobinsonPropertyPackage()
sim.AddPropertyPackage(pp)
print("Peng-Robinson property package added")

# ─────────────────────────────────────────────────────────────────────────────
# 4.  Object-type helper
# ─────────────────────────────────────────────────────────────────────────────

def _ot(name):
    """Resolve ObjectType by name, trying OT_ prefix if bare name fails."""
    for candidate in (name, f"OT_{name}"):
        val = getattr(ObjectType, candidate, None)
        if val is not None:
            return val
    raise AttributeError(f"ObjectType has no attribute '{name}' or 'OT_{name}'")

OBJ_MAP = {
    "MaterialStream":    _ot("MaterialStream"),
    "EnergyStream":      _ot("EnergyStream"),
    "Mixer":             _ot("NodeIn"),
    "Splitter":          _ot("NodeOut"),
    "Heater":            _ot("Heater"),
    "Cooler":            _ot("Cooler"),
    "Pump":              _ot("Pump"),
    "Compressor":        _ot("Compressor"),
    "Valve":             _ot("Valve"),
    "Flash":             _ot("Vessel"),
    "ConversionReactor": _ot("RCT_Conversion"),
    "ShortcutColumn":    _ot("ShortcutColumn"),
    "Recycle":           _ot("Recycle"),
}

registry = {}   # tag -> DWSIM object

def add(obj_type_str, tag, x, y):
    ot = OBJ_MAP[obj_type_str]
    wrapper = sim.AddObject(ot, x, y, tag)
    obj = wrapper.GetAsObject()
    registry[tag] = obj
    return obj

# ─────────────────────────────────────────────────────────────────────────────
# 5.  Add unit operations  (left-to-right layout)
# ─────────────────────────────────────────────────────────────────────────────

print("\nAdding unit operations...")

# --- Benzene feed section ---
add("Mixer",             "MIX-BZ",    50,   200)
add("Pump",              "P-01",     200,   200)
add("Compressor",        "K-02",      50,   400)
# --- Reactor feed ---
add("Mixer",             "MIX-03",   350,   300)
add("Heater",            "HEX-04",   500,   300)
add("ConversionReactor", "R-05",     650,   300)
add("Cooler",            "HEX-06",   800,   300)
# --- Flash & H2 recycle ---
add("Flash",             "V-07",     950,   300)
add("Splitter",          "SPL-08",  1100,   200)
add("Compressor",        "K-19",    1100,   100)
add("Recycle",           "REC-H2",  1250,   200)
# --- Liquid let-down ---
add("Valve",             "VLV-09a", 1100,   400)
# --- Sulfolane recycle ---
add("Pump",              "P-09",    1600,   600)
add("Recycle",           "REC-SUL", 1600,   700)
# --- T-10 feed mixer ---
add("Mixer",             "MIX-T10", 1300,   500)
# --- Distillation ---
add("ShortcutColumn",    "T-10",    1450,   400)
add("Recycle",           "REC-BZ",  1600,   300)
add("ShortcutColumn",    "T-13",    1600,   500)

print("Unit operations added.")

# ─────────────────────────────────────────────────────────────────────────────
# 6.  Add ALL streams (feeds, products, and every inter-unit stream)
#     Pre-defining every stream eliminates auto-creation and gives full
#     control over port assignments.
# ─────────────────────────────────────────────────────────────────────────────

print("\nAdding streams...")

ALL_STREAMS = {
    # ── Feed streams ──────────────────────────────────────────────────────────
    "BENZENE-FEED":       ( 50,  100),
    "H2-FEED":            ( 50,  500),
    "SULFOLANE-MAKEUP":   (1100, 600),
    "H2-PURGE":           (1250, 350),
    # ── Cyclohexane product (T-10 distillate) ────────────────────────────────
    "CYH-PRODUCT":        (1450, 300),
    # ── Internal inter-unit streams (named for readability) ──────────────────
    "S-RECBZ-MIXBZ":      ( 150, 200),  # REC-BZ → MIX-BZ
    "S-MIXBZ-P01":        ( 200, 200),  # MIX-BZ → P-01
    "S-P01-MIX03":        ( 280, 260),  # P-01   → MIX-03
    "S-K02-MIX03":        ( 200, 380),  # K-02   → MIX-03
    "S-RECH2-MIX03":      ( 200, 300),  # REC-H2 → MIX-03
    "S-MIX03-HEX04":      ( 430, 300),  # MIX-03 → HEX-04
    "S-HEX04-R05":        ( 575, 300),  # HEX-04 → R-05
    "S-R05-HEX06":        ( 725, 300),  # R-05   → HEX-06  ← critical
    "S-HEX06-V07":        ( 875, 300),  # HEX-06 → V-07
    "S-V07-SPL08":        (1025, 250),  # V-07 vapour → SPL-08
    "S-V07-VLV09":        (1025, 380),  # V-07 liquid → VLV-09a
    "S-SPL08-K19":        (1100, 150),  # SPL-08 → K-19
    "S-K19-RECH2":        (1175, 150),  # K-19   → REC-H2
    "S-VLV09-MIXT10":     (1200, 450),  # VLV-09a → MIX-T10
    "S-RCSUL-MIXT10":     (1450, 700),  # REC-SUL → MIX-T10
    "S-MIXT10-T10":       (1375, 400),  # MIX-T10 → T-10
    "S-T10-T13":          (1525, 460),  # T-10 bottoms → T-13
    "S-T13-RECBZ":        (1700, 300),  # T-13 distillate → REC-BZ
    "S-T13-P09":          (1700, 500),  # T-13 bottoms → P-09
    "S-P09-RCSUL":        (1650, 600),  # P-09 → REC-SUL
}

for tag, (sx, sy) in ALL_STREAMS.items():
    add("MaterialStream", tag, sx, sy)

print(f"Streams added ({len(ALL_STREAMS)} total).")

# ─────────────────────────────────────────────────────────────────────────────
# 7.  Set feed stream conditions
# ─────────────────────────────────────────────────────────────────────────────

print("\nSetting stream conditions...")

def set_stream(tag, T_C, P_bar, flow_kg_hr, comp_fracs):
    """comp_fracs: list aligned to COMPOUNDS order [Benzene, Hydrogen, Cyclohexane, Sulfolane]"""
    obj = registry[tag]
    total = sum(comp_fracs) or 1.0
    normed = [f / total for f in comp_fracs]
    try:
        obj.SetTemperature(T_C + 273.15)
        obj.SetPressure(P_bar * 1e5)
        obj.SetMassFlow(flow_kg_hr / 3600.0)
        from System import Array
        obj.SetOverallComposition(Array[float](normed))
        print(f"  {tag}: T={T_C}°C  P={P_bar}bar  F={flow_kg_hr}kg/hr")
    except Exception as e:
        print(f"  WARNING {tag}: {e}")

#                          tag               T_C  P_bar  kg/hr  [Benz, H2, CyHex, Sulfolane]
set_stream("BENZENE-FEED",      25,  1.013,  980,  [1.0,  0.0,  0.0, 0.0])
set_stream("H2-FEED",           25,  5.0,     80,  [0.0,  1.0,  0.0, 0.0])
set_stream("SULFOLANE-MAKEUP",  60,  1.5,     20,  [0.0,  0.0,  0.0, 1.0])
set_stream("H2-PURGE",          40, 30.0,      8,  [0.0,  1.0,  0.0, 0.0])

# ─────────────────────────────────────────────────────────────────────────────
# 8.  Connect objects — fully explicit (from_tag, from_port, to_tag, to_port)
#     Every stream pre-defined above; no auto-creation of intermediate streams.
#     All connections are stream↔unit-op pairs so DWSIM registers them fully.
# ─────────────────────────────────────────────────────────────────────────────

print("\nConnecting objects...")

# Format: (from_tag, from_port, to_tag, to_port)
# Streams have one output connector (port 0) and one input connector (port 0).
# Unit ops: output ports 0,1,2... in order; input ports 0,1,2... in order.
CONNECTIONS = [
    # ── Benzene feed ──────────────────────────────────────────────────────────
    ("BENZENE-FEED",    0,  "MIX-BZ",         0),  # fresh benzene → mixer inlet 0
    ("REC-BZ",          0,  "S-RECBZ-MIXBZ",  0),  # recycle block → stream
    ("S-RECBZ-MIXBZ",   0,  "MIX-BZ",         1),  # stream → mixer inlet 1
    ("MIX-BZ",          0,  "S-MIXBZ-P01",    0),  # mixer → stream
    ("S-MIXBZ-P01",     0,  "P-01",           0),  # stream → pump
    # ── H2 feed ───────────────────────────────────────────────────────────────
    ("H2-FEED",         0,  "K-02",           0),  # fresh H2 → compressor
    # ── Reactor feed mixer ────────────────────────────────────────────────────
    ("P-01",            0,  "S-P01-MIX03",    0),
    ("S-P01-MIX03",     0,  "MIX-03",         0),
    ("K-02",            0,  "S-K02-MIX03",    0),
    ("S-K02-MIX03",     0,  "MIX-03",         1),
    ("REC-H2",          0,  "S-RECH2-MIX03",  0),
    ("S-RECH2-MIX03",   0,  "MIX-03",         2),
    # ── Reaction path ─────────────────────────────────────────────────────────
    ("MIX-03",          0,  "S-MIX03-HEX04",  0),
    ("S-MIX03-HEX04",   0,  "HEX-04",         0),
    ("HEX-04",          0,  "S-HEX04-R05",    0),
    ("S-HEX04-R05",     0,  "R-05",           0),
    ("R-05",            0,  "S-R05-HEX06",    0),  # ← reactor MATERIAL outlet (port 0)
    ("S-R05-HEX06",     0,  "HEX-06",         0),
    ("HEX-06",          0,  "S-HEX06-V07",    0),
    ("S-HEX06-V07",     0,  "V-07",           0),
    # ── Flash: port 0 = vapour, port 1 = liquid ───────────────────────────────
    ("V-07",            0,  "S-V07-SPL08",    0),  # vapour outlet
    ("S-V07-SPL08",     0,  "SPL-08",         0),
    ("V-07",            1,  "S-V07-VLV09",    0),  # liquid outlet
    ("S-V07-VLV09",     0,  "VLV-09a",        0),
    # ── H2 splitter ───────────────────────────────────────────────────────────
    ("SPL-08",          0,  "S-SPL08-K19",    0),  # 90% → compressor
    ("S-SPL08-K19",     0,  "K-19",           0),
    ("SPL-08",          1,  "H2-PURGE",       0),  # 10% → purge stream
    # ── H2 recycle ────────────────────────────────────────────────────────────
    ("K-19",            0,  "S-K19-RECH2",    0),
    ("S-K19-RECH2",     0,  "REC-H2",         0),
    # ── Liquid path ───────────────────────────────────────────────────────────
    ("VLV-09a",         0,  "S-VLV09-MIXT10", 0),
    ("S-VLV09-MIXT10",  0,  "MIX-T10",        0),
    ("REC-SUL",         0,  "S-RCSUL-MIXT10", 0),
    ("S-RCSUL-MIXT10",  0,  "MIX-T10",        1),
    ("SULFOLANE-MAKEUP", 0, "MIX-T10",        2),
    ("MIX-T10",         0,  "S-MIXT10-T10",   0),
    ("S-MIXT10-T10",    0,  "T-10",           0),
    # ── T-10: port 0 = distillate (CYH product), port 1 = bottoms ────────────
    ("T-10",            0,  "CYH-PRODUCT",    0),  # distillate = cyclohexane
    ("T-10",            1,  "S-T10-T13",      0),  # bottoms → T-13
    ("S-T10-T13",       0,  "T-13",           0),
    # ── T-13: port 0 = distillate (benzene), port 1 = bottoms (sulfolane) ─────
    ("T-13",            0,  "S-T13-RECBZ",    0),
    ("S-T13-RECBZ",     0,  "REC-BZ",         0),
    ("T-13",            1,  "S-T13-P09",      0),
    ("S-T13-P09",       0,  "P-09",           0),
    ("P-09",            0,  "S-P09-RCSUL",    0),
    ("S-P09-RCSUL",     0,  "REC-SUL",        0),
]

def _do_connect(from_go, to_go, src, dst):
    for attempt in [
        lambda: sim.ConnectObjects(from_go, to_go, src, dst),
        lambda: interf.ConnectObjects(sim, from_go, to_go, src, dst),
    ]:
        try:
            attempt()
            return True
        except Exception:
            pass
    raise RuntimeError(f"ConnectObjects failed: {from_go.Tag} port{src} → {to_go.Tag} port{dst}")

ok_count = 0
for (from_tag, from_port, to_tag, to_port) in CONNECTIONS:
    try:
        f_go = registry[from_tag].GraphicObject
        t_go = registry[to_tag].GraphicObject
        _do_connect(f_go, t_go, from_port, to_port)
        print(f"  {from_tag}[{from_port}] → {to_tag}[{to_port}]")
        ok_count += 1
    except Exception as e:
        print(f"  ERROR: {from_tag}[{from_port}] → {to_tag}[{to_port}]: {e}")

print(f"Connections: {ok_count}/{len(CONNECTIONS)} OK")

# DIAGNOSTIC: verify R-05 output connector IsAttached
print("\nDIAGNOSTIC — R-05 output connectors:")
try:
    r05_go = registry["R-05"].GraphicObject
    for i, c in enumerate(r05_go.OutputConnectors):
        attached = c.IsAttached
        target = c.AttachedConnector.AttachedToObjID if attached else "—"
        print(f"  Out[{i}]: IsAttached={attached}  →  {target}")
except Exception as e:
    print(f"  (check failed: {e})")

# ─────────────────────────────────────────────────────────────────────────────
# 9.  Set up the reaction:  C6H6 + 3 H2 → C6H12  (99.9% conversion)
# ─────────────────────────────────────────────────────────────────────────────

print("\nSetting up reaction...")

try:
    from DWSIM.SharedClasses.Others import ReactionSet, Reaction  # type: ignore
    from DWSIM.Interfaces.Enums import ReactionType  # type: ignore

    rxn = Reaction()
    rxn.Name = "Benzene_Hydrogenation"
    rxn.ReactionType = ReactionType.Conversion
    rxn.ReactionPhase = 0       # vapour

    # Stoichiometry  (negative = reactant, positive = product)
    rxn.Components.Add("Benzene",     -1.0)
    rxn.Components.Add("Hydrogen",    -3.0)
    rxn.Components.Add("Cyclohexane",  1.0)
    rxn.BaseReactant = "Benzene"
    rxn.Cn = 0.999       # 99.9% conversion

    rset = ReactionSet()
    rset.Name = "Hydrogenation_Set"
    rset.Reactions.Add(rxn.ID, True)

    sim.ReactionSets.Add(rset.ID, rset)
    sim.Reactions.Add(rxn.ID, rxn)

    # Assign to R-05
    r05 = registry["R-05"]
    r05.ReactionSetID = rset.ID
    print("  Reaction added and assigned to R-05")
except Exception as e:
    print(f"  WARNING: reaction setup failed — {e}")
    print("  Set the reaction manually in DWSIM GUI (99.9% conversion, base = Benzene)")

# ─────────────────────────────────────────────────────────────────────────────
# 10.  Configure unit operation specs
# ─────────────────────────────────────────────────────────────────────────────

print("\nConfiguring unit operations...")

def cfg(tag, **kwargs):
    obj = registry.get(tag)
    if obj is None:
        print(f"  SKIP {tag}: not in registry")
        return
    for attr, val in kwargs.items():
        # Build pairs lazily so numeric operations only happen for matching attr
        if attr == "outlet_T_C":
            pairs = [("OutletTemperature", val + 273.15), ("CalculationMode", 0)]
        elif attr == "outlet_P_bar":
            pairs = [("OutletPressure", val * 1e5), ("Pout", val * 1e5)]
        elif attr == "efficiency":
            pairs = [("AdiabaticEfficiency", val), ("Efficiency", val)]
        elif attr == "T_C":
            pairs = [("FlashTemperature", val + 273.15), ("Temperature", val + 273.15)]
        elif attr == "P_bar":
            pairs = [("FlashPressure", val * 1e5), ("Pressure", val * 1e5)]
        elif attr == "condenser_P_bar":
            pairs = [("CondenserPressure", val * 1e5)]
        elif attr == "reboiler_P_bar":
            pairs = [("ReboilerPressure", val * 1e5)]
        elif attr == "reflux_ratio":
            pairs = [("RefluxRatio", val)]
        elif attr == "light_key":
            pairs = [("LightKeyComponent", val)]
        elif attr == "heavy_key":
            pairs = [("HeavyKeyComponent", val)]
        elif attr == "light_key_recovery":
            pairs = [("LightKeyComponentRecovery", val)]
        elif attr == "heavy_key_recovery":
            pairs = [("HeavyKeyComponentRecovery", val)]
        elif attr == "condenser_type":
            pairs = [("CondenserType", val)]
        elif attr == "split_fraction":
            continue  # handled separately via SplitRatios array
        else:
            pairs = [(attr, val)]

        for prop_name, prop_val in pairs:
            try:
                setattr(obj, prop_name, prop_val)
            except Exception:
                pass
    print(f"  Configured {tag}")

# Pumps & compressors
cfg("P-01",    outlet_P_bar=30,   efficiency=0.75)
cfg("K-02",    outlet_P_bar=30,   efficiency=0.75)
cfg("K-19",    outlet_P_bar=30,   efficiency=0.75)
cfg("P-09",    outlet_P_bar=1.8,  efficiency=0.75)

# Heat exchangers
cfg("HEX-04",  outlet_T_C=200)
cfg("HEX-06",  outlet_T_C=40)
cfg("R-05",    outlet_T_C=200)

# Flash drum
cfg("V-07",    T_C=40,  P_bar=30)

# Let-down valve
cfg("VLV-09a", outlet_P_bar=1.5)

# SPL-08: set split ratios (90% to K-19, 10% to H2-PURGE)
try:
    spl = registry["SPL-08"]
    from System import Array
    spl.SplitRatios = Array[float]([0.90, 0.10])
    print("  SPL-08 split ratios: 90/10")
except Exception as e:
    print(f"  WARNING SPL-08 split ratio: {e} — set manually in GUI")

# Shortcut columns
cfg("T-10",
    light_key="Cyclohexane", heavy_key="Benzene",
    light_key_recovery=0.99, heavy_key_recovery=0.99,
    reflux_ratio=5.0, condenser_P_bar=1.5, reboiler_P_bar=1.8,
    condenser_type=0)

cfg("T-13",
    light_key="Benzene", heavy_key="Sulfolane",
    light_key_recovery=0.99, heavy_key_recovery=0.99,
    reflux_ratio=2.0, condenser_P_bar=0.15, reboiler_P_bar=0.20,
    condenser_type=0)

# ─────────────────────────────────────────────────────────────────────────────
# 11.  Auto-layout and save
# ─────────────────────────────────────────────────────────────────────────────

print("\nAuto-laying out flowsheet...")
try:
    sim.AutoLayout()
except Exception as e:
    print(f"  (AutoLayout skipped: {e})")

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cyclohexane_simulation.dwxmz")
print(f"\nSaving to: {out_path}")
interf.SaveFlowsheet(sim, out_path, True)   # True = compressed (.dwxmz)
print("DONE — file saved successfully.")
print(f"\nOpen in DWSIM:  File -> Open -> {out_path}")
print("Then press Solve (or F5).")
print("\nNotes:")
print("  - Check SPL-08 split ratios (should be 90% / 10%)")
print("  - If solver doesn't converge, set initial estimates on REC-H2, REC-BZ, REC-SUL")
print("  - Sulfolane selectivity is approximated by Peng-Robinson BIPs")
