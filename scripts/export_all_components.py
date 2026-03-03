import os
import sys
import csv
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, Inductor, ACVoltageSource, OpAmp
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.kicad_exporter import SkidlExporter
import numpy as np


def export_ac_to_csv(results, csv_path):
    """Export full AC analysis results to a CSV file ready for Excel.
    
    Columns: Frequency [Hz], and for each node:
        V_mag (linear magnitude), V_dB (20*log10), Phase [deg]
    """
    if not results:
        return
    
    # Collect node names from the first result (skip ground '0')
    _, first_mna = results[0]
    node_names = sorted([n for n in first_mna.node_voltages.keys() if n != '0'])
    
    # Build header
    header = ["Frequency [Hz]"]
    for node in node_names:
        header.extend([f"|V({node})| [V]", f"V({node}) [dB]", f"Phase({node}) [deg]"])
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')  # semicolon for European Excel
        writer.writerow(header)
        
        for freq, mna_res in results:
            row = [f"{freq:.4f}"]
            for node in node_names:
                v_complex = mna_res.node_voltages.get(node, 0)
                mag = abs(v_complex)
                db = 20 * np.log10(max(mag, 1e-20))
                phase = np.degrees(np.angle(v_complex))
                row.extend([f"{mag:.6f}", f"{db:.2f}", f"{phase:.2f}"])
            writer.writerow(row)
    
    print(f"[CSV EXPORT] AC results saved to {csv_path}")


def main():
    circuit = Circuit("Demo RLC OpAmp", ground_name="0")

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
    
    print(f"Exporting KiCad project to: {export_path}")
    
    SkidlExporter.export(circuit, export_path)
    
    print("Demo components KiCad generation complete.\n")

    # Run SolverSCH AC Analysis
    print("--- Running SolverSCH AC Analysis ---")
    stamper = MNAStamper(circuit)
    A_lil, z_vec = stamper.stamp_linear()
    
    solver = SparseSolver(A_lil, z_vec, stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n)
    
    # Sweep from 100 Hz to 100 kHz, 10 points per decade
    freqs = np.logspace(2, 5, 40)
    results = solver.simulate_ac(f_start=freqs.tolist(), stamper_ref=stamper)
    
    # Print a few key frequencies to show filtering action
    test_freqs = [100, 1000, 5000, 10000, 50000]
    
    print(f"{'Freq [Hz]':>10} | {'V(in)':>10} | {'V(node_l)':>10} | {'V(node_c)':>10} | {'V(out)':>10}")
    print("-" * 65)
    
    for f_target in test_freqs:
        idx = (np.abs(freqs - f_target)).argmin()
        f_actual, mna_res = results[idx]
        
        v_in = abs(mna_res.node_voltages.get('in', 0))
        v_l = abs(mna_res.node_voltages.get('node_l', 0))
        v_c = abs(mna_res.node_voltages.get('node_c', 0))
        v_out = abs(mna_res.node_voltages.get('out', 0))
        
        print(f"{f_actual:10.0f} | {v_in:10.3f} | {v_l:10.3f} | {v_c:10.3f} | {v_out:10.3f}")

    # Export full results to CSV for Excel
    csv_path = os.path.join(export_path, "AC_Analysis.csv")
    export_ac_to_csv(results, csv_path)
    
    # Auto-open in Excel
    try:
        os.startfile(csv_path)
        print(f"[CSV EXPORT] Opening {csv_path} in Excel...")
    except Exception:
        print(f"[CSV EXPORT] Open manually: {csv_path}")

if __name__ == "__main__":
    main()

