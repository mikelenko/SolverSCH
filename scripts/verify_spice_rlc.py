import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, Inductor, ACVoltageSource, OpAmp
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

def generate_spice_netlist(filepath):
    """Generates a raw SPICE .cir file for LTspice / Ngspice."""
    spice_content = """* SolverSCH Validation - RLC Filter + OpAmp Buffer
V1 in 0 AC 1.0
R1 in node_l 100
L1 node_l node_c 1mH
C1 node_c 0 1uF
* Ideal OpAmp modeled as a Voltage Controlled Voltage Source (VCVS) with high gain
E1 out 0 node_c 0 1E6

.ac dec 10 100 100k
.probe
.end
"""
    with open(filepath, 'w') as f:
        f.write(spice_content)
    print(f"\n[SPICE] Generated LTspice/Ngspice compatible netlist: {filepath}")
    print("[SPICE] You can open this file directly in LTspice to run the exact same simulation!")

def verify_analytical():
    print("--- SolverSCH vs Analytical Mathematical Proof ---")
    
    # 1. Build circuit in SolverSCH
    circuit = Circuit("Demo", ground_name="0")
    # amplitude is for Time-Domain, ac_mag=1.0 is the actual AC Sweep magnitude
    circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=5.0, frequency=1000, ac_mag=1.0))
    circuit.add_component(Resistor("R1", "in", "node_l", 100))
    circuit.add_component(Inductor("L1", "node_l", "node_c", 1e-3))
    circuit.add_component(Capacitor("C1", "node_c", "0", 1e-6))
    circuit.add_component(OpAmp("U1", "node_c", "out", "out"))

    # 2. Run SolverSCH
    stamper = MNAStamper(circuit)
    A_lil, z_vec = stamper.stamp_linear()
    solver = SparseSolver(A_lil, z_vec, stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n)
    
    freqs = np.logspace(2, 5, 40)
    results = solver.simulate_ac(f_start=freqs.tolist(), stamper_ref=stamper)
    
    # 3. Analytical Math
    # H(s) = 1 / (s^2 * LC + s * RC + 1)
    # V_out = Vin * H(s)
    R = 100.0
    L = 1e-3
    C = 1e-6
    Vin = 1.0  # Solver uses ac_mag=1.0 by default
    
    print(f"{'Freq [Hz]':>10} | {'Solver Vc [V]':>15} | {'Exact Math Vc [V]':>18} | {'Error [%]':>10}")
    print("-" * 65)
    
    max_error = 0.0
    for idx, (f_actual, mna_res) in enumerate(results):
        # Solver result
        v_c_solver = abs(mna_res.node_voltages.get('node_c', 0))
        
        # Exact Math
        s = 1j * 2 * np.pi * f_actual
        H_s = 1.0 / (s**2 * L * C + s * R * C + 1.0)
        v_c_exact = abs(Vin * H_s)
        
        # Diff
        error_pct = abs(v_c_solver - v_c_exact) / (v_c_exact + 1e-12) * 100
        if error_pct > max_error:
            max_error = error_pct
            
        if idx % 5 == 0:
            print(f"{f_actual:10.0f} | {v_c_solver:15.6f} | {v_c_exact:18.6f} | {error_pct:10.6f}%")

    print("-" * 65)
    print(f"MAXIMUM ERROR between Sparse Matrices (SolverSCH) and Pure Math: {max_error:.2e} %")
    if max_error < 1e-5:
        print("[PASS] SolverSCH matrices perfectly match the physical differential equations!")
    else:
        print("[FAIL] Significant divergence detected.")

if __name__ == "__main__":
    generate_spice_netlist("kicad_export/AllComponents/rlc_filter_test.cir")
    verify_analytical()
