import pytest
from solver_sch.ai.auto_designer import AutonomousDesigner

def test_pareto_parsing_logic():
    goal = "[DC TARGET: 5.0V] [MAX CURRENT: 10.0mA] Zaprojektuj dzielnik"
    designer = AutonomousDesigner(target_goal=goal)
    
    assert designer.sim_mode == 'DC'
    assert designer.target_dc_voltage == 5.0
    assert designer.target_max_current_ma == 10.0

def test_regular_dc_parsing_logic():
    goal = "[DC TARGET: 12.0V] Zaprojektuj"
    designer = AutonomousDesigner(target_goal=goal)
    
    assert designer.sim_mode == 'DC'
    assert designer.target_dc_voltage == 12.0
    assert designer.target_max_current_ma is None
