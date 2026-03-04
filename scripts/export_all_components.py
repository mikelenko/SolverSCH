import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, Inductor, ACVoltageSource, OpAmp
from solver_sch.utils.kicad_exporter import SkidlExporter
from solver_sch.utils.excel_report import ExcelReportGenerator


def main():
    circuit = Circuit("Demo RLC OpAmp Filter", ground_name="0")

    # Voltage / Signal Flow
    circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=5.0, frequency=1000, dc_offset=0))
    
    # RLC Tank
    circuit.add_component(Resistor("R1", "in", "node_l", 100))
    circuit.add_component(Inductor("L1", "node_l", "node_c", 1e-3)) # 1mH
    circuit.add_component(Capacitor("C1", "node_c", "0", 1e-6))     # 1uF
    
    # Active element
    circuit.add_component(OpAmp("U1", "node_c", "out", "out"))      # Buffer

    output_dir = "kicad_export/AllComponents"
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_path = os.path.join(proj_root, output_dir)
    
    # 1. KiCad Export (SKiDL netlist + SVG)
    print(f"Exporting KiCad project to: {export_path}")
    SkidlExporter.export(circuit, export_path)
    print("KiCad export complete.\n")

    # 2. Excel Analysis Report (Selectable analyses)
    report = ExcelReportGenerator(circuit)
    report.generate(
        os.path.join(export_path, "Circuit_Report.xlsx"),
        analyses=["summary", "dc", "ac", "transient", "bom"],
        ac_params={"f_start": 100, "f_stop": 100e3, "ppd": 10},
        transient_params={"t_stop": 5e-3, "dt": 10e-6},
        auto_open=True,
    )

if __name__ == "__main__":
    main()
