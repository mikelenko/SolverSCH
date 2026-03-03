import os
import sys

# Ensure solver_sch is in PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, VoltageSource, ACVoltageSource, OpAmp
from solver_sch.utils.kicad_exporter import SkidlExporter

def main():
    # 2. CIRCUIT INITIALIZATION
    circuit = Circuit(ground_name="0")

    # 5. POWER SUPPLY
    circuit.add_component(VoltageSource("Vcc", "VCC", "0", 15))
    circuit.add_component(VoltageSource("Vee", "VEE", "0", -15))

    # 3. INSTRUMENTATION AMPLIFIER BUILD
    circuit.add_component(ACVoltageSource("V_in_plus", "in_p", "0", amplitude=1, frequency=1000, dc_offset=0))
    circuit.add_component(ACVoltageSource("V_in_minus", "in_n", "0", amplitude=1, frequency=1000, dc_offset=0))

    # Input buffers
    circuit.add_component(OpAmp("U1", "in_p", "inv1", "out1"))
    circuit.add_component(OpAmp("U2", "in_n", "inv2", "out2"))

    # Gain resistor connecting inverting inputs
    circuit.add_component(Resistor("R_gain", "inv1", "inv2", 1000))

    # Feedback resistors for buffers
    circuit.add_component(Resistor("R1", "out1", "inv1", 10000))
    circuit.add_component(Resistor("R2", "out2", "inv2", 10000))

    # Difference amplifier
    circuit.add_component(OpAmp("U3", "non_inv3", "inv3", "V_mid"))

    # Resistors for difference amplifier
    circuit.add_component(Resistor("R3", "out2", "inv3", 10000))
    circuit.add_component(Resistor("R4", "out1", "non_inv3", 10000))
    
    # Feedback and ground resistors for difference amplifier
    circuit.add_component(Resistor("R5", "V_mid", "inv3", 10000))
    circuit.add_component(Resistor("R6", "non_inv3", "0", 10000))

    # 4. SALLEN-KEY FILTER BUILD (Low-Pass Filter)
    circuit.add_component(Resistor("R7", "V_mid", "mid_sk", 10000))
    circuit.add_component(Resistor("R8", "mid_sk", "in_p_u4", 10000))
    
    circuit.add_component(Capacitor("C1", "mid_sk", "V_out", 10e-9))
    circuit.add_component(Capacitor("C2", "in_p_u4", "0", 10e-9))
    
    # Unity gain buffer for the filter
    circuit.add_component(OpAmp("U4", "in_p_u4", "V_out", "V_out"))

    # 6. KICAD EXPORT
    output_dir = "kicad_export/SignalConditioner"
    
    # Ensure export directory exists relative to project root
    # Since we are executing from the root, paths should be resolved appropriately
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_path = os.path.join(proj_root, output_dir)
    
    print(f"Exporting KiCad project to: {export_path}")
    
    SkidlExporter.export(circuit, export_path)
    
    # 7. SOLVERSCH AC ANALYSIS
    print("Running AC Analysis in SolverSCH...")
    
    stamper = MNAStamper(circuit)
    stamper.stamp_linear()
    
    solver = SparseSolver(
        A_matrix=stamper.A_lil,
        z_vector=stamper.z_vec,
        node_to_idx=stamper.node_to_idx,
        vsrc_to_idx=stamper.vsrc_to_idx,
        n_independent_nodes=stamper.n
    )
    
    # Sweep from 10Hz to 1Mhz
    freqs, mags_db, phases_deg = solver.simulate_ac(f_start=10.0, f_stop=1000000.0, points_per_decade=50, stamper_ref=stamper)
    
    # 9. LTSPICE AC VERIFICATION
    print("Running AC Analysis in LTspice for Verification...")
    from solver_sch.utils.verifier import LTspiceVerifier
    verifier = LTspiceVerifier()
    
    try:
        raw_file = verifier.verify(circuit, ".ac dec 50 10 1Meg")
        data = verifier.parse_raw(raw_file)
        
        # We can extract arrays from PyLTSpice RawRead
        lt_freqs = data.get_trace("frequency").get_wave()
        # The LTspice trace V(node) is complex in AC analysis: magnitude = 20*log10(abs(V))
        import numpy as np
        
        lt_vmid_complex = data.get_trace("V(V_mid)").get_wave()
        lt_vout_complex = data.get_trace("V(V_out)").get_wave()
        
        lt_vmid_mag = 20 * np.log10(np.abs(lt_vmid_complex))
        lt_vout_mag = 20 * np.log10(np.abs(lt_vout_complex))
        
        lt_vmid_phase = np.angle(lt_vmid_complex, deg=True)
        lt_vout_phase = np.angle(lt_vout_complex, deg=True)
        
        print("LTspice Verification successful.")
    except Exception as e:
        print(f"LTspice Verification failed: {e}")

    print("Design complete.")

if __name__ == "__main__":
    main()
