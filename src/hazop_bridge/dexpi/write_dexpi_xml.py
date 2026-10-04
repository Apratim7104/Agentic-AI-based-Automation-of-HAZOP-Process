# -*- coding: utf-8 -*-
# ============================================================
#   write_dexpi_xml.py  -  DEXPI 1.3 XML Writer
#   Generated from uploaded simulation flowsheet image
#   Batch Reactor: Acetic Acid + Sodium Bicarbonate
#   Full topology: 3 Pumps, 3 Valves, Mixer, Reactor,
#                  HX, Gas-Liquid Separator, 3 Tanks
# ============================================================

import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

print("--- BUILDING DEXPI XML (Full Flowsheet - HAZOP Ready) ---")

# ── DEXPI Class Map ────────────────────────────────────────────────────────────
DEXPI_CLASS_MAP = {
    "RCT_Conversion" : "Reactor",
    "RCT_CSTR"       : "Reactor",
    "RCT_PFR"        : "Reactor",
    "NodeIn"         : "Header",
    "NodeOut"        : "Header",
    "Mixer"          : "Header",
    "Splitter"       : "Header",
    "HeatExchanger"  : "HeatExchanger",
    "Pump"           : "Pump",
    "Compressor"     : "Compressor",
    "Valve"          : "Valve",
    "Tank"           : "Vessel",
    "Vessel"         : "Vessel",
    "Column"         : "Column",
    "Separator"      : "Vessel",
}

def get_dexpi_class(dwsim_type):
    return DEXPI_CLASS_MAP.get(dwsim_type, "ProcessEquipment")

# ── Namespaces ─────────────────────────────────────────────────────────────────
NS  = "http://dexpi.org/schema/1.3"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("",    NS)
ET.register_namespace("xsi", XSI)

# ── Root Element ───────────────────────────────────────────────────────────────
root = ET.Element(f"{{{NS}}}PlantModel", attrib={
    "SchemaVersion"             : "1.3",
    f"{{{XSI}}}schemaLocation" : (
        "http://dexpi.org/schema/1.3 "
        "http://dexpi.org/schema/1.3/DEXPI.xsd"
    )
})

# ── MetaData ───────────────────────────────────────────────────────────────────
meta = ET.SubElement(root, f"{{{NS}}}MetaData")
ET.SubElement(meta, f"{{{NS}}}PlantInformation", attrib={
    "Tag"           : "BatchReactor-Plant",
    "Name"          : "Batch Reactor - Acetic Acid and Sodium Bicarbonate",
    "CreationDate"  : datetime.now().isoformat(),
    "CreatedBy"     : "DWSIM Python Automation Bridge",
    "SchemaVersion" : "DEXPI 1.3",
    "Description"   : (
        "Full flowsheet: Feed preparation (2 pumps + 2 valves), "
        "mixing, conversion reactor, heat exchanger (E-401), "
        "gas-liquid separator (V-501), TANK-1, "
        "Gas Collection Tank, Product Collection Tank, "
        "cooling loop (PUMP-3 + VALVE-3)"
    )
})

# ── Equipment Builder ──────────────────────────────────────────────────────────
_nozzle_counter = [1]   # mutable so nested fn can increment

def add_equipment(parent, eq_id, tag, dwsim_type, nozzle_tags,
                  description="", extra_attrs=None):
    dexpi_class = get_dexpi_class(dwsim_type)
    eq_elem = ET.SubElement(parent, f"{{{NS}}}Equipment", attrib={
        "ID"             : f"Equipment-{eq_id}",
        "Tag"            : tag,
        "TagName"        : tag,
        "ComponentClass" : dexpi_class,
        "ComponentName"  : tag,
        "ComponentType"  : dwsim_type,
        "Description"    : description,
    })

    gen_attrs = ET.SubElement(eq_elem, f"{{{NS}}}GenericAttributes")
    ET.SubElement(gen_attrs, f"{{{NS}}}GenericAttribute", attrib={
        "Name": "DWSIMObjectType", "Value": dwsim_type
    })
    ET.SubElement(gen_attrs, f"{{{NS}}}GenericAttribute", attrib={
        "Name": "Source", "Value": "DWSIM Automation Export"
    })
    if extra_attrs:
        for k, v in extra_attrs.items():
            ET.SubElement(gen_attrs, f"{{{NS}}}GenericAttribute", attrib={
                "Name": k, "Value": str(v)
            })

    for nozzle_tag in nozzle_tags:
        ET.SubElement(eq_elem, f"{{{NS}}}Nozzle", attrib={
            "ID"      : f"Nozzle-{_nozzle_counter[0]}",
            "Tag"     : nozzle_tag,
            "TagName" : nozzle_tag,
            "Function": "Process"
        })
        _nozzle_counter[0] += 1

    return eq_elem

