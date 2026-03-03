import unittest
import csv
import os

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, Inductor, VoltageSource, ACVoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestRLCTransient(unittest.TestCase):
    
    def test_rlc_series_resonance(self):
        """Test standard series RLC circuit AC behavior with new auxiliary Inductor."""
        import numpy as np
        circuit = Circuit("Series RLC AC Test", ground_name="0")
        
        # 1V AC Source
        circuit.add_component(ACVoltageSource("V1", "1", "0", amplitude=1.0, frequency=1000.0, ac_mag=1.0, ac_phase=0.0))
        # Series RLC
        circuit.add_component(Resistor("R1", "1", "2", 10.0))
        circuit.add_component(Inductor("L1", "2", "3", 1e-3)) # 1mH
        circuit.add_component(Capacitor("C1", "3", "0", 1e-6)) # 1uF
        
        # Theoretical Resonance: f_res = 1 / (2 * pi * sqrt(L * C))
        f_res = 1.0 / (2.0 * np.pi * np.sqrt(1e-3 * 1e-6))
        
        stamper = MNAStamper(circuit)
        # Allocate matrices for mapping checks
        stamper.A_lil = None 
        stamper.z_vec = None
        
        solver = SparseSolver(
            A_matrix=None, 
            z_vector=None,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        solver.set_ac_stamper(stamper.stamp_ac)
        
        # 1. Test exactly at theoretical resonance
        outputs = solver.simulate_ac([f_res])
        res_mna = outputs[0][1]
        
        idx_v1 = solver.vsrc_to_idx["V1"]
        k_v1 = solver.n + idx_v1
        I_v1_phasor = res_mna.x_converged[k_v1]
        
        # I = 0.1A purely real entering node 1 -> I_V1 = -0.1A
        self.assertTrue(np.isclose(I_v1_phasor.real, -0.1, rtol=1e-3))
        self.assertTrue(np.isclose(I_v1_phasor.imag, 0.0, atol=1e-5))
        
        idx_l1 = solver.vsrc_to_idx["L1"]
        k_l1 = solver.n + idx_l1
        I_l1_phasor = res_mna.x_converged[k_l1]
        
        # I = 0.1A through L1 auxiliary branch entering node 2 -> I_L1 = 0.1A
        self.assertTrue(np.isclose(I_l1_phasor.real, 0.1, rtol=1e-3))
        self.assertTrue(np.isclose(I_l1_phasor.imag, 0.0, atol=1e-5))

    def test_underdamped_resonance(self):
        """
        Tests a series RLC circuit excited by a 5V DC step.
        L = 0.05H, C = 10uF, R = 20Ohm
        
        The system is heavily underdamped. We expect the capacitor voltage 
        to overshoot the 5V supply significantly during the transient response.
        """
        # 1. Model
        ckt = Circuit("Underdamped RLC", ground_name="0")
        
        # Step Voltage Source (0 at t<0, 5V at t>=0)
        ckt.add_component(VoltageSource("V1", "1", "0", 5.0))
        ckt.add_component(Resistor("R1", "1", "2", 20.0))
        ckt.add_component(Inductor("L1", "2", "3", 0.05))
        ckt.add_component(Capacitor("C1", "3", "0", 10e-6))
        
        # 2. Builder
        stamper = MNAStamper(ckt)
        A_lil, z_vec = stamper.stamp_linear()
        
        # 3. Solver Setup
        solver = SparseSolver(
            A_matrix=A_lil,
            z_vector=z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        # Inject transient stamping delegates
        solver.set_transient_stampers(
            basis_cb=stamper.stamp_transient_basis,
            sources_cb=stamper.stamp_transient_sources,
            update_states_cb=stamper.update_states
        )
        
        # 4. Execute Simulation
        t_stop = 0.05  # 50 ms
        dt = 1e-4      # 0.1 ms resolution
        results = solver.simulate_transient(t_stop, dt)
        
        output_file = "rlc_output.csv"
        max_v_cap = 0.0
        
        # Export and Analyze
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['time', 'v_cap'])
            
            for t, result in results:
                v_cap = result.node_voltages.get("3", 0.0)
                writer.writerow([t, v_cap])
                if v_cap > max_v_cap:
                    max_v_cap = v_cap
                    
        # 5. Physics Assertion: Overshoot must occur (> 5.0V)
        # Because the damping factor is very small, it should ring up to ~8-9V. 
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(max_v_cap, 5.0, msg=f"System did not resonate! Max voltage was {max_v_cap}V, expected > 5.0V overshoot.")
        
        print(f"\n[RLC Test] Resonant Overshoot Peak: {max_v_cap:.3f}V (Supply = 5.0V)")

if __name__ == "__main__":
    unittest.main()
