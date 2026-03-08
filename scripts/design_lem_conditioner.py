"""
design_lem_conditioner.py -> Design and Verification of a LEM Signal Conditioner.

Task:
1. Build a circuit with a burden resistor and an OpAmp level-shifter.
2. Perform a DC sweep for ±25mA LEM current.
3. Use DesignReviewAgent to audit the results.
"""

import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, CurrentSource, OpAmp
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.ai.design_reviewer import DesignReviewAgent

async def run_design_verification():
    print("--- DESIGNING LEM CURRENT CONDITIONER ---")
    
    # 1. Physical Parameters
    I_MAX = 0.025  # ±25mA
    V_REF = 1.65   # Offset for 3.3V ADC
    R_BURDEN = 66.0 # 1.65V / 25mA = 66 Ohms
    R_VAL = 10000.0 # Standard 10k resistor for OpAmp network
    
    # 2. Build Circuit
    ckt = Circuit("LEM Signal Conditioner")
    
    # Sensor & Burden
    i_lem = CurrentSource("I_LEM", "0", "sensor_out", 0.0)
    r_burden = Resistor("R_burden", "sensor_out", "0", R_BURDEN)
    ckt.add_component(i_lem)
    ckt.add_component(r_burden)
    
    # Offset Voltage
    v_offset = VoltageSource("V_offset", "offset_node", "0", V_REF)
    ckt.add_component(v_offset)
    
    # Summing Network (Non-inverting Summer with gain of 2)
    # V_sum = (V_sensor + V_offset) / 2
    ckt.add_component(Resistor("R1", "sensor_out", "sum_node", R_VAL))
    ckt.add_component(Resistor("R2", "offset_node", "sum_node", R_VAL))
    
    # OpAmp Gain = 1 + Rf/Rg = 2
    ckt.add_component(Resistor("R_fb", "adc_in", "fb_node", R_VAL))
    ckt.add_component(Resistor("R_g", "fb_node", "0", R_VAL))
    
    # Ideal OpAmp
    # in_p at sum_node, in_n at fb_node, out at adc_in
    op = OpAmp("U1", "sum_node", "fb_node", "adc_in", gain=1e6)
    ckt.add_component(op)
    
    # 3. Perform DC Sweep
    print("--- PERFORMING DC SWEEP (-25mA to +25mA) ---")
    test_currents = [-0.025, 0.0, 0.025]
    sweep_results = {}
    
    for i_val in test_currents:
        i_lem._value = i_val # Update internal value directly for sweep
        
        stamper = MNAStamper(ckt)
        A, z = stamper.stamp_linear()
        
        solver = SparseSolver(
            A_matrix=A,
            z_vector=z,
            node_to_idx=stamper.node_to_idx,
            vsrc_to_idx=stamper.vsrc_to_idx,
            n_independent_nodes=stamper.n
        )
        res = solver.solve()
        
        # Get ADC voltage
        v_adc = res.node_voltages.get("adc_in", 0.0)
        
        sweep_results[f"{i_val*1000:.1f}mA"] = round(v_adc, 4)
        print(f"I_LEM: {i_val*1000:>6.1f}mA -> V_ADC: {v_adc:.4f}V")

    # 4. LLM Verification
    print("\n--- INITIATING DESIGN REVIEW AGENT ---")
    agent = DesignReviewAgent(model="qwen2.5-coder:14b")
    
    task_intent = (
        "Design a LEM current transducer conditioner. The sensor outputs between -25mA and +25mA. "
        "The final output voltage ('adc_in' node) must be strictly safely within the 0V to 3.3V range for an MCU ADC. "
        "Center voltage (at 0mA) should be ~1.65V."
    )
    
    simulation_data = {
        "dc_sweep": sweep_results,
        "target_range": [0.0, 3.3],
        "center_target": 1.65
    }
    
    report = await agent.review_design_async(
        circuit_info=ckt.describe(),
        sim_results=simulation_data,
        task_intent=task_intent
    )
    
    print("\n" + "="*50)
    print("ENGINEERING DESIGN REVIEW REPORT")
    print("="*50)
    print(report)

if __name__ == "__main__":
    asyncio.run(run_design_verification())
