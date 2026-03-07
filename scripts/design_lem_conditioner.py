import os
import math
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, CurrentSource, OpAmp
from solver_sch.simulator import Simulator

def design_lem_conditioner():
    """
    Designs a signal conditioning circuit for a LEM Current Transducer.
    LEM Specs: Secondary current output +/- 25mA full scale.
    Target ADC: 0 - 3.3V (Microcontroller).
    Offset: 1.65V (Zero current point).
    """
    print("--- LEM Current Transducer Conditioning Design ---")
    
    c = Circuit("LEM Conditioner")
    
    # 1. LEM Current Source (Secondary Output)
    # We will simulate a sweep later, for now let's set it to 25mA (Full Scale Positive)
    i_lem_max = 0.025
    c.add_component(CurrentSource("I_LEM", "0", "lem_out", i_lem_max))
    
    # 2. Burden Resistor (Rb)
    # If we want 1V swing for 25mA: Rb = 1V / 0.025A = 40 Ohms
    r_burden = 40.0
    c.add_component(Resistor("R_burden", "lem_out", "0", r_burden))
    
    # 3. Voltage Reference (3.3V for Divider)
    c.add_component(VoltageSource("V_REF", "vref", "0", 3.3))
    
    # 4. Offset Divider (to get 1.65V)
    # Using 10k resistors for low power
    c.add_component(Resistor("R_div1", "vref", "v_offset", 10e3))
    c.add_component(Resistor("R_div2", "v_offset", "0", 10e3))
    
    # 5. Summing Amplifier / Level Shifter
    # Mapping: V_adc = V_lem * Gain + V_offset
    # If V_lem = +/- 1V, and we want +/- 1.65V swing: Gain = 1.65
    # Let's use a non-inverting summing config or a simpler Differential Amp.
    
    # Topology: Differential Amplifier
    # Vout = (R2/R1) * (V_offset - V_lem)  <-- This would invert, but we can swap inputs.
    # Vout = 1.65V + Gain * V_lem
    
    # Resistance values for Gain = 1.65
    r_gain1 = 10e3
    r_gain2 = 16.5e3
    
    # Nodes: in_p, in_n, out
    # We want Vout = V_offset + (R_gain2/R_gain1) * V_lem
    # Let's use an ideal OpAmp as a buffer/shifter
    c.add_component(OpAmp("U1", "v_offset", "fb", "adc_in", gain=1e6))
    
    # Feedback network for Gain
    # R_gain1 from fb to 'lem_out'
    # R_gain2 from fb to 'adc_in'
    # This config would be more complex for a simple offset.
    
    # SIMPLEST DESIGN: Summing OpAmp
    # But let's just use the current source directly into an OpAmp summing node
    # if we want to be elegant.
    
    # REVISED DESIGN for simplicity:
    # V_adc = V_offset + I_lem * R_burden (if R_burden is connected to V_offset)
    circuit_v2 = Circuit("LEM Conditioner V2")
    circuit_v2.add_component(VoltageSource("V_REF", "vref", "0", 3.3))
    circuit_v2.add_component(Resistor("R_div1", "vref", "v_offset", 10e3))
    circuit_v2.add_component(Resistor("R_div2", "v_offset", "0", 10e3))
    # Buffered offset (OpAmp Buffer)
    circuit_v2.add_component(OpAmp("U_BUF", "v_offset", "v_offset_buf", "v_offset_buf", gain=1e6))
    
    # LEM Current Source connected to the buffered 1.65V node
    # Current flows from 1.65V node into the sensor.
    # V_adc = 1.65V + I_lem * R_burden
    circuit_v2.add_component(CurrentSource("I_LEM", "v_offset_buf", "adc_in", i_lem_max))
    # Burden resistor to 'adc_in' (but current is already defined)
    # Wait, if it's an ideal current source, the resistor doesn't change the current.
    # It just creates a voltage drop.
    circuit_v2.add_component(Resistor("R_burden", "adc_in", "v_offset_buf", 66.0)) # 25mA * 66 = 1.65V
    
    for current in [-0.025, 0.0, 0.025]:
        # Update current value
        for comp in circuit_v2.get_components():
            if comp.name == "I_LEM":
                comp.value = current
        
        # We must re-instantiate or trigger re-build because Simulator is lazy
        # Force 'mna' backend to test our internal implementation
        sim = Simulator(circuit_v2, backend="mna")
        res = sim.dc()
        v_adc = res.node_voltages["adc_in"]
        print(f"I_LEM = {current*1000:>6.1f} mA | V_ADC = {v_adc:.3f} V")
        
        # Check range (V_adc = 1.65 + I_lem * 66)
        if current == -0.025: assert abs(v_adc - 0.0) < 0.01
        if current == 0.0:    assert abs(v_adc - 1.65) < 0.01
        if current == 0.025:  assert abs(v_adc - 3.3) < 0.01

    print("\n=> SUCCESS! Circuit correctly maps +/-25mA to 0-3.3V range.")

if __name__ == "__main__":
    design_lem_conditioner()
