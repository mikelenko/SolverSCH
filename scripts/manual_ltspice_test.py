from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, BJT
from solver_sch.utils.verifier import LTspiceVerifier
import os

def manual_verify():
    print("=== Manual LTspice Verification Test ===")
    
    # 1. Build a simple Voltage Divider (12V -> 6V)
    ckt = Circuit("Manual Test Divider", ground_name="0")
    ckt.add_component(VoltageSource("1", "vcc", "0", 12.0))
    ckt.add_component(Resistor("1", "vcc", "out", 1000.0))
    ckt.add_component(Resistor("2", "out", "0", 1000.0))
    
    # 2. Build a BJT Inverter / Switch
    # VCC=12V, RC=1k, RB=10k. 
    ckt_bjt = Circuit("BJT Sign-off Test", ground_name="0")
    ckt_bjt.add_component(VoltageSource("VCC", "vcc", "0", 12.0))
    ckt_bjt.add_component(VoltageSource("VIN", "in", "0", 5.0)) # Input to base
    ckt_bjt.add_component(Resistor("C", "vcc", "out", 1000.0))
    ckt_bjt.add_component(BJT("Q1", "out", "in", "0")) # Simplified BJT call
    
    # Target: V_out = VCC - Ic*RC. With 5V base and 10k RB (omitted for now, direct drive for simplicity)
    # Wait, the Exporter uses R, V, Q, B. 
    # Let's add RB to avoid direct 5V on base which might be unstable in LTspice model
    ckt_bjt.add_component(Resistor("B", "in", "base_node", 10000.0))
    # Re-build ckt_bjt properly
    ckt_bjt = Circuit("BJT Sign-off Test", ground_name="0")
    ckt_bjt.add_component(VoltageSource("VCC", "vcc", "0", 12.0))
    ckt_bjt.add_component(VoltageSource("VIN", "in", "0", 5.0))
    ckt_bjt.add_component(Resistor("C", "vcc", "out", 1000.0))
    ckt_bjt.add_component(Resistor("B", "in", "base", 10000.0))
    ckt_bjt.add_component(BJT("1", "out", "base", "0"))
    
    print("\n--- BJT Verifier Test ---")
    # Base Current ~ (5 - 0.7) / 10k = 0.43mA
    # Collector Current ~ 100 * 0.43mA = 43mA (Saturation check)
    # Target Vout should be close to 0.2V (Saturation)
    passed_bjt, msg_bjt = LTspiceVerifier.verify_dc(ckt_bjt, 0.2)
    
    if passed_bjt:
        print(f"[SUCCESS] {msg_bjt}")
    else:
        print(f"[BJT VERSION] {msg_bjt}")
    
    # Cleanup verification files
    # for f in ["signoff.cir", "signoff.raw", "signoff.log"]:
    #     if os.path.exists(f):
    #         os.remove(f)

if __name__ == "__main__":
    manual_verify()