# ══════════════════════════════════════════════════════════════════════════════
#  EQUIPMENT  (read from flowsheet image, left-to-right, top-to-bottom)
# ══════════════════════════════════════════════════════════════════════════════

# ── Acetic Acid Feed side ──────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "PUMP-1",
    tag         = "PUMP-1",
    dwsim_type  = "Pump",
    nozzle_tags = ["Inlet", "Outlet", "Energy-Port"],
    description = "Acetic Acid Feed Pump",
    extra_attrs = {"EnergyStream": "E2", "NominalPressure_bar": "1.01325"}
)

add_equipment(root,
    eq_id       = "VALVE-2",
    tag         = "VALVE-2",
    dwsim_type  = "Valve",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "Acetic Acid Feed Control Valve (stream 18 -&gt; 19)"
)

# ── Sodium Bicarbonate Feed side ───────────────────────────────────────────────
add_equipment(root,
    eq_id       = "PUMP-2",
    tag         = "PUMP-2",
    dwsim_type  = "Pump",
    nozzle_tags = ["Inlet", "Outlet", "Energy-Port"],
    description = "Sodium Bicarbonate Feed Pump",
    extra_attrs = {"EnergyStream": "E3", "NominalPressure_bar": "1.01325"}
)

add_equipment(root,
    eq_id       = "VALVE-1",
    tag         = "VALVE-1",
    dwsim_type  = "Valve",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "Sodium Bicarbonate Feed Control Valve (stream 16 -&gt; 17)"
)

# ── Feed Mixer ─────────────────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "MIX-1",
    tag         = "MIX-1",
    dwsim_type  = "Mixer",
    nozzle_tags = ["Inlet-Acid", "Inlet-Bicarb", "Outlet"],
    description = "Feed Mixer: combines acid stream 19 and bicarb stream 17"
)

# ── Conversion Reactor ─────────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "Conversion-Reactor",
    tag         = "Conversion reactor",
    dwsim_type  = "RCT_Conversion",
    nozzle_tags = ["Feed-Inlet", "Outlet-1-Gas", "Outlet-2-Liquid", "Energy-Port"],
    description = "Conversion Reactor: CH3COOH + NaHCO3 reaction",
    extra_attrs = {
        "EnergyStream"    : "E4",
        "EnergyDuty_kW"   : "-0.02",
        "ReactionType"    : "Conversion",
        "Reagent-A"       : "Acetic Acid",
        "Reagent-B"       : "Sodium Bicarbonate",
    }
)

# ── Heat Exchanger E-401 ───────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "E-401",
    tag         = "E-401",
    dwsim_type  = "HeatExchanger",
    nozzle_tags = ["Hot-Inlet", "Hot-Outlet", "Cold-Inlet", "Cold-Outlet"],
    description = "Heat Exchanger E-401: cools Outlet 2 before separator"
)

# ── Gas-Liquid Separator V-501 ─────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "V-501",
    tag         = "V-501",
    dwsim_type  = "Separator",
    nozzle_tags = ["Feed-Inlet", "Gas-Outlet", "Liquid-Outlet", "Drain"],
    description = "V-501 Gas Liquid Separator: splits CO2 gas from liquid product"
)

# ── TANK-1 (Outlet 1 gas / overhead tank) ─────────────────────────────────────
add_equipment(root,
    eq_id       = "TANK-1",
    tag         = "TANK-1",
    dwsim_type  = "Tank",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "TANK-1: receives Outlet 1 overhead stream (stream 13)"
)

# ── Gas Collection Tank ────────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "Gas-Collection-Tank",
    tag         = "Gas Collection Tank",
    dwsim_type  = "Tank",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "Gas Collection Tank: collects CO2 gas from V-501 gas outlet"
)

# ── Product Collection Tank ────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "Product-Collection-Tank",
    tag         = "Product Collection Tank",
    dwsim_type  = "Tank",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "Product Collection Tank: collects liquid product from V-501"
)

# ── Cooling Loop: PUMP-3 ───────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "PUMP-3",
    tag         = "PUMP-3",
    dwsim_type  = "Pump",
    nozzle_tags = ["Inlet", "Outlet", "Energy-Port"],
    description = "Cooling Water Recirculation Pump",
    extra_attrs = {"EnergyStream": "E5", "EnergyDuty_kW": "0.00"}
)

# ── Cooling Loop: VALVE-3 ──────────────────────────────────────────────────────
add_equipment(root,
    eq_id       = "VALVE-3",
    tag         = "VALVE-3",
    dwsim_type  = "Valve",
    nozzle_tags = ["Inlet", "Outlet"],
    description = "Cooling Loop Control Valve (stream 21 -&gt; 22)"
)

