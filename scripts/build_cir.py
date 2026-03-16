"""Build StepDownDCDC_LM5085.cir from Schematic_Netlist.json + NET file."""
import json
from solver_sch.parser.altium_parser import AltiumParser
from solver_sch.utils.exporter import LTspiceExporter

# 1. Load exact sheet components from JSON
with open('Schematic_Netlist.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sheet = data['Sheets']['StepDownDCDC_LM5085.SchDoc']
# Get designators (skip pure-numeric test points)
designators = {des: info['Comment'] for des, info in sheet.items()
               if not des.isdigit()}
print(f"Komponenty z JSON (sheet 16): {sorted(designators.keys())}")
print(f"Liczba: {len(designators)}")

# 2. Parse full NET file
proj = AltiumParser.parse_netlist_file('StepDownDCDC_LM5085.NET')

# 3. Filter to exact sheet-16 designators
filtered = AltiumParser.filter_by_designators(proj, set(designators.keys()))

# 4. Override comments — prefer BOM xlsx Description (human-readable values like "68µH", "10 mOhms")
#    Fall back to JSON Comment only when BOM has no parseable value
bom_descs = AltiumParser.parse_bom_xlsx('058-SBS-06.xlsx')  # all sheets, Description column

for des in list(filtered.components.keys()):
    comp = filtered.components[des]
    json_comment = designators.get(des, comp.comment)
    bom_desc = bom_descs.get(des, '')

    # For ICs (U-prefix): always keep JSON comment (part number like "LM5085SD/NOPB")
    # so is_analog_component can identify them by name. BOM desc wins for passives only.
    if comp.prefix == 'U':
        comp.comment = json_comment
    elif bom_desc and AltiumParser.extract_value(bom_desc) is not None:
        comp.comment = bom_desc
    else:
        comp.comment = json_comment

# 5. Convert to Circuit
circuit = AltiumParser.convert_to_circuit(filtered, circuit_name="StepDownDCDC_LM5085")

comps = circuit.get_components()
print(f"\nAnalogowych komponentów w .cir: {len(comps)}")
for c in comps:
    print(f"  {c.name}")

# 6. Export — U6 (LM5085Gate) is now a real component, exported as B-source
LTspiceExporter.export(circuit, 'StepDownDCDC_LM5085.cir', analysis='op')
print("\n[OK] Wygenerowano StepDownDCDC_LM5085.cir")
