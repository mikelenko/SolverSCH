import numpy as np
from solver_sch.model.circuit import Circuit, Resistor, Capacitor, OpAmp, ACVoltageSource, VoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver

def test_sweep():
    # Setup the same remediated circuit
    ckt = Circuit("Linearity_Test")
    
    # Power
    ckt.add_component(VoltageSource("VCC", "vcc", "0", 15.0))
    ckt.add_component(VoltageSource("VEE", "vee", "0", -15.0))
    
    # Filter + Gain Stage
    r_filter = 10000.0
    c_filter = 106.1e-9
    r_in = 10000.0
    r_f = 30000.0
    
    vin_src = ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000.0, dc_offset=0.0)
    ckt.add_component(vin_src)
    ckt.add_component(Resistor("Rfilt", "in", "filt_node", r_filter))
    ckt.add_component(Capacitor("Cfilt", "filt_node", "0", c_filter))
    ckt.add_component(Resistor("Rin", "gain_node", "0", r_in))
    ckt.add_component(Resistor("Rf", "gain_node", "out", r_f))
    ckt.add_component(OpAmp("U1", in_p="filt_node", in_n="gain_node", out="out", gain=1e5))
    
    
    test_voltages = [0.0, 0.5, 1.0, 2.0, 3.0, 3.5, 4.0]
    print(f"{'Vin (V)':<10} | {'Vout (V)':<10} | {'Gain':<10}")
    print("-" * 35)
    
    for v in test_voltages:
        vin_src.dc_offset = v
        # Re-initialize stamper/solver to catch the new DC offset
        stamper = MNAStamper(ckt)
        stamper.stamp_linear()
        solver = SparseSolver(stamper.A_lil, stamper.z_vec, stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n)
        res = solver.solve()
        vout = res.node_voltages.get("out", 0.0)
        gain = vout / v if v != 0 else 0
        print(f"{v:<10.2f} | {vout:<10.4f} | {gain:<10.4f}")

if __name__ == "__main__":
    test_sweep()