# ══════════════════════════════════════════════════════════════════════════════
#  PIPING NETWORK  (all material + energy streams from flowsheet)
# ══════════════════════════════════════════════════════════════════════════════
piping = ET.SubElement(root, f"{{{NS}}}PipingNetworkSystem", attrib={
    "ID"      : "PipingSystem-1",
    "Tag"     : "Main Process Lines",
    "TagName" : "Main Process Lines"
})

def add_stream(parent, stream_id, tag, stream_type,
               description="", extra_attrs=None):
    seg = ET.SubElement(parent, f"{{{NS}}}PipingNetworkSegment", attrib={
        "ID"             : f"Stream-{stream_id}",
        "Tag"            : tag,
        "TagName"        : tag,
        "ComponentClass" : "PipingNetworkSegment",
        "LineType"       : stream_type,
        "Description"    : description,
    })
    gen_attrs = ET.SubElement(seg, f"{{{NS}}}GenericAttributes")
    ET.SubElement(gen_attrs, f"{{{NS}}}GenericAttribute", attrib={
        "Name": "StreamType", "Value": stream_type
    })
    if extra_attrs:
        for k, v in extra_attrs.items():
            ET.SubElement(gen_attrs, f"{{{NS}}}GenericAttribute", attrib={
                "Name": k, "Value": str(v)
            })
    return seg

# ── Material Streams ───────────────────────────────────────────────────────────
material_streams = [
    # (stream_id,              tag,                       description)
    ("Acetic-Acid-Feed",       "Acetic Acid Feed",        "Raw acetic acid feed to PUMP-1"),
    ("18",                     "18",                      "PUMP-1 outlet to VALVE-2"),
    ("19",                     "19",                      "VALVE-2 outlet to MIX-1 (acid side)"),
    ("Sodium-Bicarbonate-Feed","Sodium bicarbonate Feed", "Raw sodium bicarbonate feed to PUMP-2"),
    ("16",                     "16",                      "PUMP-2 outlet to VALVE-1"),
    ("17",                     "17",                      "VALVE-1 outlet to MIX-1 (bicarb side)"),
    ("Feed-Mixture",           "Feed Mixture",            "MIX-1 outlet to Conversion reactor"),
    ("Outlet-1",               "Outlet 1",                "Reactor overhead outlet to TANK-1"),
    ("Outlet-2",               "Outlet 2",                "Reactor liquid outlet to E-401"),
    ("13",                     "13",                      "TANK-1 outlet stream"),
    ("Cooling-Water",          "Cooling Water",           "Cooling water supply to E-401 (from PUMP-3 loop)"),
    ("21",                     "21",                      "PUMP-3 outlet to VALVE-3"),
    ("22",                     "22",                      "VALVE-3 outlet / cooling water return"),
    ("8",                      "8",                       "V-501 separator feed from E-401"),
    ("12",                     "12",                      "V-501 drain / bottom stream"),
    ("Gas-Outlet-Stream",      "Gas Outlet Stream",       "V-501 gas phase outlet to Gas Collection Tank"),
    ("Liquid-Outlet-Stream",   "Liquid Outlet Stream",    "V-501 liquid phase outlet to Product Collection Tank"),
    ("Gas-Collection-Stream",  "Gas Collection Stream",   "Gas Collection Tank outlet"),
    ("Product-Collection-Stream","Product Collection Stream","Product Collection Tank outlet"),
]

for sid, stag, sdesc in material_streams:
    add_stream(piping, sid, stag, "MaterialStream", description=sdesc)

# ── Energy Streams ─────────────────────────────────────────────────────────────
energy_streams = [
    ("E2", "E2", "PUMP-1 energy input (0.00 kW)",         "0.00"),
    ("E3", "E3", "PUMP-2 energy input (0.00 kW)",         "0.00"),
    ("E4", "E4", "Conversion reactor energy (-0.02 kW)",  "-0.02"),
    ("E5", "E5", "PUMP-3 energy input (0.00 kW)",         "0.00"),
]

for sid, stag, sdesc, duty in energy_streams:
    add_stream(piping, sid, stag, "EnergyStream",
               description=sdesc,
               extra_attrs={"EnergyDuty_kW": duty})

