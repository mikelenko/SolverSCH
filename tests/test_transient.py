"""
test_transient.py -> Unit Test for Backward Euler numerical integration.
"""

import unittest
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, Capacitor
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver


class TestTransientRC(unittest.TestCase):
    
    def test_rc_charging_curve(self):
        """
        Validates the Backward Euler nested loop resolving a linear RC timing circuit.
        Circuit: 5V source -> 1k Ohm Resistor -> 1uF Capacitor -> Ground.
        Expected: Exponential charging curve achieving ~3.16V in tau = 1ms.
        """
        # 1. Model Layer
        ckt = Circuit("RC Charging Filter", ground_name="0")
        ckt.add_component(VoltageSource("V1", "1", "0", 5.0))
        ckt.add_component(Resistor("R1", "1", "2", 1000.0))  # 1k Ohm
        ckt.add_component(Capacitor("C1", "2", "0", 1e-6))   # 1uF
        
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
        
        # Inject dynamic equations callbacks
        # Transient parameters
        solver.set_transient_stampers(
            basis_cb=stamper.stamp_transient_basis,
            sources_cb=stamper.stamp_transient_sources,
            update_states_cb=stamper.update_states
        )
        # Non-linear stamper can be set too, works passively if no nonlinear components exist.
        solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
        
        # Run transient analysis for 5ms with step of 10us
        dt = 1e-5
        t_stop = 0.005
        results = solver.simulate_transient(t_stop, dt)
        
        # Search the timeline for t = 1ms (1e-3s)
        target_time = 1e-3
        target_voltage = 0.0
        
        for t, res in results:
            if abs(t - target_time) < (dt / 2.0):  # Safe float comparison
                target_voltage = res.node_voltages["2"]
                break
                
        # Theoretical Voltage at one Tau: V(tau) = V_src * (1 - e^-1)
        # V(1ms) = 5.0 * (1 - 0.367879) = 5.0 * 0.63212 = 3.1606 V
        
        # We accept a loose tolerance (e.g., delta 0.05) because Backward Euler has inherent local truncation error.
        self.assertAlmostEqual(
            target_voltage, 
            3.16, 
            delta=0.05, 
            msg=f"Capacitor RC transient failed. Expected ~3.16V, got {target_voltage:.4f}V"
        )

if __name__ == "__main__":
    unittest.main()
