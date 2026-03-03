import unittest
from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestHierarchy(unittest.TestCase):
    
    def test_cascaded_voltage_divider(self):
        """
        Tests the .SUBCKT macro expansion and node prefixing algorithms.
        A 10V source feeds X1(Divider), which feeds X2(Divider).
        """
        netlist = """
* Main Netlist
V1 vdd 0 10.0
X1 vdd mid 0 DIVIDER
X2 mid out 0 DIVIDER

* Subcircuit Definitions
.SUBCKT DIVIDER in out gnd_port
R1 in out 10k
R2 out gnd_port 10k
.ENDS
"""
        # Parsing should automatically flatten X1 and X2 into 4 resistors total
        circuit = NetlistParser.parse_netlist(netlist, "Hierarchy Validation")
        
        comps = list(circuit.get_components())
        
        # 1 Voltage source + 4 Resistors
        self.assertEqual(len(comps), 5, "Flattened circuit should exactly contain 5 components.")
        
        # Verify prefixed naming convention
        resistor_names = [c.name for c in comps if c.name.startswith('X')]
        self.assertIn('X1.R1', resistor_names)
        self.assertIn('X1.R2', resistor_names)
        self.assertIn('X2.R1', resistor_names)
        self.assertIn('X2.R2', resistor_names)
        
        # Execute DC Analysis to mathematically prove topological integrity
        stamper = MNAStamper(circuit)
        stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=stamper.A_lil,
            z_vector=stamper.z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        result = solver.solve()
        
        # Math Proof: 
        # X2 input resistance = 10k + 10k = 20k
        # X1 lower leg = 10k || 20k = 6.666k
        # V(mid) = 10V * (6.666k / 16.666k) = 4.0V
        # V(out) = 4.0V * (10k / 20k) = 2.0V
        self.assertAlmostEqual(result.node_voltages.get('mid', 0.0), 4.0, places=3)
        self.assertAlmostEqual(result.node_voltages.get('out', 0.0), 2.0, places=3)

if __name__ == "__main__":
    unittest.main()
