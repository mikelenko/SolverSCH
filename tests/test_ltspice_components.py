import os
import unittest
import numpy as np

from solver_sch.model.circuit import Circuit, Resistor, Capacitor, Inductor, ACVoltageSource, OpAmp
from solver_sch.utils.verifier import LTspiceVerifier

class TestLTspiceComponents(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.verifier = LTspiceVerifier()

    def test_capacitor_ac_voltage_source(self):
        """
        Test RC Low-Pass Filter in LTSpice.
        R = 1k, C = 1uF. fc = 159.15Hz.
        """
        ckt = Circuit("RC_Test", ground_name="0")
        
        R = 1000.0
        C = 1e-6
        fc = 1.0 / (2.0 * np.pi * R * C)
        
        ckt.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=fc, dc_offset=0.0, ac_mag=1.0, ac_phase=0.0))
        ckt.add_component(Resistor("R1", "in", "out", R))
        ckt.add_component(Capacitor("C1", "out", "0", C))
        
        raw_file = self.verifier.verify(ckt, ".ac dec 10 10 1k")
        data = self.verifier.parse_raw(raw_file)
        
        freqs = data.get_trace("frequency").get_wave()
        v_out_cmplx = data.get_trace("V(out)").get_wave()
        
        # Calculate magnitude
        v_out_mag = 20 * np.log10(np.abs(v_out_cmplx))
        
        # Assert at cutoff frequency - the closest point in the sweep
        idx_fc = (np.abs(np.abs(freqs) - fc)).argmin()
        mag_at_fc = v_out_mag[idx_fc]
        
        self.assertAlmostEqual(mag_at_fc, -3.01, delta=0.5, msg="Capacitor RC filter magnitude failed -3dB test")

    def test_inductor(self):
        """
        Test RL High-Pass Filter behavior in LTSpice.
        R = 1k, L = 1mH. fc = R / (2*pi*L) = 159.15kHz.
        """
        ckt = Circuit("RL_Test", ground_name="0")
        
        R = 1000.0
        L = 1e-3
        fc = R / (2.0 * np.pi * L)
        
        ckt.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=fc, dc_offset=0.0, ac_mag=1.0, ac_phase=0.0))
        ckt.add_component(Inductor("L1", "in", "out", L))
        ckt.add_component(Resistor("R1", "out", "0", R))
        
        raw_file = self.verifier.verify(ckt, ".ac dec 10 1k 1Meg")
        data = self.verifier.parse_raw(raw_file)
        
        freqs = data.get_trace("frequency").get_wave()
        v_out_cmplx = data.get_trace("V(out)").get_wave()
        
        # Calculate magnitude
        v_out_mag = 20 * np.log10(np.abs(v_out_cmplx))
        
        idx_fc = (np.abs(np.abs(freqs) - fc)).argmin()
        mag_at_fc = v_out_mag[idx_fc]
        
        self.assertAlmostEqual(mag_at_fc, -3.01, delta=0.5, msg="Inductor RL filter magnitude failed -3dB test")

    def test_opamp_vcvs(self):
        """
        Test Non-Inverting OpAmp (Gain = 1 + Rf/Rg = 1 + 10k/1k = 11).
        Because it's modeled as a VCVS with very high gain, it should precisely amplify by 11.
        """
        ckt = Circuit("OpAmp_Test", ground_name="0")
        
        # DC source for easy verification
        ckt.add_component(ACVoltageSource("Vin", "in_p", "0", amplitude=0.0, frequency=0.0, dc_offset=1.0, ac_mag=0.0, ac_phase=0.0))
        
        # OpAmp VCVS Model overrides VCC/VEE in exporter
        ckt.add_component(OpAmp("U1", "in_p", "in_n", "out"))
        
        ckt.add_component(Resistor("Rf", "out", "in_n", 10000))
        ckt.add_component(Resistor("Rg", "in_n", "0", 1000))

        # We can use our DC verify engine here since it's a DC test
        passed, msg = self.verifier.verify_dc(ckt, target_v=11.0, tolerance=0.01)
        self.assertTrue(passed, msg)

if __name__ == "__main__":
    unittest.main()
