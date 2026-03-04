from solver_sch.ai.auto_designer import AutonomousDesigner
from solver_sch.ai.llm_providers import get_provider

def test_monte_carlo_parsing():
    goal = "[DC TARGET: 5.0V] [MONTE CARLO: 500] Zaprojektuj dzielnik napięcia"
    designer = AutonomousDesigner(target_goal=goal, llm=get_provider("stub"))
    
    assert designer.sim_mode == 'DC'
    assert designer.target_dc_voltage == 5.0
    assert designer.monte_carlo_runs == 500
    
def test_monte_carlo_perturbation():
    goal = "[DC TARGET: 5.0V] [MONTE CARLO: 1]"
    designer = AutonomousDesigner(target_goal=goal, llm=get_provider("stub"))
    
    base_netlist = """* Test Netlist
V1 in 0 10
R1 in out 10k
C1 out 0 100u"""
    
    perturbed = designer._perturb_netlist(base_netlist)
    
    # Ensure it's not strictly equal (due to Gaussian randomness)
    # But structurally sound
    assert base_netlist != perturbed
    assert "V1 in 0 10" in perturbed # V should not be perturbed
    assert "10k" not in perturbed # R1 should be perturbed
    assert "100u" not in perturbed # C1 should be perturbed
    assert "R1 in out" in perturbed
    assert "C1 out 0" in perturbed
