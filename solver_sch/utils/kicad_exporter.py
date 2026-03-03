import os
import sys
import json
from skidl import Part, Net, Circuit as SKiDLCircuit

from solver_sch.model.circuit import (
    Circuit, Resistor, Capacitor, Inductor, VoltageSource, ACVoltageSource,
    Diode, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator
)

class SkidlExporter:
    """
    Generates KiCad netlists using SKiDL as a Hardware-as-Code compiler.
    Replaces manual schematic layout with standard EDA netlist generation.
    """

    @staticmethod
    def export(circuit: Circuit, output_dir: str):
        """Translates SolverSCH Circuit to KiCad NET file via SKiDL."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 1. Netlist Construction with SKiDL
        skidl_ckt = SKiDLCircuit()
        
        # Configure KiCad paths for SKiDL so it can find symbols for generate_svg rendering
        kicad_base = r"C:\Users\micha\AppData\Local\Programs\KiCad\9.0"
        if os.path.exists(kicad_base):
            sym_dir = os.path.join(kicad_base, "share", "kicad", "symbols")
            os.environ["KICAD_SYMBOL_DIR"] = sym_dir
            from skidl import lib_search_paths, KICAD
            if sym_dir not in lib_search_paths[KICAD]:
                lib_search_paths[KICAD].append(sym_dir)
              
        # Local cache for skidl parts and nets
        sk_parts = {}
        sk_nets = {}

        # Create Nets
        for node in circuit.get_unique_nodes():
            net_name = "GND" if node == "0" else node
            sk_nets[node] = Net(net_name, circuit=skidl_ckt)

        # Create Parts and connect them
        for comp in circuit.get_components():
            part = SkidlExporter._create_skidl_part(comp, skidl_ckt)
            if part:
                sk_parts[comp.name] = part
                SkidlExporter._connect_part(comp, part, sk_nets)

        # 2. Asset Generation
        basename = os.path.basename(output_dir)
        net_file = os.path.join(output_dir, f"{basename}.net")

        try:
            skidl_ckt.generate_netlist(file_=net_file)
            print(f"[SKIDL EXPORT] Netlist successfully saved to {net_file}")
            
            # Optional: Generate graphical schematic using NetlistSVG
            # SKiDL's generate_svg actually writes a .json file and runs netlistsvg for us!
            svg_base = os.path.join(output_dir, basename)
            skidl_ckt.generate_svg(file_=svg_base)
            print(f"[SKIDL EXPORT] Schematic SVG saved to {svg_base}.svg")
            
        except Exception as e:
            print(f"[SKIDL EXPORT] Error during KiCad asset generation: {e}")

    @staticmethod
    def _create_skidl_part(comp, circuit) -> Part:
        """Maps SolverSCH components to KiCad library parts via SKiDL."""
        try:
            if isinstance(comp, Resistor):
                p = Part('Device', 'R_Small', footprint='Resistor_SMD:R_0805_2012Metric', circuit=circuit)
                p.value = str(comp.value)
                p.ref = comp.name
                return p
            elif isinstance(comp, Capacitor):
                p = Part('Device', 'C_Small', footprint='Capacitor_SMD:C_0805_2012Metric', circuit=circuit)
                p.value = str(comp.value)
                p.ref = comp.name
                return p
            elif isinstance(comp, Inductor):
                p = Part('Device', 'L_Small', footprint='Inductor_SMD:L_0805_2012Metric', circuit=circuit)
                p.value = str(comp.value)
                p.ref = comp.name
                return p
            elif isinstance(comp, OpAmp):
                p = Part('Amplifier_Operational', 'LM358', footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', circuit=circuit)
                p.ref = comp.name
                return p
            elif isinstance(comp, (VoltageSource, ACVoltageSource)):
                p = Part('Connector', 'Conn_01x02_Male', footprint='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical', circuit=circuit)
                p.ref = comp.name
                return p
        except Exception as e:
            # If KiCad libraries aren't in path, SKiDL might fail to instantiate Part.
            # Catching it gracefully so we don't crash the whole pipeline if one part fails.
            pass
        return None

    @staticmethod
    def _connect_part(comp, sk_part, sk_nets):
        """Connects skidl part pins to nets based on circuit nodes."""
        try:
            if isinstance(comp, (Resistor, Capacitor, Inductor)):
                sk_part[1] += sk_nets[comp.node1]
                sk_part[2] += sk_nets[comp.node2]
            elif isinstance(comp, (VoltageSource, ACVoltageSource)):
                sk_part[1] += sk_nets[comp.node1]
                sk_part[2] += sk_nets[comp.node2]
            elif isinstance(comp, OpAmp):
                # Mapping for standard SOIC-8 OpAmp (LM358 style)
                # Pin 3: +, Pin 2: -, Pin 1: Out
                sk_part[3] += sk_nets[comp.in_p]
                sk_part[2] += sk_nets[comp.in_n]
                sk_part[1] += sk_nets[comp.out]
        except Exception as e:
            pass
