"""
test_diode.py -> Unit Test for Non-linear Newton-Raphson convergence.
"""

import unittest
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, Diode
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver


class TestDiodeNR(unittest.TestCase):
    
    def test_diode_convergence(self):
        """
        Validates the Newton-Raphson loop resolving a non-linear Diode circuit.
        Circuit: 5V source -> 1k Ohm Resistor -> Diode -> Ground.
        Expected: Stable convergence, Diode voltage drops purely to ~0.7V.
        """
        # 1. Model Layer
        ckt = Circuit("Diode Clipper Subtest", ground_name="0")
        ckt.add_component(VoltageSource("V1", "1", "0", 5.0))
        ckt.add_component(Resistor("R1", "1", "2", 1000.0))
        ckt.add_component(Diode("D1", "2", "0"))
        
        # 2. Builder Layer (Stamper Linear Base)
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
        
        # Inject dynamic NR equations for Diode companions
        solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
        
        result = solver.solve()
        
        voltages = result.node_voltages
        currents = result.voltage_source_currents
        
        # Source must be 5V securely
        self.assertAlmostEqual(voltages["1"], 5.0, places=5)
        
        # Verify the mathematically damped NR Loop successfully converged on the Diode forward curve
        diode_v = voltages["2"]
        self.assertTrue(
            0.6 <= diode_v <= 0.8, 
            f"Diode Voltage didn't drop across realistic PN boundaries! Got: {diode_v}V"
        )

if __name__ == "__main__":
    unittest.main()
