import math
import pytest
from solver_sch.model.circuit import Circuit, Resistor, CurrentSource
from solver_sch.simulator import Simulator

def test_current_source_ohm_law():
    """
    Law: V = I * R
    If I=2A and R=10 Ohm, then V(node) should be 20V.
    """
    c = Circuit("Ohm Law with Current Source")
    
    # 2A source from node 'in' to ground '0'
    # In Spice notation: I1 0 in 2A (Current flows 0 -> in)
    # Our implementation: node1 -> node2. So node1='0', node2='in'.
    c.add_component(CurrentSource("I1", "0", "in", 2.0))
    c.add_component(Resistor("R1", "in", "0", 10.0))
    
    sim = Simulator(c)
    result = sim.dc()
    
    v_in = result.node_voltages["in"]
    
    # Expected: 2A * 10 Ohm = 20V
    assert math.isclose(v_in, 20.0, rel_tol=1e-9)

def test_current_source_floating_potential():
    """
    Multiple current sources in series/parallel.
    """
    c = Circuit("Current Divider")
    # I1(1A) -> I2(0.5A) -> R(10)
    # Node n1: I1 enters. 
    c.add_component(CurrentSource("I1", "0", "n1", 1.0))
    # Node n1: I2 leaves.
    c.add_component(CurrentSource("I2", "n1", "0", 0.3))
    # Net current at n1: 1.0 - 0.3 = 0.7A
    c.add_component(Resistor("R1", "n1", "0", 100.0))
    
    sim = Simulator(c)
    result = sim.dc()
    
    v_n1 = result.node_voltages["n1"]
    # 0.7A * 100 Ohm = 70V
    assert math.isclose(v_n1, 70.0, rel_tol=1e-9)
