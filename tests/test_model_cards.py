import pytest
import os
from solver_sch.model.circuit import Circuit, Diode, BJT, MOSFET_N, ModelCard
from solver_sch.utils.exporter import LTspiceExporter

def test_model_cards_export(tmp_path):
    """Verifies that ModelCards are registered and correctly exported by LTspiceExporter."""
    circuit = Circuit("Test Model Cards")
    
    # 1. Register a custom ModelCard
    diode_model = ModelCard("1N4148", "D", {"Is": "2.52n", "Rs": "0.568", "N": "1.752", "Cjo": "4p", "M": "0.4", "tt": "20n"})
    circuit.add_model(diode_model)
    
    bjt_model = ModelCard("2N3904", "NPN", {"Is": "1e-14", "Bf": "300", "Vaf": "100", "Ise": "1e-14"})
    circuit.add_model(bjt_model)

    # 2. Assign models to components
    d1 = Diode("1", "node1", "0", model="1N4148")
    d2 = Diode("2", "node2", "0") # Fallback
    
    q1 = BJT("1", "col", "base", "0", model="2N3904")
    q2 = BJT("2", "col", "base2", "0") # Fallback
    
    m1 = MOSFET_N("1", "drain", "gate", "0", model="IRF540N") # A model from external lib or to be defined
    
    circuit.add_component(d1)
    circuit.add_component(d2)
    circuit.add_component(q1)
    circuit.add_component(q2)
    circuit.add_component(m1)
    
    # 3. Export and verify
    export_path = os.path.join(tmp_path, "test_models.cir")
    LTspiceExporter.export(circuit, export_path, analysis="op")
    
    with open(export_path, "r", encoding="ascii") as f:
        content = f.read()

    # Verify component instantiate lines
    assert "D1 node1 0 1N4148" in content, "Diode with designated model not exported correctly."
    assert "D2 node2 0 D_MODEL" in content, "Diode without model did not use fallback D_MODEL."
    assert "Q1 col base 0 2N3904" in content, "BJT with designated model not exported correctly."
    assert "Q2 col base2 0 NPN_MODEL" in content, "BJT without model did not use fallback NPN_MODEL."
    assert "M1 drain gate 0 0 IRF540N" in content, "MOSFET with designated model not exported correctly."
    
    # Verify .model directives
    assert ".model 1N4148 D(Is=2.52n Rs=0.568 N=1.752 Cjo=4p M=0.4 tt=20n)" in content, "ModelCard directive for Diode missing or incorrect."
    assert ".model 2N3904 NPN(Is=1e-14 Bf=300 Vaf=100 Ise=1e-14)" in content, "ModelCard directive for BJT missing or incorrect."
