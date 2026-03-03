"""
test_rectifier.py -> Integration Test for Half-Wave Rectifier Simulation.
"""

import unittest
import csv
from solver_sch.model.circuit import Circuit, Resistor, Diode, ACVoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver


class TestHalfWaveRectifier(unittest.TestCase):
    
    def test_rectifier_output(self):
        """
        Validates nested integration of AC sources, Non-Linear backward mapping and outputs a CSV.
        Circuit: AC 50Hz 5V Amplitude -> Diode -> 1k Ohm Resistor -> Ground
        """
        # 1. Model Layer
        ckt = Circuit("Half-Wave Rectifier", ground_name="0")
        
        # AC Source: 5.0V amplitude, 50Hz frequency
        ckt.add_component(ACVoltageSource("V1", "1", "0", 5.0, 50.0))
        
        # Non-Linear Junction
        ckt.add_component(Diode("D1", "1", "2"))
        
        # Output Load
        ckt.add_component(Resistor("R1", "2", "0", 1000.0))
        
        # 2. Builder Layer
        stamper = MNAStamper(ckt)
        A_lil, z_vec = stamper.stamp_linear()
        
        # 3. Solver Layer
        solver = SparseSolver(
            A_matrix=A_lil,
            z_vector=z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        # Inject callbacks        # Transient and Nonlinear mappings
        solver.set_transient_stampers(
            basis_cb=stamper.stamp_transient_basis,
            sources_cb=stamper.stamp_transient_sources,
            update_states_cb=stamper.update_states
        )
        solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
        
        # Two full standard periods (50Hz -> T = 0.02s -> t_stop = 0.04s)
        dt = 0.0001
        t_stop = 0.04
        results = solver.simulate_transient(t_stop, dt)
        
        # 4. Data Export logic (No rigid assert, CSV generation for external plotter validation)
        # Expected Header: 'time, v_in, v_out'
        
        csv_filename = 'rectifier_output.csv'
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['time', 'v_in', 'v_out'])
            
            for t, res in results:
                v_in = res.node_voltages.get("1", 0.0)
                v_out = res.node_voltages.get("2", 0.0)
                writer.writerow([f"{t:.6f}", f"{v_in:.6f}", f"{v_out:.6f}"])


if __name__ == "__main__":
    unittest.main()
