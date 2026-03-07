import math
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, MOSFET_N, ModelCard
from solver_sch.simulator import Simulator

def test_mosfet_triode_region():
    """
    Test weryfikujący zbieżność oraz działanie NMOS w zakresie liniowym (triodowym).
    Warunek triodowy: Vgs > Vth ORAZ Vds < Vgs - Vth
    """
    circuit = Circuit("MOSFET Triode Test")
    
    # Model NMOS (Level 1)
    nmos_model = ModelCard("BS170", "NMOS", {"VTO": "2.0", "KP": "0.1", "LAMBDA": "0.01"})
    circuit.add_model(nmos_model)
    
    V_DD = 10.0
    V_GG = 5.0
    R_D = 1000.0
    
    circuit.add_component(VoltageSource("VDD", "vd", "0", V_DD))
    circuit.add_component(VoltageSource("VGG", "vg", "0", V_GG))
    circuit.add_component(Resistor("RD", "vd", "drain", R_D))
    circuit.add_component(MOSFET_N("M1", "drain", "vg", "0", model="BS170"))
    
    # MNA Simulation
    sim = Simulator(circuit, backend="ltspice")
    result = sim.dc()
    
    v_ds = result.node_voltages.get("drain", 0.0)
    v_th = 2.0
    overdrive = V_GG - v_th
    
    # 1. Asercja: tranzystor JEST w zakresie triodowym
    assert v_ds < overdrive, f"Spodziewano się Vds < {overdrive}V (trioda), uzykano {v_ds}V"
    
    # 2. Asercja empiryczna (bazująca na wcześniejszym sukcesie)
    assert abs(v_ds - 0.033) < 0.005, f"Spodziewano się odłożenia 33mV na nasyconym kanale, uzyskano {v_ds}V"
