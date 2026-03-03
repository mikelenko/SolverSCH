from solver_sch.model.circuit import Circuit, Resistor, Capacitor, VoltageSource, ACVoltageSource, OpAmp
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.verifier import LTspiceVerifier
from solver_sch.utils.altium_exporter import AltiumScriptExporter
from solver_sch.utils.kicad_exporter import SkidlExporter
import numpy as np
import os

def design_and_verify():
    print("=== Manual OpAmp Filter Design & Verification ===")
    
    # 1. Topology & Calculations
    # Gain = 4 (Non-inverting: 1 + Rf/Rin = 4 => Rf/Rin = 3. Let Rin=1k, Rf=3k)
    # Filter Cutoff = 150Hz (RC Filter: fc = 1 / (2 * pi * R * C))
    # Let R = 10k, then C = 1 / (2 * pi * 10k * 150) approx 106nF
    
    # Power & Input
    ckt = Circuit("OpAmp_LPF_Gain4", ground_name="0")
    ckt.add_component(VoltageSource("VCC", "vcc", "0", 15.0))
    ckt.add_component(VoltageSource("VEE", "vee", "0", -15.0))
    # AC Source for frequency response, DC=1V for gain check
    # 1. Component Values for Non-Inverting Active LPF (Gain = +4, Fc = 150Hz)
    # Gain = 1 + Rf / Rin => Gain = 1 + 30k / 10k = 4
    # Fc = 1 / (2 * pi * Rfilter * Cfilter) => Cfilter = 1 / (2 * pi * 10k * 150) approx 106nF
    r_filter = 10000.0
    c_filter = 106.1e-9 # 106.1 nF
    r_in = 10000.0
    r_f = 30000.0
    
    # 2. Build Circuit
    ckt = Circuit("Active_NonInverting_Filter_150Hz")
    
    # Nodes: 
    # '0' (GND)
    # 'in' (Input)
    # 'filt_node' (Passive filter output / OpAmp Non-Inverting Input)
    # 'gain_node' (OpAmp Inverting Input / Feedback Node)
    # 'out' (Output)
    
    # Vin: Amplitude 1V, Freq 1kHz, DC Offset 1.0V (Expect +4.0V DC at output)
    ckt.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000.0, dc_offset=1.0))
    
    # Passive RC filter stage (at input to ensure high impedance/low noise filtered)
    ckt.add_component(Resistor("Rfilt", "in", "filt_node", r_filter))
    ckt.add_component(Capacitor("Cfilt", "filt_node", "0", c_filter))
    
    # Gain stage (Non-inverting configuration)
    ckt.add_component(Resistor("Rin", "gain_node", "0", r_in))
    ckt.add_component(Resistor("Rf", "gain_node", "out", r_f))
    
    # OpAmp: in_p to filtered node, in_n to feedback node, out to output
    ckt.add_component(OpAmp("U1", in_p="filt_node", in_n="gain_node", out="out", gain=1e5))
    
    print(f"Topology: Non-Inverting Active Filter (Buffer + Filter)")
    print(f"Target: Gain = +4 ({20*np.log10(4):.2f} dB), Fc = 150 Hz")

    # 3. Solver and Analysis
    stamper = MNAStamper(ckt)
    stamper.stamp_linear()
    solver = SparseSolver(stamper.A_lil, stamper.z_vec, stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n)
    
    res_dc = solver.solve()
    v_amp = res_dc.node_voltages.get('amp_out', 0.0)
    v_out_dc = res_dc.node_voltages.get('out', 0.0)
    print(f"DC Input: 1.0V")
    print(f"DC Amp Output: {v_amp:.3f}V (Expect 4.0V)")
    print(f"DC Final Output: {v_out_dc:.3f}V (Expect 4.0V)")
    
    # 3. Native Solver Verification (AC Cutoff)
    print("\n--- SolverSCH Verification (AC) ---")
    freqs, mags, _ = solver.simulate_ac(f_start=10, f_stop=1000, points_per_decade=50, stamper_ref=stamper)
    
    # Find mag at 150Hz
    idx_150 = (np.abs(freqs - 150.0)).argmin()
    mag_150 = mags.get('out', np.zeros(len(freqs)))[idx_150]
    # Passband mag is at 10Hz (approx gain 4 = 12.04 dB)
    mag_pass = mags.get('out', np.zeros(len(freqs)))[0]
    
    print(f"Passband Gain: {mag_pass:.2f} dB")
    print(f"Magnitude at 150Hz: {mag_150:.2f} dB")
    print(f"Relative Attenuation: {mag_150 - mag_pass:.2f} dB (Expect -3dB)")
    
    # 5. Altium Export
    print("\n--- Altium Schematic Export ---")
    AltiumScriptExporter.export(ckt, "generate_filter_sch.pas")

    # 6. KiCad Layout Export
    print("\n--- KiCad Layout Export ---")
    SkidlExporter.export(ckt, "filter_kicad")

if __name__ == "__main__":
    design_and_verify()
