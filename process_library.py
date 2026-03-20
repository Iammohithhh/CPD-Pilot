"""
process_library.py — Built-in knowledge of common industrial chemical processes.

WHY THIS EXISTS:
When a student says "design an ethanol plant", Claude needs a starting blueprint.
This file provides structured data about ~10 common CPD chemicals:
- What's the industrial synthesis route?
- What unit operations are needed?
- What reactions occur?
- What are typical operating conditions?
- Which thermodynamic model to use?

Claude uses this as a STARTING POINT, then customizes via DWSIM tools.

LEARNING NOTE:
Each process here is a simplified version of the real industrial route.
Real plants have more recycles, heat integration, and control systems.
These are appropriate for a college CPD course assignment.
"""

# Each process is a dictionary with a standard structure.
# Claude reads this, then builds the DWSIM flowsheet step by step.

PROCESS_LIBRARY = {
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
                "equation": "C2H4 + H2O → C2H5OH",
                "type": "ConversionReactor",
                "conversion": 0.05,  # 5% single-pass on ethylene
                "temperature_C": 300,
                "pressure_bar": 70,
                "catalyst": "H3PO4 on silica gel",
            }
        ],
        "compounds": ["Ethylene", "Water", "Ethanol"],
        "thermo_model": "NRTL",  # Polar system (water + ethanol)
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix fresh ethylene + recycle"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat feed to 300°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Hydration reactor"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool reactor effluent"},
            {"type": "Flash", "name": "V-101", "purpose": "Separate vapor (unreacted C2H4) from liquid"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "Distillation: ethanol/water separation"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh ethylene feed",
             "T_C": 25, "P_bar": 70, "total_flow_kg_hr": 100,
             "composition": {"Ethylene": 0.99, "Water": 0.01}},
            {"name": "S-02", "type": "material", "description": "Fresh water feed",
             "T_C": 25, "P_bar": 70, "total_flow_kg_hr": 200,
             "composition": {"Ethylene": 0.0, "Water": 1.0}},
        ],
        "connections": [
            # (from_stream_or_unit, to_stream_or_unit)
            ("S-01", "MIX-101"),
            ("S-02", "MIX-101"),   # water feed into mixer (was missing!)
            ("MIX-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),  # liquid outlet to column
        ],
        "notes": (
            "The vapor from V-101 (unreacted ethylene) is recycled back to MIX-101. "
            "T-101 produces ethanol as distillate and water as bottoms. "
            "Real plants use azeotropic distillation or molecular sieves for >95% ethanol."
        ),
    },

    "methanol": {
        "name": "Methanol Production",
        "route": "Syngas Conversion (ICI Low-Pressure Process)",
        "description": (
            "Methanol is synthesized from syngas (CO + H2) over a Cu/ZnO/Al2O3 catalyst "
            "at 250°C and 50-100 bar. The reaction is exothermic and equilibrium-limited. "
            "Single-pass conversion is ~25%. Crude methanol is purified by distillation."
        ),
        "reactions": [
            {
                "equation": "CO + 2H2 → CH3OH",
                "type": "ConversionReactor",
                "conversion": 0.25,
                "temperature_C": 250,
                "pressure_bar": 80,
                "catalyst": "Cu/ZnO/Al2O3",
            },
            {
                "equation": "CO2 + 3H2 → CH3OH + H2O",
                "type": "ConversionReactor",
                "conversion": 0.15,
                "temperature_C": 250,
                "pressure_bar": 80,
                "catalyst": "Cu/ZnO/Al2O3",
            },
        ],
        "compounds": [
            "Carbon Monoxide", "Hydrogen", "Methanol", "Water",
            "Carbon Dioxide", "Nitrogen",
        ],
        "thermo_model": "Peng-Robinson",  # Gas-phase dominant
        "unit_operations": [
            {"type": "Compressor", "name": "K-101", "purpose": "Compress syngas to 80 bar"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 250°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Methanol synthesis reactor"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool reactor effluent to 40°C"},
            {"type": "Flash", "name": "V-101", "purpose": "Separate unreacted gas from crude methanol"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "Purify methanol (remove water + lights)"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh syngas feed",
             "T_C": 40, "P_bar": 30, "total_flow_kg_hr": 1000,
             "composition": {"Carbon Monoxide": 0.30, "Hydrogen": 0.60,
                             "Carbon Dioxide": 0.05, "Nitrogen": 0.05}},
        ],
        "connections": [
            ("S-01", "K-101"),
            ("K-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),
        ],
        "notes": (
            "Unreacted gas from V-101 is recycled (with a small purge to prevent N2 buildup). "
            "T-101 removes dissolved gases as distillate and water as bottoms; "
            "methanol is the side draw or a second column is used."
        ),
    },

    "ammonia": {
        "name": "Ammonia Production",
        "route": "Haber-Bosch Process",
        "description": (
            "Ammonia is made from nitrogen and hydrogen at extreme conditions: "
            "400-500°C, 150-300 bar, over an iron catalyst (Fe3O4 + promoters). "
            "Equilibrium conversion is low (~15%), so massive recycle is needed. "
            "Product ammonia is condensed out at -33°C."
        ),
        "reactions": [
            {
                "equation": "N2 + 3H2 → 2NH3",
                "type": "EquilibriumReactor",
                "temperature_C": 450,
                "pressure_bar": 200,
                "catalyst": "Promoted iron (Fe3O4 + K2O + Al2O3)",
            }
        ],
        "compounds": ["Nitrogen", "Hydrogen", "Ammonia", "Argon"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix fresh feed + recycle"},
            {"type": "Compressor", "name": "K-101", "purpose": "Compress to 200 bar"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 450°C"},
            {"type": "EquilibriumReactor", "name": "R-101", "purpose": "Ammonia synthesis reactor"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool to condense ammonia (-33°C)"},
            {"type": "Flash", "name": "V-101", "purpose": "Separate liquid NH3 from unreacted gas"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Fresh synthesis gas (1:3 N2:H2)",
             "T_C": 25, "P_bar": 30, "total_flow_kg_hr": 1000,
             "composition": {"Nitrogen": 0.25, "Hydrogen": 0.74, "Argon": 0.01}},
        ],
        "connections": [
            ("S-01", "MIX-101"),
            ("MIX-101", "K-101"),
            ("K-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
        ],
        "notes": (
            "Vapor from V-101 (unreacted N2+H2) recycles to MIX-101 with a small purge "
            "to remove accumulated argon. Liquid NH3 from V-101 is the product. "
            "Real Haber-Bosch plants include shift converters and CO2 removal upstream."
        ),
    },

    "acetic_acid": {
        "name": "Acetic Acid Production",
        "route": "Methanol Carbonylation (Monsanto/Cativa Process)",
        "description": (
            "Acetic acid is made by reacting methanol with carbon monoxide "
            "in the liquid phase using a rhodium-iodide catalyst (Monsanto) "
            "or iridium-iodide (Cativa) at 150-200°C and 30-60 bar. "
            "Selectivity is >99%."
        ),
        "reactions": [
            {
                "equation": "CH3OH + CO → CH3COOH",
                "type": "ConversionReactor",
                "conversion": 0.99,
                "temperature_C": 180,
                "pressure_bar": 40,
                "catalyst": "Rh/HI (Monsanto catalyst)",
            }
        ],
        "compounds": ["Methanol", "Carbon Monoxide", "Acetic Acid", "Water",
                       "Methyl Iodide", "Hydrogen Iodide"],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix methanol + CO feeds"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 180°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Carbonylation reactor (liquid phase)"},
            {"type": "Flash", "name": "V-101", "purpose": "Flash off dissolved CO + lights"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "Light ends column (remove HI, MeI)"},
            {"type": "ShortcutColumn", "name": "T-102", "purpose": "Product column (pure acetic acid)"},
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
            ("S-01", "MIX-101"),
            ("S-02", "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "V-101"),
            ("V-101", "T-101"),
            ("T-101", "T-102"),
        ],
        "notes": (
            "T-101 recovers catalyst components (HI, MeI) as distillate for recycle. "
            "T-102 gives pure acetic acid as distillate, water as bottoms. "
            "Simplified — real Cativa process has more complex catalyst recovery."
        ),
    },

    "benzene": {
        "name": "Benzene Production",
        "route": "Catalytic Reforming + Extraction",
        "description": (
            "Benzene is produced by catalytic reforming of naphtha, followed by "
            "solvent extraction (Sulfolane process) to separate benzene from "
            "non-aromatic hydrocarbons. The reformate contains benzene, toluene, "
            "xylenes (BTX) and paraffins."
        ),
        "reactions": [
            {
                "equation": "C6H12 → C6H6 + 3H2 (cyclohexane dehydrogenation)",
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
            {"type": "Heater", "name": "H-101", "purpose": "Preheat naphtha feed to 500°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Catalytic reformer"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool reformate"},
            {"type": "Flash", "name": "V-101", "purpose": "Separate H2 from liquid reformate"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "Benzene column (separate benzene from heavier BTX)"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Naphtha feed",
             "T_C": 25, "P_bar": 20, "total_flow_kg_hr": 1000,
             "composition": {"n-Hexane": 0.40, "Cyclohexane": 0.50, "Benzene": 0.05, "Toluene": 0.05}},
        ],
        "connections": [
            ("S-01", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),
        ],
        "notes": (
            "Simplified model — real reforming uses multiple reactor beds with "
            "interstage heating. Extraction step (Sulfolane) is omitted for simplicity. "
            "H2 from V-101 is a valuable byproduct."
        ),
    },

    "ethylene_oxide": {
        "name": "Ethylene Oxide Production",
        "route": "Direct Oxidation (Silver Catalyst)",
        "description": (
            "Ethylene oxide (EO) is made by partial oxidation of ethylene over "
            "a silver catalyst at 250-300°C and 10-20 bar. Selectivity is ~80% "
            "(competing total combustion to CO2 + H2O). EO is absorbed in water."
        ),
        "reactions": [
            {
                "equation": "C2H4 + 0.5 O2 → C2H4O",
                "type": "ConversionReactor",
                "conversion": 0.10,
                "temperature_C": 270,
                "pressure_bar": 15,
                "catalyst": "Ag/Al2O3",
            }
        ],
        "compounds": ["Ethylene", "Oxygen", "Ethylene Oxide", "Carbon Dioxide", "Water", "Nitrogen"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix ethylene + air/O2 + recycle"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 270°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Partial oxidation reactor"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool reactor effluent"},
            {"type": "Flash", "name": "V-101", "purpose": "Absorber — EO absorbed in water"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "EO stripping/purification column"},
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
            ("S-01", "MIX-101"),
            ("S-02", "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "V-101"),
            ("V-101", "T-101"),
        ],
        "notes": (
            "Low single-pass conversion requires large recycle. "
            "CO2 is removed by scrubbing (omitted here). "
            "EO is highly reactive — downstream used for ethylene glycol production."
        ),
    },

    "sulphuric_acid": {
        "name": "Sulphuric Acid Production",
        "route": "Contact Process",
        "description": (
            "Sulphuric acid is made by the Contact Process: burn sulphur to SO2, "
            "oxidize SO2 to SO3 over V2O5 catalyst, then absorb SO3 in concentrated "
            "H2SO4 to make oleum, which is diluted to give product acid."
        ),
        "reactions": [
            {
                "equation": "S + O2 → SO2",
                "type": "ConversionReactor",
                "conversion": 1.0,
                "temperature_C": 1000,
                "pressure_bar": 1.5,
                "catalyst": "None (combustion)",
            },
            {
                "equation": "2 SO2 + O2 → 2 SO3",
                "type": "EquilibriumReactor",
                "temperature_C": 450,
                "pressure_bar": 1.5,
                "catalyst": "V2O5",
            },
        ],
        "compounds": ["Sulfur", "Oxygen", "Nitrogen", "Sulfur Dioxide",
                       "Sulfur Trioxide", "Water", "Sulfuric Acid"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Sulphur burner (S → SO2)"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool SO2 gas to 450°C"},
            {"type": "EquilibriumReactor", "name": "R-102", "purpose": "Converter (SO2 → SO3)"},
            {"type": "Cooler", "name": "C-102", "purpose": "Cool SO3 gas"},
            {"type": "Flash", "name": "V-101", "purpose": "Absorber (SO3 + H2SO4 → oleum)"},
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
            ("S-02", "R-101"),
            ("S-01", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "R-102"),
            ("R-102", "C-102"),
            ("C-102", "V-101"),
        ],
        "notes": (
            "Real Contact Process uses double absorption (2 absorbers) for >99.5% conversion. "
            "Simplified to single pass here. Heat recovery between converter beds is important "
            "for energy efficiency."
        ),
    },

    "urea": {
        "name": "Urea Production",
        "route": "Stamicarbon CO2 Stripping Process",
        "description": (
            "Urea is made from ammonia and CO2 in two steps: first ammonium carbamate "
            "forms at 180-200°C and 150 bar, then carbamate dehydrates to urea. "
            "Overall conversion ~65-70%. Unconverted carbamate is decomposed and recycled."
        ),
        "reactions": [
            {
                "equation": "2 NH3 + CO2 → NH2COONH4 (ammonium carbamate)",
                "type": "ConversionReactor",
                "conversion": 0.95,
                "temperature_C": 185,
                "pressure_bar": 150,
                "catalyst": "None (thermal)",
            },
            {
                "equation": "NH2COONH4 → (NH2)2CO + H2O (dehydration to urea)",
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
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix NH3 + CO2 feeds"},
            {"type": "Compressor", "name": "K-101", "purpose": "Compress CO2 to 150 bar"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Urea synthesis reactor"},
            {"type": "Flash", "name": "V-101", "purpose": "CO2 stripper (decompose carbamate)"},
            {"type": "Flash", "name": "V-102", "purpose": "LP decomposer"},
            {"type": "Heater", "name": "H-101", "purpose": "Evaporator/concentrator"},
        ],
        "streams": [
            {"name": "S-01", "type": "material", "description": "Liquid ammonia feed",
             "T_C": 25, "P_bar": 20, "total_flow_kg_hr": 600,
             "composition": {"Ammonia": 1.0}},
            {"name": "S-02", "type": "material", "description": "CO2 feed",
             "T_C": 40, "P_bar": 5, "total_flow_kg_hr": 750,
             "composition": {"Carbon Dioxide": 1.0}},
        ],
        "connections": [
            ("S-02", "K-101"),
            ("K-101", "MIX-101"),
            ("S-01", "MIX-101"),
            ("MIX-101", "R-101"),
            ("R-101", "V-101"),
            ("V-101", "V-102"),
            ("V-102", "H-101"),
        ],
        "notes": (
            "Simplified — real Stamicarbon process has HP/LP/vacuum decomposition stages, "
            "carbamate condenser, and prilling/granulation tower for solid urea product."
        ),
    },

    "acetone": {
        "name": "Acetone Production",
        "route": "Cumene Process (co-product with Phenol)",
        "description": (
            "Acetone is produced as a co-product with phenol via the cumene process: "
            "benzene + propylene → cumene → cumene hydroperoxide → phenol + acetone. "
            "This is the dominant industrial route (~90% of world acetone)."
        ),
        "reactions": [
            {
                "equation": "C6H6 + C3H6 → C6H5CH(CH3)2 (cumene)",
                "type": "ConversionReactor",
                "conversion": 0.95,
                "temperature_C": 250,
                "pressure_bar": 30,
                "catalyst": "H3PO4/SiO2 or zeolite",
            },
        ],
        "compounds": ["Benzene", "Propylene", "Isopropylbenzene", "Acetone",
                       "Phenol", "Water"],
        "thermo_model": "NRTL",
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix benzene + propylene"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 250°C"},
            {"type": "ConversionReactor", "name": "R-101", "purpose": "Alkylation reactor (cumene formation)"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool reactor effluent"},
            {"type": "ShortcutColumn", "name": "T-101", "purpose": "Separate cumene from unreacted benzene"},
            {"type": "ShortcutColumn", "name": "T-102", "purpose": "Separate acetone from phenol"},
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
            ("S-01", "MIX-101"),
            ("S-02", "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "T-101"),
            ("T-101", "T-102"),
        ],
        "notes": (
            "Simplified — omits cumene oxidation and acid cleavage steps. "
            "In reality: cumene is first oxidized to cumene hydroperoxide (CHP), "
            "then CHP is cleaved with acid to give phenol + acetone. "
            "Here we model just the alkylation + separation for simplicity."
        ),
    },

    "hydrogen": {
        "name": "Hydrogen Production",
        "route": "Steam Methane Reforming (SMR)",
        "description": (
            "Hydrogen is produced by steam reforming of natural gas (methane). "
            "CH4 + H2O → CO + 3H2 at 800-900°C over Ni catalyst, followed by "
            "water-gas shift (CO + H2O → CO2 + H2) at 350°C. "
            "CO2 is removed by amine scrubbing or PSA."
        ),
        "reactions": [
            {
                "equation": "CH4 + H2O → CO + 3H2",
                "type": "EquilibriumReactor",
                "temperature_C": 850,
                "pressure_bar": 25,
                "catalyst": "Ni/Al2O3",
            },
            {
                "equation": "CO + H2O → CO2 + H2",
                "type": "ConversionReactor",
                "conversion": 0.90,
                "temperature_C": 350,
                "pressure_bar": 25,
                "catalyst": "Fe2O3/Cr2O3 (HTS) then Cu/ZnO (LTS)",
            },
        ],
        "compounds": ["Methane", "Water", "Carbon Monoxide", "Hydrogen",
                       "Carbon Dioxide"],
        "thermo_model": "Peng-Robinson",
        "unit_operations": [
            {"type": "Mixer", "name": "MIX-101", "purpose": "Mix methane + steam"},
            {"type": "Heater", "name": "H-101", "purpose": "Preheat to 850°C"},
            {"type": "EquilibriumReactor", "name": "R-101", "purpose": "Steam reformer"},
            {"type": "Cooler", "name": "C-101", "purpose": "Cool to WGS temperature (350°C)"},
            {"type": "ConversionReactor", "name": "R-102", "purpose": "Water-gas shift reactor"},
            {"type": "Cooler", "name": "C-102", "purpose": "Cool shifted gas"},
            {"type": "Flash", "name": "V-101", "purpose": "Condense water, separate H2-rich gas"},
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
            ("S-01", "MIX-101"),
            ("S-02", "MIX-101"),
            ("MIX-101", "H-101"),
            ("H-101", "R-101"),
            ("R-101", "C-101"),
            ("C-101", "R-102"),
            ("R-102", "C-102"),
            ("C-102", "V-101"),
        ],
        "notes": (
            "Simplified — omits PSA (Pressure Swing Adsorption) unit for final H2 purification. "
            "Steam-to-carbon ratio is typically 3:1 to prevent coking. "
            "Real SMR plants include heat recovery from flue gas."
        ),
    },
}


def lookup_process(chemical: str) -> dict:
    """
    Look up a chemical process from the built-in library.

    Args:
        chemical: Name of the target chemical (e.g., "ethanol", "ammonia")

    Returns:
        Dictionary with process details, or error if not found.
    """
    # Normalize: lowercase, strip whitespace, handle common aliases
    key = chemical.lower().strip()

    # Common aliases
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
        "acetone": "acetone",
        "phenol": "acetone",  # co-product from same process
    }

    key = aliases.get(key, key)

    if key in PROCESS_LIBRARY:
        import copy
        process = copy.deepcopy(PROCESS_LIBRARY[key])
        return {
            "found": True,
            "chemical": key,
            **process,
        }
    else:
        available = list(PROCESS_LIBRARY.keys())
        return {
            "found": False,
            "chemical": chemical,
            "message": f"'{chemical}' not in built-in library.",
            "available_chemicals": available,
            "suggestion": (
                "Claude can still design a process for this chemical using its own "
                "chemistry knowledge. Just describe the process you want and use "
                "the simulation tools directly."
            ),
        }


def list_available_processes() -> list[str]:
    """Return list of all chemicals in the built-in library."""
    return list(PROCESS_LIBRARY.keys())


# Quick test
if __name__ == "__main__":
    import json

    # Test lookup
    result = lookup_process("ethanol")
    print(f"Found: {result['name']}")
    print(f"Route: {result['route']}")
    print(f"Unit ops: {len(result['unit_operations'])}")
    print(f"Compounds: {result['compounds']}")
    print()

    # Test alias
    result = lookup_process("NH3")
    print(f"Found: {result['name']}")
    print()

    # Test missing
    result = lookup_process("polyethylene")
    print(f"Found: {result['found']}")
    print(f"Available: {result['available_chemicals']}")
