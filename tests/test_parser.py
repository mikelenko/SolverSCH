import unittest

from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestNetlistParser(unittest.TestCase):
    
    def test_inverting_amplifier_netlist(self):
        """
        Tests the Netlist Parser ability to compile an Inverting OpAmp circuit from a SPICE string,
        and verifies the parsed Circuit object solves correctly under the MNA Engine.
        """
        
        # Raw Multi-Line SPICE String
        spice_netlist = """
        * Op-Amp Inverting Amplifier Headless Test
        * K = -Rf / Rin = -100k / 10k = -10
        
        V1 in 0 1.0  // DC Source 1V
        Rin in n_inv 10k ; Input resistor
        
        Rf n_inv out 100k
        
        * E-source representation for Op-Amp (out in_p in_n gain)
        E1 out 0 n_inv 100000
        """
        
        # 1. Parse into Circuit Object
        circuit = NetlistParser.parse_netlist(spice_netlist, circuit_name="Parsed MNA")
        
        # Basic parsing structural validation
        self.assertEqual(len(circuit.get_components()), 4, "Parser failed to register all 4 physical components.")
        nodes = circuit.get_unique_nodes()
        self.assertIn("in", nodes)
        self.assertIn("n_inv", nodes)
        self.assertIn("out", nodes)
        self.assertIn("0", nodes)
        
        # 2. Seamlessly route to mathematical backend
        stamper = MNAStamper(circuit)
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
        
        print(f"\n[SPICE Parsed OpAmp] Vout = {vout:.3f}V (Expected -10.0V)")
        print(f"[SPICE Parsed OpAmp] Virtual Ground = {v_inv:.6f}V (Expected ~0.0V)")
        
        # The true test of headless engineering
        self.assertAlmostEqual(vout, -10.0, places=2, msg="Parsed Inverting Amplifier math routing failed!")
        self.assertAlmostEqual(v_inv, 0.0, places=3, msg="Parsed OpAmp Virtual Ground collapsed!")

if __name__ == "__main__":
    unittest.main()
