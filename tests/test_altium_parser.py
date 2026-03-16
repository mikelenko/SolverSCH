import pytest
from solver_sch.model.altium_model import AltiumProject, AltiumComponent, AltiumNet, AltiumPin
from solver_sch.parser.altium_parser import AltiumParser
from solver_sch.model.circuit import Resistor, Capacitor, Diode

def test_extract_value():
    """Testy rygorystyczne na parsowanie inżynieryjnych zapisów wartości."""
    assert AltiumParser.extract_value("100k 1% 0402") == pytest.approx(100000.0)
    assert AltiumParser.extract_value("10p/50V C0G 0402") == pytest.approx(10e-12)
    assert AltiumParser.extract_value("1u/16V X7R") == pytest.approx(1e-6)
    assert AltiumParser.extract_value("0R") == pytest.approx(0.001)
    assert AltiumParser.extract_value("0R 0402") == pytest.approx(0.001)
    assert AltiumParser.extract_value("1k5 1% 0402") == pytest.approx(1500.0)
    assert AltiumParser.extract_value("620R") == pytest.approx(620.0)
    assert AltiumParser.extract_value("51R 1% 0402") == pytest.approx(51.0)
    assert AltiumParser.extract_value("2R2") == pytest.approx(2.2)
    assert AltiumParser.extract_value("4U7/16V") == pytest.approx(4.7e-6)
    assert AltiumParser.extract_value("random string without numbers") is None
    assert AltiumParser.extract_value("100 1%") == 100.0

def test_parse_netlist_content():
    """Weryfikuje odczyt bloków komponentów [...] i sieci (...)."""
    netlist_text = """
[
C1_1
CAPC0402L
100n/16V X7R 0402
]
[
R184_2
RESC0402L
10k 1% 0402
]
[
U1_1
SOIC127P600-8L
TCAN1051HDRQ1
]
(
+5V
C1_1-1
)
(
GND
C1_1-2
R184_2-1
U1_1-2
)
"""
    proj = AltiumParser.parse_netlist_content(netlist_text)
    
    assert len(proj.components) == 3
    assert proj.components['C1_1'].comment == "100n/16V X7R 0402"
    assert proj.components['R184_2'].footprint == "RESC0402L"
    assert proj.components['U1_1'].prefix == "U"
    
    assert len(proj.nets) == 2
    net_5v = next(n for n in proj.nets if n.name == "+5V")
    assert len(net_5v.pins) == 1
    assert net_5v.pins[0].designator == "C1_1"
    assert net_5v.pins[0].pin == "1"

def test_convert_to_circuit():
    """Weryfikuje proces konwersji ze struktur Altium do czystego solver_sch Circuit."""
    proj = AltiumProject()
    proj.components = {
        'R1': AltiumComponent('R1', 'RES', '10k'),
        'C1': AltiumComponent('C1', 'CAP', '100n'),
        'D1': AltiumComponent('D1', 'DIO', 'DIODE'),
        'U1': AltiumComponent('U1', 'SOT', 'LMV321') # Wzmacniacz op, zostanie
    }
    proj.nets = [
        AltiumNet('+5V', [AltiumPin('R1', '1')]),
        AltiumNet('NetR1_C1', [AltiumPin('R1', '2'), AltiumPin('C1', '1'), AltiumPin('D1', '1')]),
        AltiumNet('0', [AltiumPin('C1', '2'), AltiumPin('D1', '2')])
    ]
    
    circuit = AltiumParser.convert_to_circuit(proj)
    
    components = circuit.get_components()
    comp_map = {c.name: c for c in components}
    
    assert len(components) == 4 # R1, C1, D1, U1
    
    assert isinstance(comp_map['R1'], Resistor)
    assert comp_map['R1'].resistance == 10000.0
    assert comp_map['R1'].node1 == "+5V"
    assert comp_map['R1'].node2 == "NetR1_C1"
    
    assert isinstance(comp_map['C1'], Capacitor)
    assert comp_map['C1'].capacitance == pytest.approx(100e-9)
    assert comp_map['C1'].node2 == "0"
    
    assert isinstance(comp_map['D1'], Diode)
    assert comp_map['D1'].anode == "NetR1_C1"
    assert comp_map['D1'].cathode == "0"
