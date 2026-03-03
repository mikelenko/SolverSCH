import unittest

from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, Diode
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestZenerDiode(unittest.TestCase):
    
    def test_zener_breakdown(self):
        """
        Tests Zener Breakdown Clamping mechanism.
        V_source = 10V
        R_limit = 1k
        Diode with Vz = 5.1V (Reverse biased)
        
        Expect the voltage across the diode to be clamped at ~ -5.1V
        """
        ckt = Circuit("Zener Regulator", ground_name="0")
        
        # 10V Source
        ckt.add_component(VoltageSource("V1", "in", "0", 10.0))
        
        # 1k Limiting Resistor
        ckt.add_component(Resistor("R1", "in", "out", 1000.0))
        
        # Diode: Anode connected to Ground ("0"), Cathode to "out" -> Reverse Biased!
        # Threshold: 5.1V
        ckt.add_component(Diode("D1", anode="0", cathode="out", Vz=5.1))
        
        stamper = MNAStamper(ckt)
        A_lil, z_vec = stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=A_lil,
            z_vector=z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
        
        result = solver.solve()
        vout = result.node_voltages.get("out", 0.0)
        
        print(f"\n[Zener] Reverse Biased 10V -> V_cathode={vout:.3f}V (Expected ~5.1V)")
        
        # Validations: Voltage at "out" node must be strictly clamped by the zener drop
        self.assertAlmostEqual(vout, 5.1, places=1, msg="Zener failed to collapse and regulate voltage.")

if __name__ == "__main__":
    unittest.main()
