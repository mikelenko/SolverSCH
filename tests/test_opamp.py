import unittest

from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, OpAmp
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestOpAmp(unittest.TestCase):
    
    def test_inverting_amplifier(self):
        """
        Tests an Inverting Amplifier topology using the ideal VCVS OpAmp model.
        Vin = 1.0V (DC)
        Rin = 1k
        Rf = 10k
        
        Expected Gain (Av) = -Rf/Rin = -10
        Expected Vout = Av * Vin = -10.0V
        Expected Virtual Ground at Inverting Input (n_inv) = 0.0V
        """
        ckt = Circuit("Inverting Amplifier", ground_name="0")
        
        # Stimulus
        ckt.add_component(VoltageSource("Vin", "in", "0", 1.0))
        
        # Feedback Network
        ckt.add_component(Resistor("Rin", "in", "n_inv", 1000.0))
        ckt.add_component(Resistor("Rf", "n_inv", "out", 10000.0))
        
        # Operational Amplifier Macromodel
        # Non-inverting input grounded ("0")
        # Inverting input to "n_inv"
        # Output to "out"
        ckt.add_component(OpAmp("U1", in_p="0", in_n="n_inv", out="out"))
        
        stamper = MNAStamper(ckt)
        A_lil, z_vec = stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=A_lil,
            z_vector=z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        result = solver.solve()
        
        vout = result.node_voltages.get("out", 0.0)
        v_inv = result.node_voltages.get("n_inv", 0.0)
        
        print(f"\n[Op-Amp Inverting] Vout = {vout:.3f}V (Expected -10.0V)")
        print(f"[Op-Amp Virtual GND] V_n_inv = {v_inv:.6f}V (Expected ~0.0V)")
        
        self.assertAlmostEqual(vout, -10.0, places=2, msg="Inverting Amplifier failed to reach correct gain voltage.")
        self.assertAlmostEqual(v_inv, 0.0, places=3, msg="OpAmp failed to maintain Virtual Ground.")

if __name__ == "__main__":
    unittest.main()
