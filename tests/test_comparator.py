import pytest
from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.model.circuit import Comparator

def evaluate_dc_netlist(netlist_str: str) -> float:
    circuit = NetlistParser.parse_netlist(netlist_str, "Test Circuit")
    stamper = MNAStamper(circuit)
    stamper.stamp_linear()
    
    solver = SparseSolver(
        A_matrix=stamper.A_lil,
        z_vector=stamper.z_vec,
        node_to_idx=stamper.node_to_idx,
        vsrc_to_idx=stamper.vsrc_to_idx,
        n_independent_nodes=stamper.n
    )
    solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
    
    result = solver.solve()
    return result.node_voltages.get('out', 0.0)

def test_comparator_high_output():
    """Test when Non-Inverting > Inverting, it should output V_high (5.0V)."""
    netlist = '''
    V1 in_p 0 3.0
    V2 in_n 0 1.0
    U1 in_p in_n out 5.0 0.0
    R1 out 0 1k
    '''
    vout = evaluate_dc_netlist(netlist)
    assert abs(vout - 5.0) < 0.01

def test_comparator_low_output():
    """Test when Non-Inverting < Inverting, it should output V_low (0.0V)."""
    netlist = '''
    V1 in_p 0 1.0
    V2 in_n 0 3.0
    U1 in_p in_n out 5.0 0.0
    R1 out 0 1k
    '''
    vout = evaluate_dc_netlist(netlist)
    assert abs(vout - 0.0) < 0.01

def test_comparator_custom_rails():
    """Test Comparator with custom high/low rails (-2.5V to 2.5V)."""
    netlist_high = '''
    V1 in_p 0 1.0
    V2 in_n 0 0.0
    U1 in_p in_n out 2.5 -2.5
    R1 out 0 1k
    '''
    vout_high = evaluate_dc_netlist(netlist_high)
    assert abs(vout_high - 2.5) < 0.01
    
    netlist_low = '''
    V1 in_p 0 0.0
    V2 in_n 0 1.0
    U1 in_p in_n out 2.5 -2.5
    R1 out 0 1k
    '''
    vout_low = evaluate_dc_netlist(netlist_low)
    assert abs(vout_low - (-2.5)) < 0.01
