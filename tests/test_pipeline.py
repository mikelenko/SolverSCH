"""
test_pipeline.py -> Complete Integration Test from Model to Solver.
"""

import unittest
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver, MNAResult


class TestMNAPipeline(unittest.TestCase):
    
    def test_voltage_divider_pipeline(self):
        """
        Validates the complete 3-layer architecture:
        Model -> Builder (Stamping) -> Solver (Math execution)
        """
        # 1. Model Layer
        ckt = Circuit("Voltage Divider Subtest", ground_name="0")
        ckt.add_component(VoltageSource("V1", "1", "0", 5.0))
        ckt.add_component(Resistor("R1", "1", "2", 10.0))
        ckt.add_component(Resistor("R2", "2", "0", 10.0))
        
        self.assertEqual(len(ckt.get_components()), 3)
        self.assertEqual(ckt.get_unique_nodes(), {"0", "1", "2"})
        
        # 2. Builder Layer (Stamper)
        stamper = MNAStamper(ckt)
        A_lil, z_vec = stamper.stamp_linear()
        
        # Expect n=2 independent nodes ('1', '2'), m=1 voltage source.
        # Matrix size should be 3x3
        self.assertEqual(A_lil.shape, (3, 3))
        self.assertEqual(z_vec.shape, (3, 1))
        
        # 3. Solver Layer
        solver = SparseSolver(
            A_matrix=A_lil,
            z_vector=z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        result: MNAResult = solver.solve()
        
        # Evaluate Mathematical accuracy
        voltages = result.node_voltages
        currents = result.voltage_source_currents
        
        # Tolerance config
        places = 5
        
        self.assertAlmostEqual(voltages["0"], 0.0, places=places, msg="Ground must be exactly 0V")
        self.assertAlmostEqual(voltages["1"], 5.0, places=places, msg="Node 1 tied to 5V source should be 5V")
        self.assertAlmostEqual(voltages["2"], 2.5, places=places, msg="Divider middle node should be 2.5V")
        
        # Current assertion (Source drives 5V across 20 Ohms total = 0.25A)
        # By MNA active sign convention, V1 delivers -0.25A.
        self.assertAlmostEqual(currents["V1"], -0.25, places=places, msg="Proper loop current drawn")

if __name__ == "__main__":
    unittest.main()
