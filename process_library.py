"""
process_library.py — Built-in knowledge of common industrial chemical processes.

Each entry has a standard structure:
  name, route, description, reactions, compounds, thermo_model,
  unit_operations, streams, connections, unit_op_specs, notes

unit_op_specs provides default operating specs (outlet temperature, reflux ratio,
outlet pressure, key components, etc.) that configure_unit_operation() applies so
DWSIM can actually converge each block.  Claude can override any spec via the
configure_unit_operation tool when the user specifies different values.
"""

PROCESS_LIBRARY = {

    # ──────────────────────────────────────────────────────────────────────────
    "ethanol": {
        "name": "Ethanol Production",
        "route": "Ethylene Hydration",
        "description": (
            "Ethanol is produced by catalytic hydration of ethylene. "
            "Ethylene reacts with steam over a phosphoric acid catalyst (H3PO4) "
            "at 300°C and 70 bar. Single-pass conversion is ~5%, so a large "
            "recycle stream is needed. Products are separated by distillation."
        ),
        "reactions": [
            {
                "equation": "Ethylene + Water → Ethanol",
                "type": "ConversionReactor",
                "conversion": 0.05,
                "temperature_C": 300,
                "pressure_bar": 70,
                "catalyst": "H3PO4 on silica gel",
            }
        ],
        "compounds": ["Ethylene", "Water", "Ethanol"],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix fresh ethylene + recycle"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat feed to 300°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Hydration reactor 300°C 70 bar"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool reactor effluent to 40°C"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Flash: separate C2H4 vapour from liquid"},
            {"type": "ShortcutColumn",   "name": "T-101",   "purpose": "Distillation: ethanol/water separation"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh ethylene feed",
             "T_C": 25, "P_bar": 70, "total_flow_kg_hr": 100,
             "composition": {"Ethylene": 0.99, "Water": 0.01}},
            {"name": "S-02", "type": "material", "description": "Fresh water/steam feed",
             "T_C": 25, "P_bar": 70, "total_flow_kg_hr": 200,
             "composition": {"Ethylene": 0.0, "Water": 1.0}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "V-101"),
            ("V-101",   "T-101"),
        ],
        "unit_op_specs": {
            "H-101":  {"outlet_T_C": 300},
            "C-101":  {"outlet_T_C": 40},
            "V-101":  {"P_bar": 70,  "T_C": 40},
            "T-101":  {
                "light_key": "Ethanol", "heavy_key": "Water",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.01,
                "reflux_ratio": 1.5, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "Vapour from V-101 (unreacted ethylene) is recycled to MIX-101. "
            "T-101 gives ethanol as distillate, water as bottoms. "
            "Real plants use azeotropic distillation or molecular sieves for >95% ethanol."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "methanol": {
        "name": "Methanol Production",
        "route": "Syngas Conversion (ICI Low-Pressure Process)",
        "description": (
            "Methanol is synthesised from syngas (CO + H2) over Cu/ZnO/Al2O3 catalyst "
            "at 250°C and 50-100 bar. Single-pass conversion ~25%. "
            "Crude methanol is purified by distillation."
        ),
        "reactions": [
            {
                "equation": "Carbon Monoxide + 2 Hydrogen → Methanol",
                "type": "ConversionReactor",
                "conversion": 0.25,
                "temperature_C": 250,
                "pressure_bar": 80,
                "catalyst": "Cu/ZnO/Al2O3",
            },
        ],
        "compounds": [
            "Carbon Monoxide", "Hydrogen", "Methanol", "Water",
            "Carbon Dioxide", "Nitrogen",
        ],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Compressor",       "name": "K-101", "purpose": "Compress syngas to 80 bar"},
            {"type": "Heater",           "name": "H-101", "purpose": "Preheat to 250°C"},
            {"type": "ConversionReactor","name": "R-101", "purpose": "Methanol synthesis reactor"},
            {"type": "Cooler",           "name": "C-101", "purpose": "Cool reactor effluent to 40°C"},
            {"type": "Flash",            "name": "V-101", "purpose": "Separate unreacted gas from crude methanol"},
            {"type": "ShortcutColumn",   "name": "T-101", "purpose": "Purify methanol (remove water + lights)"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh syngas feed",
             "T_C": 40, "P_bar": 30, "total_flow_kg_hr": 1000,
             "composition": {
                 "Carbon Monoxide": 0.30, "Hydrogen": 0.60,
                 "Carbon Dioxide": 0.05,  "Nitrogen": 0.05,
             }},
        ],
        "connections": [
            ("S-01",  "K-101"),
            ("K-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),
        ],
        "unit_op_specs": {
            "K-101": {"outlet_P_bar": 80,  "efficiency": 0.75},
            "H-101": {"outlet_T_C": 250},
            "C-101": {"outlet_T_C": 40},
            "V-101": {"P_bar": 80, "T_C": 40},
            "T-101": {
                "light_key": "Methanol", "heavy_key": "Water",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.05,
                "reflux_ratio": 1.2, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "Unreacted gas from V-101 (N2, CO, H2) is recycled with a small purge. "
            "T-101 removes lights as distillate; methanol is side draw or second column."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "ammonia": {
        "name": "Ammonia Production",
        "route": "Haber-Bosch Process",
        "description": (
            "Ammonia is made from N2 and H2 at 400–500°C, 150–300 bar, "
            "over an iron catalyst. Equilibrium conversion ~15%; large recycle needed. "
            "Product NH3 is condensed at –33°C."
        ),
        "reactions": [
            {
                "equation": "Nitrogen + 3 Hydrogen → 2 Ammonia",
                "type": "ConversionReactor",
                "conversion": 0.15,
                "temperature_C": 450,
                "pressure_bar": 200,
                "catalyst": "Promoted iron (Fe3O4 + K2O + Al2O3)",
            }
        ],
        "compounds": ["Nitrogen", "Hydrogen", "Ammonia", "Argon"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix fresh feed + recycle"},
            {"type": "Compressor",       "name": "K-101",   "purpose": "Compress to 200 bar"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat to 450°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Ammonia synthesis reactor"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool to condense ammonia (–33°C)"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Separate liquid NH3 from unreacted gas"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh synthesis gas (1:3 N2:H2)",
             "T_C": 25, "P_bar": 30, "total_flow_kg_hr": 1000,
             "composition": {"Nitrogen": 0.25, "Hydrogen": 0.74, "Argon": 0.01}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("MIX-101", "K-101"),
            ("K-101",   "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "V-101"),
        ],
        "unit_op_specs": {
            "K-101":  {"outlet_P_bar": 200, "efficiency": 0.75},
            "H-101":  {"outlet_T_C": 450},
            "C-101":  {"outlet_T_C": -33},
            "V-101":  {"P_bar": 200, "T_C": -33},
        },
        "notes": (
            "Vapour from V-101 (N2 + H2 + Ar) recycles to MIX-101 with a small purge "
            "to prevent argon accumulation. Liquid NH3 from V-101 is the product."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "acetic_acid": {
        "name": "Acetic Acid Production",
        "route": "Methanol Carbonylation (Monsanto/Cativa Process)",
        "description": (
            "Acetic acid is made by liquid-phase carbonylation of methanol with CO "
            "over a Rh–iodide catalyst at 150–200°C, 30–60 bar. Selectivity >99%."
        ),
        "reactions": [
            {
                "equation": "Methanol + Carbon Monoxide → Acetic Acid",
                "type": "ConversionReactor",
                "conversion": 0.99,
                "temperature_C": 180,
                "pressure_bar": 40,
                "catalyst": "Rh/HI (Monsanto catalyst)",
            }
        ],
        "compounds": [
            "Methanol", "Carbon Monoxide", "Acetic Acid",
            "Water", "Methyl Iodide", "Hydrogen Iodide",
        ],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix methanol + CO feeds"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat to 180°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Carbonylation reactor"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Flash off dissolved CO + lights"},
            {"type": "ShortcutColumn",   "name": "T-101",   "purpose": "Light ends column (remove HI, MeI)"},
            {"type": "ShortcutColumn",   "name": "T-102",   "purpose": "Product column (pure acetic acid)"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Methanol feed",
             "T_C": 25, "P_bar": 40, "total_flow_kg_hr": 500,
             "composition": {"Methanol": 1.0}},
            {"name": "S-02", "type": "material", "description": "CO feed",
             "T_C": 25, "P_bar": 40, "total_flow_kg_hr": 440,
             "composition": {"Carbon Monoxide": 1.0}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "V-101"),
            ("V-101",   "T-101"),
            ("T-101",   "T-102"),
        ],
        "unit_op_specs": {
            "H-101": {"outlet_T_C": 180},
            "V-101": {"P_bar": 40, "T_C": 120},
            "T-101": {
                "light_key": "Methyl Iodide", "heavy_key": "Acetic Acid",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.01,
                "reflux_ratio": 2.0, "condenser_P_bar": 1.013,
            },
            "T-102": {
                "light_key": "Acetic Acid", "heavy_key": "Water",
                "light_key_recovery": 0.98, "heavy_key_recovery": 0.02,
                "reflux_ratio": 1.5, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "T-101 recovers HI and MeI as distillate for catalyst recycle. "
            "T-102 gives pure acetic acid as distillate, water as bottoms."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "benzene": {
        "name": "Benzene Production",
        "route": "Catalytic Reforming",
        "description": (
            "Benzene is produced by catalytic reforming of naphtha (cyclohexane "
            "dehydrogenation) over Pt/Al2O3 at 500°C and 20 bar. "
            "Hydrogen is a valuable co-product."
        ),
        "reactions": [
            {
                "equation": "Cyclohexane → Benzene + 3 Hydrogen",
                "type": "ConversionReactor",
                "conversion": 0.90,
                "temperature_C": 500,
                "pressure_bar": 20,
                "catalyst": "Pt/Al2O3",
            }
        ],
        "compounds": ["n-Hexane", "Cyclohexane", "Benzene", "Toluene", "Hydrogen"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Heater",           "name": "H-101", "purpose": "Preheat naphtha to 500°C"},
            {"type": "ConversionReactor","name": "R-101", "purpose": "Catalytic reformer"},
            {"type": "Cooler",           "name": "C-101", "purpose": "Cool reformate to 40°C"},
            {"type": "Flash",            "name": "V-101", "purpose": "Separate H2 from liquid reformate"},
            {"type": "ShortcutColumn",   "name": "T-101", "purpose": "Benzene column: benzene/toluene split"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Naphtha feed",
             "T_C": 25, "P_bar": 20, "total_flow_kg_hr": 1000,
             "composition": {
                 "n-Hexane": 0.40, "Cyclohexane": 0.50,
                 "Benzene": 0.05,  "Toluene": 0.05,
             }},
        ],
        "connections": [
            ("S-01",  "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),
        ],
        "unit_op_specs": {
            "H-101": {"outlet_T_C": 500},
            "C-101": {"outlet_T_C": 40},
            "V-101": {"P_bar": 20, "T_C": 40},
            "T-101": {
                "light_key": "Benzene", "heavy_key": "Toluene",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.01,
                "reflux_ratio": 3.0, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "Simplified — real reforming uses multiple reactor beds with interstage heating. "
            "H2 from V-101 is a valuable byproduct."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "ethylene_oxide": {
        "name": "Ethylene Oxide Production",
        "route": "Direct Oxidation (Silver Catalyst)",
        "description": (
            "Ethylene oxide (EO) is made by partial oxidation of ethylene over "
            "silver catalyst at 250–300°C, 10–20 bar. Selectivity ~80%."
        ),
        "reactions": [
            {
                "equation": "Ethylene + Oxygen → Ethylene Oxide",
                "type": "ConversionReactor",
                "conversion": 0.10,
                "temperature_C": 270,
                "pressure_bar": 15,
                "catalyst": "Ag/Al2O3",
            }
        ],
        "compounds": [
            "Ethylene", "Oxygen", "Ethylene Oxide",
            "Carbon Dioxide", "Water", "Nitrogen",
        ],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix ethylene + air/O2 + recycle"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat to 270°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Partial oxidation reactor"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool reactor effluent to 40°C"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Absorber — EO absorbed in water"},
            {"type": "ShortcutColumn",   "name": "T-101",   "purpose": "EO stripping/purification column"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Ethylene feed",
             "T_C": 25, "P_bar": 15, "total_flow_kg_hr": 500,
             "composition": {"Ethylene": 1.0}},
            {"name": "S-02", "type": "material", "description": "Air/Oxygen feed",
             "T_C": 25, "P_bar": 15, "total_flow_kg_hr": 300,
             "composition": {"Oxygen": 0.21, "Nitrogen": 0.79}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "V-101"),
            ("V-101",   "T-101"),
        ],
        "unit_op_specs": {
            "H-101": {"outlet_T_C": 270},
            "C-101": {"outlet_T_C": 40},
            "V-101": {"P_bar": 15, "T_C": 40},
            "T-101": {
                "light_key": "Ethylene Oxide", "heavy_key": "Water",
                "light_key_recovery": 0.98, "heavy_key_recovery": 0.01,
                "reflux_ratio": 2.0, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "Low single-pass conversion requires large recycle. "
            "CO2 scrubbing (omitted) removes combustion by-product."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "sulphuric_acid": {
        "name": "Sulphuric Acid Production",
        "route": "Contact Process",
        "description": (
            "Sulphuric acid via the Contact Process: burn sulphur to SO2, oxidise "
            "SO2 → SO3 over V2O5 catalyst, absorb SO3 into H2SO4 to make oleum."
        ),
        "reactions": [
            {
                "equation": "Sulfur + Oxygen → Sulfur Dioxide",
                "type": "ConversionReactor",
                "conversion": 1.0,
                "temperature_C": 1000,
                "pressure_bar": 1.5,
                "catalyst": "None (combustion)",
            },
            {
                "equation": "Sulfur Dioxide + Oxygen → Sulfur Trioxide",
                "type": "ConversionReactor",
                "conversion": 0.98,
                "temperature_C": 450,
                "pressure_bar": 1.5,
                "catalyst": "V2O5",
            },
        ],
        "compounds": [
            "Sulfur", "Oxygen", "Nitrogen",
            "Sulfur Dioxide", "Sulfur Trioxide", "Water", "Sulfuric Acid",
        ],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            # MIX-101 combines air + molten sulphur before the burner
            # (ConversionReactor only has one inlet, so a Mixer is required)
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix air + molten sulphur"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Sulphur burner (S → SO2) at 1000°C"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool combustion gas to 450°C"},
            {"type": "ConversionReactor","name": "R-102",   "purpose": "SO2 converter (SO2 → SO3) over V2O5"},
            {"type": "Cooler",           "name": "C-102",   "purpose": "Cool SO3 gas to 100°C"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Absorber (SO3 + H2SO4 → oleum)"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Dry air feed",
             "T_C": 25, "P_bar": 1.5, "total_flow_kg_hr": 1000,
             "composition": {"Oxygen": 0.21, "Nitrogen": 0.79}},
            {"name": "S-02", "type": "material", "description": "Molten sulphur feed",
             "T_C": 140, "P_bar": 1.5, "total_flow_kg_hr": 300,
             "composition": {"Sulfur": 1.0}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "R-102"),
            ("R-102",   "C-102"),
            ("C-102",   "V-101"),
        ],
        "unit_op_specs": {
            "C-101": {"outlet_T_C": 450},
            "C-102": {"outlet_T_C": 100},
            "V-101": {"P_bar": 1.5, "T_C": 100},
        },
        "notes": (
            "Real Contact Process uses double absorption for >99.5% conversion. "
            "Heat recovery between converter beds is important for energy efficiency."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "urea": {
        "name": "Urea Production",
        "route": "Stamicarbon CO2 Stripping Process",
        "description": (
            "Urea from NH3 + CO2: ammonium carbamate forms at 185°C, 150 bar, "
            "then dehydrates to urea. Overall conversion ~65–70%. "
            "Unconverted carbamate is decomposed and recycled."
        ),
        "reactions": [
            {
                "equation": "2 Ammonia + Carbon Dioxide → Urea + Water",
                "type": "ConversionReactor",
                "conversion": 0.65,
                "temperature_C": 185,
                "pressure_bar": 150,
                "catalyst": "None (thermal)",
            },
        ],
        "compounds": ["Ammonia", "Carbon Dioxide", "Water", "Urea"],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Compressor",       "name": "K-101",   "purpose": "Compress CO2 to 150 bar"},
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix NH3 + compressed CO2"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Urea synthesis reactor 185°C 150 bar"},
            {"type": "Flash",            "name": "V-101",   "purpose": "HP CO2 stripper (decompose carbamate)"},
            {"type": "Flash",            "name": "V-102",   "purpose": "LP decomposer"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Evaporator/concentrator"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Liquid ammonia feed",
             "T_C": 25, "P_bar": 20, "total_flow_kg_hr": 600,
             "composition": {"Ammonia": 1.0}},
            {"name": "S-02", "type": "material", "description": "CO2 feed",
             "T_C": 40, "P_bar": 5,  "total_flow_kg_hr": 750,
             "composition": {"Carbon Dioxide": 1.0}},
        ],
        "connections": [
            ("S-02",    "K-101"),
            ("K-101",   "MIX-101"),
            ("S-01",    "MIX-101"),
            ("MIX-101", "R-101"),
            ("R-101",   "V-101"),
            ("V-101",   "V-102"),
            ("V-102",   "H-101"),
        ],
        "unit_op_specs": {
            "K-101":  {"outlet_P_bar": 150, "efficiency": 0.75},
            "V-101":  {"P_bar": 150, "T_C": 185},
            "V-102":  {"P_bar": 5,   "T_C": 100},
            "H-101":  {"outlet_T_C": 140},
        },
        "notes": (
            "Simplified — real Stamicarbon process has HP/LP/vacuum decomposition stages, "
            "carbamate condenser, and prilling/granulation for solid urea product."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "acetone": {
        "name": "Acetone Production",
        "route": "Cumene Process (co-product with Phenol)",
        "description": (
            "Acetone is co-produced with phenol via the cumene process: "
            "benzene + propylene → cumene over acid catalyst, then oxidation "
            "and acid cleavage gives phenol + acetone. ~90% of world acetone."
        ),
        "reactions": [
            {
                "equation": "Benzene + Propylene → Isopropylbenzene",
                "type": "ConversionReactor",
                "conversion": 0.95,
                "temperature_C": 250,
                "pressure_bar": 30,
                "catalyst": "H3PO4/SiO2 or zeolite",
            },
        ],
        "compounds": [
            "Benzene", "Propylene", "Isopropylbenzene",
            "Acetone", "Phenol", "Water",
        ],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix benzene + propylene"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat to 250°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Alkylation reactor (cumene formation)"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool reactor effluent to 40°C"},
            {"type": "ShortcutColumn",   "name": "T-101",   "purpose": "Separate benzene from cumene"},
            {"type": "ShortcutColumn",   "name": "T-102",   "purpose": "Separate acetone from phenol"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Benzene feed",
             "T_C": 25, "P_bar": 30, "total_flow_kg_hr": 500,
             "composition": {"Benzene": 1.0}},
            {"name": "S-02", "type": "material", "description": "Propylene feed",
             "T_C": 25, "P_bar": 30, "total_flow_kg_hr": 300,
             "composition": {"Propylene": 1.0}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "T-101"),
            ("T-101",   "T-102"),
        ],
        "unit_op_specs": {
            "H-101": {"outlet_T_C": 250},
            "C-101": {"outlet_T_C": 40},
            "T-101": {
                "light_key": "Benzene", "heavy_key": "Isopropylbenzene",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.01,
                "reflux_ratio": 2.5, "condenser_P_bar": 1.013,
            },
            "T-102": {
                "light_key": "Acetone", "heavy_key": "Phenol",
                "light_key_recovery": 0.99, "heavy_key_recovery": 0.01,
                "reflux_ratio": 2.0, "condenser_P_bar": 1.013,
            },
        },
        "notes": (
            "Simplified — omits cumene oxidation and acid cleavage steps. "
            "Models alkylation + separation only; real process has additional oxidation reactor."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "cyclohexane": {
        "name": "Cyclohexane Production",
        "route": "Benzene Catalytic Hydrogenation + Sulfolane Extractive Distillation",
        "description": (
            "Cyclohexane (≥99 wt% purity) is produced by vapour-phase catalytic "
            "hydrogenation of benzene over a Ni/Al₂O₃ fixed-bed catalyst at 200 °C "
            "and 30 bar (ΔH_rxn = −208 kJ/mol, essentially irreversible, >99.9% conversion). "
            "Because cyclohexane (bp 80.7 °C) and benzene (bp 80.1 °C) form a "
            "near-azeotrope (α ≈ 1.02), conventional distillation cannot achieve product "
            "spec. Sulfolane (tetramethylene sulfone, bp 285 °C) is used as an extractive "
            "solvent: its high affinity for the aromatic π-system retains benzene in the "
            "liquid phase, raising the effective α to ~2.5 and allowing cyclohexane to "
            "leave as overhead distillate. A second column (solvent stripper) regenerates "
            "the sulfolane and recovers unreacted benzene for recycle. Unreacted H₂ is "
            "separated in a high-pressure flash, split 90/10 (recycle/purge), and "
            "recompressed before returning to the reactor feed mixer."
        ),
        "reactions": [
            {
                "equation": "Benzene + 3 Hydrogen → Cyclohexane",
                "type": "ConversionReactor",
                "conversion": 0.999,
                "temperature_C": 200,
                "pressure_bar": 30,
                "catalyst": "Ni/Al₂O₃ fixed bed",
            }
        ],
        "compounds": ["Benzene", "Hydrogen", "Cyclohexane", "Sulfolane"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            # ── Feed pressurisation ───────────────────────────────────────────
            {"type": "Pump",             "name": "P-01",
             "purpose": "Benzene feed pump: raise liquid benzene from storage pressure to reactor pressure (30 bar)"},
            {"type": "Compressor",       "name": "K-02",
             "purpose": "Fresh H₂ feed compressor: raise hydrogen supply (5 bar) to reactor pressure (30 bar)"},
            {"type": "Mixer",            "name": "MIX-03",
             "purpose": "Feed mixer: combine pressurised benzene (from P-01) + fresh H₂ (from K-02) + recycled H₂ (from K-19)"},
            # ── Reaction section ──────────────────────────────────────────────
            {"type": "Heater",           "name": "HEX-04",
             "purpose": "Feed preheater (HEX-01 in PFD): heat mixed feed to 200 °C using medium-pressure steam"},
            {"type": "ConversionReactor","name": "R-05",
             "purpose": "Fixed-bed hydrogenation reactor: C₆H₆ + 3 H₂ → C₆H₁₂, Ni/Al₂O₃, 200 °C, 30 bar, 99.9% conversion"},
            {"type": "Cooler",           "name": "HEX-06",
             "purpose": "Reactor effluent cooler (HEX-02 in PFD): cool from 200 °C to 40 °C using cooling water"},
            # ── Flash & H₂ recycle ────────────────────────────────────────────
            {"type": "Flash",            "name": "V-07",
             "purpose": "High-pressure flash drum: separate unreacted H₂ vapour from liquid cyclohexane/benzene at 30 bar, 40 °C"},
            {"type": "Splitter",         "name": "SPL-08",
             "purpose": "H₂ vapour splitter: 90% recycle fraction to K-19, 10% purge to prevent inert build-up"},
            {"type": "Valve",            "name": "VLV-09a",
             "purpose": "Liquid let-down valve: reduce flash liquid from 30 bar to column pressure (1.5 bar) before extractive distillation"},
            {"type": "Compressor",       "name": "K-19",
             "purpose": "Recycle H₂ compressor: recompress recycled H₂ from flash pressure back to 30 bar for return to MIX-03"},
            # ── Sulfolane make-up pump ────────────────────────────────────────
            {"type": "Pump",             "name": "P-09",
             "purpose": "Sulfolane recycle pump: pump regenerated sulfolane from T-13 bottoms back to T-10 solvent feed tray"},
            # ── Extractive distillation section ───────────────────────────────
            {"type": "ShortcutColumn",   "name": "T-10",
             "purpose": (
                 "Extractive distillation column: sulfolane solvent (S/F ≈ 4 mol/mol) "
                 "suppresses benzene volatility. Overhead = cyclohexane product (99+ wt%). "
                 "Bottoms = benzene dissolved in sulfolane → T-13 for solvent recovery."
             )},
            {"type": "ShortcutColumn",   "name": "T-13",
             "purpose": (
                 "Solvent recovery / benzene stripper: separate benzene from sulfolane under "
                 "moderate vacuum to limit reboiler temperature (sulfolane degrades >220 °C). "
                 "Overhead = recovered benzene → recycle to benzene feed. "
                 "Bottoms = regenerated sulfolane → P-09 → T-10 solvent inlet."
             )},
        ],
        "streams": [
            {
                "name": "BENZENE-FEED", "type": "material",
                "description": "Fresh liquid benzene feed at storage conditions",
                "T_C": 25, "P_bar": 1.013, "total_flow_kg_hr": 980,
                "composition": {
                    "Benzene": 1.0, "Hydrogen": 0.0,
                    "Cyclohexane": 0.0, "Sulfolane": 0.0,
                },
            },
            {
                "name": "H2-FEED", "type": "material",
                "description": "Fresh hydrogen feed from pipeline or PSA unit",
                "T_C": 25, "P_bar": 5.0, "total_flow_kg_hr": 80,
                "composition": {
                    "Benzene": 0.0, "Hydrogen": 1.0,
                    "Cyclohexane": 0.0, "Sulfolane": 0.0,
                },
            },
            {
                "name": "SULFOLANE-MAKEUP", "type": "material",
                "description": "Fresh sulfolane make-up (small stream to compensate losses; bulk solvent comes from P-09 recycle)",
                "T_C": 60, "P_bar": 1.5, "total_flow_kg_hr": 20,
                "composition": {
                    "Benzene": 0.0, "Hydrogen": 0.0,
                    "Cyclohexane": 0.0, "Sulfolane": 1.0,
                },
            },
        ],
        "connections": [
            # ── Feed pressurisation ───────────────────────────────────────────
            ("BENZENE-FEED",   "P-01"),
            ("P-01",           "MIX-03"),
            ("H2-FEED",        "K-02"),
            ("K-02",           "MIX-03"),
            # ── Reaction path ─────────────────────────────────────────────────
            ("MIX-03",         "HEX-04"),
            ("HEX-04",         "R-05"),
            ("R-05",           "HEX-06"),
            ("HEX-06",         "V-07"),
            # ── Flash outlets: VAPOUR port first, LIQUID port second ──────────
            # DWSIM Flash assigns: port 0 = vapour, port 1 = liquid.
            # Connection order here must match that port order.
            ("V-07",           "SPL-08"),    # port 0 (vapour) → H₂ splitter
            ("V-07",           "VLV-09a"),   # port 1 (liquid) → let-down valve
            # ── H₂ recycle loop (closed) ──────────────────────────────────────
            ("SPL-08",         "K-19"),      # recycle fraction (90%) → compressor
            ("K-19",           "MIX-03"),    # recompressed H₂ → feed mixer (loop closed)
            # SPL-08 purge port (10%) is a dead-end terminal stream in this build.
            # ── Extractive distillation ───────────────────────────────────────
            ("VLV-09a",        "T-10"),      # depressurised liquid feed → column
            ("SULFOLANE-MAKEUP","T-10"),     # small sulfolane make-up → column
            # T-10: port 0 = distillate (cyclohexane product), port 1 = bottoms
            ("T-10",           "T-13"),      # bottoms (benzene + sulfolane) → stripper
            # ── Solvent recovery & recycle loops (closed) ─────────────────────
            # T-13: port 0 = distillate (benzene), port 1 = bottoms (sulfolane)
            # Benzene distillate recycles to P-01 inlet (benzene feed loop).
            ("T-13",           "P-01"),      # recovered benzene → benzene feed pump
            # Sulfolane bottoms pump back to T-10 solvent tray.
            ("T-13",           "P-09"),      # sulfolane bottoms → recycle pump
            ("P-09",           "T-10"),      # pumped sulfolane → T-10 solvent inlet
        ],
        "unit_op_specs": {
            # Feed pressurisation
            "P-01":    {"outlet_P_bar": 30,   "efficiency": 0.75},
            "K-02":    {"outlet_P_bar": 30,   "efficiency": 0.75},
            # Preheater
            "HEX-04":  {"outlet_T_C": 200},
            # Reactor — outlet_T_C forces isothermal mode in DWSIM ConversionReactor
            "R-05":    {"outlet_T_C": 200},
            # Effluent cooler
            "HEX-06":  {"outlet_T_C": 40},
            # High-pressure flash
            "V-07":    {"T_C": 40, "P_bar": 30},
            # H₂ splitter: fraction 0 = recycle (90%), fraction 1 = purge (10%)
            "SPL-08":  {"split_fraction": 0.90},
            # Recycle compressor
            "K-19":    {"outlet_P_bar": 30,   "efficiency": 0.75},
            # Liquid let-down valve
            "VLV-09a": {"outlet_P_bar": 1.5},
            # Sulfolane recycle pump
            "P-09":    {"outlet_P_bar": 1.8,  "efficiency": 0.75},
            # T-10: Extractive distillation — cyclohexane (light) vs benzene (heavy)
            "T-10": {
                "light_key":          "Cyclohexane",
                "heavy_key":          "Benzene",
                "light_key_recovery": 0.99,
                "heavy_key_recovery": 0.99,
                "reflux_ratio":       5.0,
                "condenser_P_bar":    1.5,
                "reboiler_P_bar":     1.8,
                "condenser_type":     0,        # 0 = total condenser
            },
            # T-13: Solvent stripper — benzene (light) vs sulfolane (heavy)
            # Moderate vacuum to keep reboiler below sulfolane degradation temp (~220 °C)
            "T-13": {
                "light_key":          "Benzene",
                "heavy_key":          "Sulfolane",
                "light_key_recovery": 0.99,
                "heavy_key_recovery": 0.99,
                "reflux_ratio":       2.0,
                "condenser_P_bar":    0.15,     # ~150 mbar vacuum
                "reboiler_P_bar":     0.20,
                "condenser_type":     0,
            },
        },
        "notes": (
            "PFD TOPOLOGY (matches standard industrial layout):\n"
            "  BENZENE-FEED → P-01 → MIX-03\n"
            "  H2-FEED      → K-02 → MIX-03\n"
            "  MIX-03 → HEX-04 (steam) → R-05 (reactor) → HEX-06 (CW) → V-07 (flash)\n"
            "  V-07 vapour → SPL-08 → [purge | K-19 → MIX-03]  (H₂ recycle loop)\n"
            "  V-07 liquid → VLV-09a → T-10 ← SULFOLANE-MAKEUP\n"
            "                        ← P-09 ← T-13 bottoms      (sulfolane recycle loop)\n"
            "  T-10 distillate = cyclohexane product\n"
            "  T-10 bottoms    → T-13 → distillate (benzene) → P-01  (benzene recycle)\n"
            "                         → bottoms (sulfolane)  → P-09  (solvent recycle)\n\n"
            "RECYCLE LOOPS (all closed in this build):\n"
            "  1. H₂ recycle:       SPL-08 → K-19 → MIX-03\n"
            "  2. Benzene recycle:  T-13 distillate → P-01\n"
            "  3. Sulfolane recycle: T-13 bottoms → P-09 → T-10\n\n"
            "KNOWN DWSIM ISSUES:\n"
            "  • T-13 has TWO outlet ports; DWSIM ShortcutColumn may only expose one "
            "outlet in scripting. If the benzene-recycle connection (T-13 → P-01) fails, "
            "leave it open-loop and manually connect in the GUI.\n"
            "  • Sulfolane DWSIM name: try 'Sulfolane', 'Tetramethylene sulfone', "
            "or search by CAS 126-33-0.\n"
            "  • SPL-08 purge port (10%) is a terminal dead-end stream — add a "
            "ProductStream block in the GUI if purge flow data are required."
        ),
    },

    # ──────────────────────────────────────────────────────────────────────────
    "hydrogen": {
        "name": "Hydrogen Production",
        "route": "Steam Methane Reforming (SMR)",
        "description": (
            "H2 from steam reforming of natural gas: CH4 + H2O → CO + 3H2 at "
            "850°C over Ni catalyst, then water-gas shift CO + H2O → CO2 + H2 at 350°C. "
            "CO2 removed by PSA or amine scrubbing."
        ),
        "reactions": [
            {
                "equation": "Methane + Water → Carbon Monoxide + 3 Hydrogen",
                "type": "ConversionReactor",
                "conversion": 0.80,
                "temperature_C": 850,
                "pressure_bar": 25,
                "catalyst": "Ni/Al2O3",
            },
            {
                "equation": "Carbon Monoxide + Water → Carbon Dioxide + Hydrogen",
                "type": "ConversionReactor",
                "conversion": 0.90,
                "temperature_C": 350,
                "pressure_bar": 25,
                "catalyst": "Fe2O3/Cr2O3 (HTS) then Cu/ZnO (LTS)",
            },
        ],
        "compounds": [
            "Methane", "Water", "Carbon Monoxide",
            "Hydrogen", "Carbon Dioxide",
        ],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer",            "name": "MIX-101", "purpose": "Mix methane + steam"},
            {"type": "Heater",           "name": "H-101",   "purpose": "Preheat to 850°C"},
            {"type": "ConversionReactor","name": "R-101",   "purpose": "Steam reformer (primary)"},
            {"type": "Cooler",           "name": "C-101",   "purpose": "Cool to WGS temperature 350°C"},
            {"type": "ConversionReactor","name": "R-102",   "purpose": "Water-gas shift reactor"},
            {"type": "Cooler",           "name": "C-102",   "purpose": "Cool shifted gas to 40°C"},
            {"type": "Flash",            "name": "V-101",   "purpose": "Condense water, separate H2-rich gas"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Natural gas (methane) feed",
             "T_C": 25, "P_bar": 25, "total_flow_kg_hr": 500,
             "composition": {"Methane": 0.95, "Carbon Dioxide": 0.05}},
            {"name": "S-02", "type": "material", "description": "Steam feed",
             "T_C": 250, "P_bar": 25, "total_flow_kg_hr": 1500,
             "composition": {"Water": 1.0}},
        ],
        "connections": [
            ("S-01",    "MIX-101"),
            ("S-02",    "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101",   "R-101"),
            ("R-101",   "C-101"),
            ("C-101",   "R-102"),
            ("R-102",   "C-102"),
            ("C-102",   "V-101"),
        ],
        "unit_op_specs": {
            "H-101":  {"outlet_T_C": 850},
            "C-101":  {"outlet_T_C": 350},
            "C-102":  {"outlet_T_C": 40},
            "V-101":  {"P_bar": 25, "T_C": 40},
        },
        "notes": (
            "PSA (Pressure Swing Adsorption) for final H2 purification is omitted. "
            "Steam-to-carbon ratio 3:1 prevents coking. "
            "Real SMR plants include extensive heat recovery from flue gas."
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Lookup helpers
# ──────────────────────────────────────────────────────────────────────────────

def lookup_process(chemical: str) -> dict:
    """Look up a chemical process from the built-in library."""
    import copy
    key = chemical.lower().strip()
    aliases = {
        "etoh": "ethanol",
        "meoh": "methanol",
        "nh3": "ammonia",
        "acoh": "acetic_acid",
        "acetic acid": "acetic_acid",
        "hoac": "acetic_acid",
        "h2so4": "sulphuric_acid",
        "sulfuric acid": "sulphuric_acid",
        "sulphuric acid": "sulphuric_acid",
        "sulphuric_acid": "sulphuric_acid",
        "eo": "ethylene_oxide",
        "ethylene oxide": "ethylene_oxide",
        "h2": "hydrogen",
        "co(nh2)2": "urea",
        "phenol": "acetone",
    }
    key = aliases.get(key, key)
    if key in PROCESS_LIBRARY:
        process = copy.deepcopy(PROCESS_LIBRARY[key])
        return {"found": True, "chemical": key, **process}
    return {
        "found": False,
        "chemical": chemical,
        "message": f"'{chemical}' not in built-in library.",
        "available_chemicals": list(PROCESS_LIBRARY.keys()),
        "suggestion": (
            "Claude can still design a process for this chemical using its own "
            "chemistry knowledge. Just describe the process you want and use "
            "the simulation tools directly."
        ),
    }


def list_available_processes() -> list[str]:
    """Return list of all chemicals in the built-in library."""
    return list(PROCESS_LIBRARY.keys())


if __name__ == "__main__":
    import json
    for name, proc in PROCESS_LIBRARY.items():
        print(f"{name}: {len(proc['unit_operations'])} ops, "
              f"{len(proc['connections'])} connections, "
              f"{len(proc.get('unit_op_specs', {}))} specs")
