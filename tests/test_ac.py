import unittest
import numpy as np

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, ACVoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

class TestACAnalysis(unittest.TestCase):
    
    def test_rc_lowpass_filter(self):
        """
        Tests Small-Signal AC Analysis over an RC Low-Pass Filter.
        R1 = 1k, C1 = 1uF
        Vin = 1.0V AC Phase 0
        
        Cutoff Frequency fc = 1 / (2*pi*R*C) ~= 159.15 Hz
        At fc, the expected magnitude drop is approx -3.0 dB.
        """
        ckt = Circuit("RC Low-Pass Filter", ground_name="0")
        
        R = 1000.0
        C = 1e-6
        fc = 1.0 / (2.0 * np.pi * R * C)
        
        ckt.add_component(ACVoltageSource("Vin", "in", "0", amplitude=0.0, frequency=0.0, ac_mag=1.0, ac_phase=0.0))
        ckt.add_component(Resistor("R1", "in", "out", R))
        ckt.add_component(Capacitor("C1", "out", "0", C))
        
        stamper = MNAStamper(ckt)
        # Pre-assign memory structures structurally
        stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=stamper.A_lil,
            z_vector=stamper.z_vec,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        
        # We sweep from 10 Hz to 10 kHz to ensure we capture the 159Hz point
        # High resolution needed to hit exactly near fc
        freqs, mags_db, phases_deg = solver.simulate_ac(f_start=10.0, f_stop=10000.0, points_per_decade=100, stamper_ref=stamper)
        
        out_mag = mags_db.get("out")
        self.assertIsNotNone(out_mag, "Failed to retrieve AC magnitude for output node.")
        
        # Find the index of the frequency closest to theoretical fc
        idx_fc = (np.abs(freqs - fc)).argmin()
        actual_fc = freqs[idx_fc]
        mag_at_fc = out_mag[idx_fc]
        
        print(f"\n[AC Low-Pass] Theoretical Cutoff: {fc:.2f} Hz")
        print(f"[AC Low-Pass] Closest Swept Freq: {actual_fc:.2f} Hz")
        print(f"[AC Low-Pass] Magnitude at Cutoff: {mag_at_fc:.3f} dB (Expected ~ -3.0 dB)")
        
        # Test 1: -3dB Cutoff Magnitude Assertion (+/- 0.1dB tolerance)
        self.assertAlmostEqual(mag_at_fc, -3.01, delta=0.1, msg="Magnitude didn't drop by -3dB at Cutoff frequency.")
        
        # Test 2: Low Freq Pass (near 0 dB)
        self.assertAlmostEqual(out_mag[0], 0.0, delta=0.1, msg="Filter didn't pass low frequencies structurally.")
        
        # Test 3: High Freq Block (significant negative dB)
        self.assertLess(out_mag[-1], -20.0, msg="Filter failed to attenuate high frequencies.")

if __name__ == "__main__":
    unittest.main()
