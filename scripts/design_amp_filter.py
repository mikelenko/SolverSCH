from solver_sch.model.circuit import Circuit, Resistor, Capacitor, VoltageSource, ACVoltageSource, OpAmp
from solver_sch.utils.verifier import LTspiceVerifier
from solver_sch.utils.kicad_exporter import SkidlExporter
import os

def main():
    circuit = Circuit(ground_name="0")

    # Power supplies for OpAmp
    circuit.add_component(VoltageSource("Vcc", "VCC", "0", 15))
    circuit.add_component(VoltageSource("Vee", "VEE", "0", -15))

    # OpAmp
    circuit.add_component(OpAmp("U1", "in", "fb", "out_amp", "VCC", "VEE"))

    # Non-inverting amplifier feedback network (Gain = 1 + Rf/Rg = 1 + 10k/1k = 11)
    circuit.add_component(Resistor("Rf", "out_amp", "fb", 10000))
    circuit.add_component(Resistor("Rg", "fb", "0", 1000))

    # Input signal to non-inverting input
    circuit.add_component(ACVoltageSource("Vin", "in", "0", dc_offset=0, amplitude=1))

    # Low-pass filter at the output (fc ~ 1kHz)
    circuit.add_component(Resistor("Rlp", "out_amp", "out_lp", 1600))
    circuit.add_component(Capacitor("Clp", "out_lp", "0", 100e-9))

    # Export to KiCad
    project_dir = "amp_filter_kicad"
    SkidlExporter.export(circuit, project_dir)

    # Simulate
    verifier = LTspiceVerifier()
    
    # AC Analysis to see the frequency response of the filter and gain
    raw_file = verifier.verify(circuit, "ac dec 50 10 100k")
    
    data = verifier.parse_raw(raw_file)
    
    print(f"Design complete. KiCad files generated in '{project_dir}' directory.")

if __name__ == "__main__":
    main()
