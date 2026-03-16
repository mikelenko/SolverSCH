from solver_sch.model.altium_model import AltiumProject, AltiumComponent, AltiumNet, AltiumPin
from solver_sch.parser.altium_parser import AltiumParser

def test_isolate_subcircuit():
    """Verify that BFS graph traversal isolates a subcircuit properly without leaking through stop nets."""
    proj = AltiumProject()
    
    # R1 -> NetA, NetB (NetB is StopNet)
    proj.components['R1'] = AltiumComponent('R1', 'RES', '10k')
    
    # R2 -> NetA, NetC (NetA connects R1 and R2; R2 links to NetC)
    proj.components['R2'] = AltiumComponent('R2', 'RES', '10k')
    
    # R3 -> NetB, NetD (Should be excluded since BFS stops at NetB)
    proj.components['R3'] = AltiumComponent('R3', 'RES', '10k')
    
    # C1 -> NetC, NetE (NetC connects R2 and C1; NetE is dead end)
    proj.components['C1'] = AltiumComponent('C1', 'CAP', '100n')

    proj.nets = [
        AltiumNet('NetA', [AltiumPin('R1', '1'), AltiumPin('R2', '1')]),
        AltiumNet('STOP_GND', [AltiumPin('R1', '2'), AltiumPin('R3', '1')]),
        AltiumNet('NetC', [AltiumPin('R2', '2'), AltiumPin('C1', '1')]),
        AltiumNet('NetD', [AltiumPin('R3', '2')]),
        AltiumNet('NetE', [AltiumPin('C1', '2')])
    ]
    
    # Start extraction at NetE. The graph should traverse: NetE -> C1 -> NetC -> R2 -> NetA -> R1 -> STOP_GND. 
    # It must stop at STOP_GND, so R3 and NetD should NOT be included.
    isolated = AltiumParser.isolate_subcircuit(proj, 'NetE', ['STOP_GND'])
    assert 'C1' in isolated.components
    assert 'R2' in isolated.components
    assert 'R1' in isolated.components
    assert 'R3' not in isolated.components  # Because STOP_GND was a wall
    
    assert len(isolated.nets) == 4          # NetA, STOP_GND, NetC, NetE
    assert not any(n.name == 'NetD' for n in isolated.nets)
