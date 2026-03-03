import unittest
import numpy as np

from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestCMOSLogic(unittest.TestCase):
    
    def simulate_cmos_inverter(self, v_in: float) -> float:
        """Helper to run a non-linear sparse solve for a specific input voltage."""
        netlist = f"""
* CMOS Inverter Test (Vin = {v_in}V)
Vdd vdd 0 5.0
Vin in 0 {v_in}

* M<name> <drain> <gate> <source> <type>
M1 out in vdd PMOS W=10u L=1u
M2 out in 0 NMOS W=5u L=1u
"""
        circuit = NetlistParser.parse_netlist(netlist, "CMOS_Gate")
        
        stamper = MNAStamper(circuit)
        stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=stamper.A_lil,
            z_vector=stamper.z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
        
        # NR Solve
        result = solver.solve()
        
        return result.node_voltages.get("out", -999.0)

    def test_inverter_low_input(self):
        """Test 1: Input = 0V -> Output strict 5.0V (Pull-up strong, Pull-down Cutoff)."""
        v_out = self.simulate_cmos_inverter(0.0)
        self.assertAlmostEqual(v_out, 5.0, places=3, msg="Output should be rigidly 5.0V when Input is 0V")

    def test_inverter_high_input(self):
        """Test 2: Input = 5.0V -> Output strict 0.0V (Pull-down strong, Pull-up Cutoff)."""
        v_out = self.simulate_cmos_inverter(5.0)
        self.assertAlmostEqual(v_out, 0.0, places=3, msg="Output should be rigidly 0.0V when Input is 5.0V")

if __name__ == "__main__":
    unittest.main()
