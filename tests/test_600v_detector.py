import math
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, OpAmp
from solver_sch.simulator import Simulator

def test_600v_detector_scaling():
    """
    Testuje obwód mający za zadanie zeskanować 600V wejścia do bezpiecznego zakresu mikrokontrolera (5V).
    Używa kaskady wysokonapięciowych rezystorów oraz bufora VCVS wysokiej impedancji.
    """
    c = Circuit("600V to 5V Detector Test")

    c.add_component(VoltageSource("Vin", "in", "0", 600.0))

    # Wysokonapięciowy dzielnik (1.19M + 10k)
    c.add_component(Resistor("R_h1", "in", "n1", 400e3))
    c.add_component(Resistor("R_h2", "n1", "n2", 400e3))
    c.add_component(Resistor("R_h3", "n2", "div", 390e3))
    c.add_component(Resistor("R_low", "div", "0", 10e3))

    # Wzmacniacz buforujący napięcie testowe
    c.add_component(OpAmp("U1", "div", "out", "out", gain=1e6))

    # MNA Simulation
    sim = Simulator(c, backend="mna")
    dc_result = sim.dc()
    
    v_div = dc_result.node_voltages["div"]
    v_out = dc_result.node_voltages["out"]
    
    # Tolerancja rzędu 5mV dla DC punktu statycznego
    assert math.isclose(v_div, 5.0, abs_tol=0.005), f"Węzeł zdzielony dał {v_div}V (oczekiwano 5V z 600V dzielnika 120:1)"
    assert math.isclose(v_out, 5.0, abs_tol=0.005), f"Wzmacniacz skopiował napięcie z na {v_out}V (oczekiwano kopii wzorcowej 5V na wyjściu bufora)"
