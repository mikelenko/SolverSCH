import asyncio
import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.simulator import Simulator
from solver_sch.ai.design_reviewer import DesignReviewAgent

# Configure logging to see parser details
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("altium_test")

async def test_altium_integration():
    netlist_path = os.path.join("Import", "sensor_interface_altium.nsx")
    if not os.path.exists(netlist_path):
        # Fallback for case sensitivity or different root
        netlist_path = os.path.join("import", "sensor_interface_altium.nsx")
    
    if not os.path.exists(netlist_path):
        print(f"ERROR: Netlist file not found at {netlist_path}")
        return

    print(f"--- PARSING ALTIUM NETLIST: {netlist_path} ---")
    try:
        with open(netlist_path, 'r', encoding='utf-8', errors='ignore') as f:
            netlist_text = f.read()
            
        parser = NetlistParser()
        circuit = parser.parse_netlist(netlist_text, circuit_name="Altium Sensor Interface")
        
        # Force a sensor voltage for demonstration (150mV * (1 + 22k/1k) = 3.45V)
        for comp in circuit.get_components():
            if comp.name == "V_SENSOR":
                comp.dc_offset = 0.15
                
    except Exception as e:
        print(f"PARSER ERROR: {e}")
        return

    # 1. Extract BOM
    print("\n--- BILL OF MATERIALS (BOM) ---")
    bom = []
    for comp in circuit.get_components():
        info = f"{comp.name}: {type(comp).__name__} at nodes {list(comp.nodes())}"
        if hasattr(comp, 'value'):
            info += f", Value: {comp.value}"
        elif hasattr(comp, 'gain'):
            info += f", Gain: {comp.gain}"
        print(info)
        bom.append(info)

    # 2. Run Simulation
    print("\n--- RUNNING SIMULATION (DC Operating Point) ---")
    try:
        sim = Simulator(circuit, backend="mna") 
        dc_res = sim.dc()
        
        sim_summary = dc_res.to_dict()
        print("DC Voltages:")
        for node, voltage in dc_res.node_voltages.items():
            print(f"  {node}: {voltage:.4f}V")
            
    except Exception as e:
        print(f"SIMULATION ERROR: {e}")
        sim_summary = {"error": str(e)}

    # 3. AI Design Review
    print("\n--- INITIATING AI DESIGN REVIEW (Qwen 14B) ---")
    agent = DesignReviewAgent(
        model="qwen2.5-coder:14b",
        allowed_tools=["recalculate_divider", "recalculate_opamp_gain"]
    )
    
    task_intent = "Please perform a comprehensive design review of this circuit based on the standard system guidelines."
    
    report = await agent.review_design_async(
        circuit_info="\n".join(bom),
        sim_results=sim_summary,
        task_intent=task_intent
    )
    
    with open("altium_audit_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    
    print("\n" + "="*50)
    print("ALTIUM DESIGN REVIEW REPORT SAVED TO altium_audit_report.md")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_altium_integration())
