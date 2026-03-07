import os
import logging
from solver_sch import Circuit, Simulator, Resistor, VoltageSource, OpAmp

# Configure logging to see the execution flow
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("design_600v")

def design_600v_detector():
    """
    Designs a voltage measurement circuit that scales 600V DC to 5V DC.
    - High-voltage divider: 3x 396.6k (total 1.19M) + 10k.
    - OpAmp buffer for isolation.
    """
    c = Circuit("600V to 5V Detector")

    # 1. 600V Input Source
    c.add_component(VoltageSource("Vin", "in", "0", 600.0))

    # 2. High-Voltage Divider (Series resistors for voltage rating safety)
    # Total R_high = 1.19M
    c.add_component(Resistor("R_h1", "in", "n1", 400e3))
    c.add_component(Resistor("R_h2", "n1", "n2", 400e3))
    c.add_component(Resistor("R_h3", "n2", "div", 390e3))
    
    # 3. Low-side Resistor
    # Ratio = (1200k / 10k) = 120. 600V / 120 = 5.0V
    c.add_component(Resistor("R_low", "div", "0", 10e3))

    # 4. OpAmp Buffer (VCVS Backend)
    # Nodes: in_p, in_n, out
    c.add_component(OpAmp("U1", "div", "out", "out", gain=1e6))
    
    # 5. OpAmp Supplies
    c.add_component(VoltageSource("Vcc", "vcc", "0", 15.0))
    c.add_component(VoltageSource("Vee", "vee", "0", -15.0))

    # --- Simulation ---
    logger.info("Initializing Simulator...")
    sim = Simulator(c)
    
    # Run DC simulation
    dc_result = sim.dc()
    v_div = dc_result.node_voltages["div"]
    v_out = dc_result.node_voltages["out"]
    
    logger.info(f"--- Simulation Results ---")
    logger.info(f"Divider Voltage: {v_div:.4f} V")
    logger.info(f"Buffer Output:   {v_out:.4f} V")
    
    # Calculate Power Dissipation in R_h1
    i_div = 600 / (1190e3 + 10e3)
    p_h1 = (i_div ** 2) * 400e3
    logger.info(f"Power dissipation in R_h1 (400k): {p_h1*1000:.2f} mW")

    # --- Cross-Validation with LTspice ---
    logger.info("Running LTspice Cross-Validation...")
    try:
        comparison = sim.compare_with_ltspice(analyses=["dc"], workdir="results/ltspice_signoff")
        dc_comp = comparison["dc"]
        logger.info(f"LTspice Match: {dc_comp.summary()}")
        
        # --- Generate Report ---
        report_path = "results/600V_Detector_Report.xlsx"
        sim.report(report_path, ltspice_results=comparison, auto_open=False)
        logger.info(f"Excel report generated: {os.path.abspath(report_path)}")
        
    except Exception as e:
        logger.warning(f"LTspice verification failed (is it installed?): {e}")
        # Generate basic report if LTspice is missing
        sim.report("results/600V_Detector_Report.xlsx", auto_open=False)

if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    design_600v_detector()
