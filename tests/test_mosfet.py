import unittest

from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, NMOS
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestNMOSInverter(unittest.TestCase):
    
    def test_nmos_inverter(self):
        """
        Tests an NMOS Inverter logic gate.
        VDD = 5V, Rd = 10k
        
        Logic 0 (Vin = 0V) -> Vout = 5V (Cutoff)
        Logic 1 (Vin = 5V) -> Vout ~ 0V (Linear/Triode Region)
        """
        
        # --- TEST CASE 1: Logic 0 -> 1 (Cutoff) ---
        ckt_low = Circuit("NMOS Inverter - Low", ground_name="0")
        
        ckt_low.add_component(VoltageSource("VDD", "vdd", "0", 5.0))
        ckt_low.add_component(VoltageSource("Vin", "in", "0", 0.0)) # Input LOW
        
        ckt_low.add_component(Resistor("Rd", "vdd", "out", 10000.0))
        ckt_low.add_component(NMOS("M1", drain="out", gate="in", source="0"))
        
        stamper_low = MNAStamper(ckt_low)
        A_lil_low, z_vec_low = stamper_low.stamp_linear()
        
        solver_low = SparseSolver(
            A_matrix=A_lil_low,
            z_vector=z_vec_low,
            node_to_idx=stamper_low.node_to_idx,
            vsrc_to_idx=stamper_low.vsrc_to_idx,
            n_independent_nodes=stamper_low.n
        )
        solver_low.set_nonlinear_stamper(stamper_low.stamp_nonlinear)
        
        result_low = solver_low.solve()
        vout_low = result_low.node_voltages.get("out", 0.0)
        
        # --- TEST CASE 2: Logic 1 -> 0 (Linear) ---
        ckt_high = Circuit("NMOS Inverter - High", ground_name="0")
        
        ckt_high.add_component(VoltageSource("VDD", "vdd", "0", 5.0))
        ckt_high.add_component(VoltageSource("Vin", "in", "0", 5.0)) # Input HIGH
        
        ckt_high.add_component(Resistor("Rd", "vdd", "out", 10000.0))
        ckt_high.add_component(NMOS("M1", drain="out", gate="in", source="0"))
        
        stamper_high = MNAStamper(ckt_high)
        A_lil_high, z_vec_high = stamper_high.stamp_linear()
        
        solver_high = SparseSolver(
            A_matrix=A_lil_high,
            z_vector=z_vec_high,
            node_to_idx=stamper_high.node_to_idx,
            vsrc_to_idx=stamper_high.vsrc_to_idx,
            n_independent_nodes=stamper_high.n
        )
        solver_high.set_nonlinear_stamper(stamper_high.stamp_nonlinear)
        
        result_high = solver_high.solve()
        vout_high = result_high.node_voltages.get("out", 0.0)
        
        print(f"\n[NMOS Inverter] Vin=0V -> Vout={vout_low:.3f}V (Expected ~5.0V)")
        print(f"[NMOS Inverter] Vin=5V -> Vout={vout_high:.3f}V (Expected ~0V)")
        
        # Validations
        self.assertAlmostEqual(vout_low, 5.0, places=2, msg="Inverter failed to reach HIGH state during Cutoff.")
        self.assertLess(vout_high, 0.5, msg="Inverter failed to drop LOW during Linear switch.")

if __name__ == "__main__":
    unittest.main()