# ══════════════════════════════════════════════════════════════════════════════
#  CONNECTIONS  (From -&gt; To, matching flowsheet topology)
# ══════════════════════════════════════════════════════════════════════════════
connections = [
    # Acetic Acid path
    ("Conn-01",  "Acetic-Acid-Feed",          "PUMP-1"),
    ("Conn-02",  "PUMP-1",                    "18"),
    ("Conn-03",  "18",                        "VALVE-2"),
    ("Conn-04",  "VALVE-2",                   "19"),
    ("Conn-05",  "19",                        "MIX-1"),
    ("Conn-E2",  "E2",                        "PUMP-1"),

    # Sodium Bicarbonate path
    ("Conn-06",  "Sodium-Bicarbonate-Feed",   "PUMP-2"),
    ("Conn-07",  "PUMP-2",                    "16"),
    ("Conn-08",  "16",                        "VALVE-1"),
    ("Conn-09",  "VALVE-1",                   "17"),
    ("Conn-10",  "17",                        "MIX-1"),
    ("Conn-E3",  "E3",                        "PUMP-2"),

    # Mixer -&gt; Reactor
    ("Conn-11",  "MIX-1",                     "Feed-Mixture"),
    ("Conn-12",  "Feed-Mixture",              "Conversion-Reactor"),

    # Reactor outlets
    ("Conn-13",  "Conversion-Reactor",        "Outlet-1"),
    ("Conn-14",  "Conversion-Reactor",        "Outlet-2"),
    ("Conn-E4",  "Conversion-Reactor",        "E4"),

    # Outlet 1 -&gt; TANK-1
    ("Conn-15",  "Outlet-1",                  "TANK-1"),
    ("Conn-16",  "TANK-1",                    "13"),

    # Outlet 2 -&gt; E-401 -&gt; V-501
    ("Conn-17",  "Outlet-2",                  "E-401"),
    ("Conn-18",  "E-401",                     "8"),
    ("Conn-19",  "8",                         "V-501"),

    # Cooling loop -&gt; E-401
    ("Conn-20",  "Cooling-Water",             "E-401"),
    ("Conn-21",  "E-401",                     "PUMP-3"),
    ("Conn-22",  "PUMP-3",                    "21"),
    ("Conn-23",  "21",                        "VALVE-3"),
    ("Conn-24",  "VALVE-3",                   "22"),
    ("Conn-E5",  "E5",                        "PUMP-3"),

    # V-501 outlets
    ("Conn-25",  "V-501",                     "Gas-Outlet-Stream"),
    ("Conn-26",  "V-501",                     "Liquid-Outlet-Stream"),
    ("Conn-27",  "V-501",                     "12"),

    # Gas path
    ("Conn-28",  "Gas-Outlet-Stream",         "Gas-Collection-Tank"),
    ("Conn-29",  "Gas-Collection-Tank",       "Gas-Collection-Stream"),

    # Liquid product path
    ("Conn-30",  "Liquid-Outlet-Stream",      "Product-Collection-Tank"),
    ("Conn-31",  "Product-Collection-Tank",   "Product-Collection-Stream"),
]

for conn_id, from_id, to_id in connections:
    ET.SubElement(root, f"{{{NS}}}Connection", attrib={
        "ID"  : conn_id,
        "From": from_id,
        "To"  : to_id
    })

# ══════════════════════════════════════════════════════════════════════════════
#  SAVE XML
# ══════════════════════════════════════════════════════════════════════════════
print("--- SAVING DEXPI XML ---")

xml_str   = ET.tostring(root, encoding="unicode", xml_declaration=False)
pretty    = minidom.parseString(xml_str).toprettyxml(indent="  ")
lines     = [l for l in pretty.splitlines() if l.strip()]
final_xml = "\n".join(lines)

output_path = os.path.join(OUT_DIR, "BatchReactor_DEXPI_Export_v2.xml")

with open(output_path, "w", encoding="utf-8") as f:
    f.write(final_xml)

n_eq  = 12   # PUMP-1/2/3, VALVE-1/2/3, MIX-1, Reactor, E-401, V-501, TANK-1, Gas Tank, Product Tank
n_str = len(material_streams) + len(energy_streams)
n_con = len(connections)

print(f"\n[SUCCESS] DEXPI XML saved to:\n          {output_path}")
print(f"\n[STATS]")
print(f"  Equipment items  : {n_eq}")
print(f"    - Pumps        : 3  (PUMP-1, PUMP-2, PUMP-3)")
print(f"    - Valves       : 3  (VALVE-1, VALVE-2, VALVE-3)")
print(f"    - Mixer        : 1  (MIX-1)")
print(f"    - Reactor      : 1  (Conversion reactor)")
print(f"    - Heat Exch.   : 1  (E-401)")
print(f"    - Separator    : 1  (V-501 Gas-Liquid Separator)")
print(f"    - Tanks        : 3  (TANK-1, Gas Collection Tank, Product Collection Tank)")
print(f"  Material Streams : {len(material_streams)}")
print(f"  Energy Streams   : {len(energy_streams)}")
print(f"  Total Streams    : {n_str}")
print(f"  Connections      : {n_con}")
print(f"\n  Ready to upload to HAZOP Copilot!")
print(f"  File size        : {os.path.getsize(output_path):,} bytes")