"""
solver_sch — Python-native EDA Circuit Simulator

Clean public API for LLMs and developers.

QUICKSTART:

    from solver_sch import Circuit, Resistor, Capacitor, Simulator

    circuit = Circuit("RC Low-Pass Filter")
    circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000))
    circuit.add_component(Resistor("R1", "in", "out", 1000))
    circuit.add_component(Capacitor("C1", "out", "0", 1e-6))

    sim = Simulator(circuit)
    ac  = sim.ac(f_start=10, f_stop=100e3)
    print(ac.to_json())

DISCOVERY:

    from solver_sch import available_components, available_analyses
    print(available_components())   # All component schemas
    print(available_analyses())     # All simulation methods
"""

# ── Domain Model ──────────────────────────────────────────────────
from solver_sch.model.circuit import (
    Circuit,
    Component,
    Resistor,
    Capacitor,
    Inductor,
    VoltageSource,
    ACVoltageSource,
    Diode,
    BJT,
    MOSFET_N,
    MOSFET_P,
    OpAmp,
    Comparator,
    # Aliases
    NMOS,
    PMOS,
    NPN,
)

# ── High-Level Facade ─────────────────────────────────────────────
from solver_sch.simulator import Simulator

# ── JSON-Serializable Results ─────────────────────────────────────
from solver_sch.results import (
    DcAnalysisResult,
    AcAnalysisResult,
    AcAnalysisResult as AcResult,
    TransientAnalysisResult,
    TransientAnalysisResult as TransientResult,
    NodeAcResult,
    ValidationResult,
    CircuitValidationError,
    ValidationError,
)

# ── Discovery / Registry ──────────────────────────────────────────
from solver_sch.registry import (
    available_components,
    available_analyses,
    component_help,
    COMPONENT_REGISTRY,
    get_component_classes,
)

__all__ = [
    # Domain model
    "Circuit", "Component",
    "Resistor", "Capacitor", "Inductor",
    "VoltageSource", "ACVoltageSource",
    "Diode", "BJT", "MOSFET_N", "MOSFET_P", "NMOS", "PMOS", "NPN",
    "OpAmp", "Comparator",
    # Facade
    "Simulator",
    # Results
    "DcAnalysisResult",
    "AcAnalysisResult", "AcResult",
    "TransientAnalysisResult", "TransientResult",
    "NodeAcResult",
    "ValidationResult",
    "CircuitValidationError",
    # Discovery
    "available_components",
    "available_analyses",
    "component_help",
    "COMPONENT_REGISTRY",
    "get_component_classes",
]
