"""
circuit.py -> Core Domain Model (Physical Representation).

Strict Rules:
- This module must represent the real-world connectivity of an electrical circuit.
- NO arrays, NO matrices, NO numerical solvers, NO numpy, NO scipy dependencies.
"""

from abc import ABC, abstractmethod
import math
from typing import Any, List, Tuple, Dict, Optional, Set

class ModelCard:
    """A collection of physical simulation parameters for a specific component type.
    
    Mimics SPICE .MODEL cards. E.g., .MODEL 1N4148 D(Is=2.52n Rs=0.568 N=1.752 ...)
    """
    def __init__(self, name: str, model_type: str, parameters: Dict[str, Any]):
        self.name = name
        self.model_type = model_type  # e.g., 'D', 'NPN', 'PNP', 'NMOS', 'PMOS'
        self.parameters = parameters
        
    def __repr__(self) -> str:
        params_str = ' '.join(f"{k}={v}" for k, v in self.parameters.items())
        return f".model {self.name} {self.model_type}({params_str})"


class Component(ABC):
    """Abstract Base Class for an electronic circuit element."""

    def __init__(self, name: str) -> None:
        self.name: str = name

    @abstractmethod
    def nodes(self) -> Tuple[str, ...]:
        """Return the terminals to which this component is connected."""
        pass

    @property
    def value(self) -> float:
        """Default value for generic reporting/descriptions."""
        return 0.0


class TwoTerminalPassive(Component):
    """Base class for components with exactly two terminals and a primary numerical value."""
    
    def __init__(self, name: str, node1: str, node2: str, value: float) -> None:
        super().__init__(name)
        self.node1: str = node1
        self.node2: str = node2
        self._value: float = value

    def nodes(self) -> Tuple[str, str]:
        return self.node1, self.node2

    @property
    def value(self) -> float:
        return self._value


class ThreeTerminalActive(Component):
    """Base class for active components with three primary terminals (e.g. BJT, MOSFET)."""
    
    def __init__(self, name: str, term1: str, term2: str, term3: str) -> None:
        super().__init__(name)
        self.term1: str = term1
        self.term2: str = term2
        self.term3: str = term3

    def nodes(self) -> Tuple[str, str, str]:
        return self.term1, self.term2, self.term3


class Resistor(TwoTerminalPassive):
    """A linear resistor element (Passive)."""

    @property
    def resistance(self) -> float:
        return self.value


class VoltageSource(TwoTerminalPassive):
    """An independent ideal voltage source (Active)."""

    @property
    def voltage(self) -> float:
        return self.value


class CurrentSource(TwoTerminalPassive):
    """An independent ideal current source (Active).
    
    Current flows from node1 to node2 inside the source.
    """

    @property
    def current(self) -> float:
        return self.value


class ACVoltageSource(TwoTerminalPassive):
    """An independent ideal AC voltage source.
    
    Supports Time-Domain Sine sweeps and Small-Signal AC Frequency Domain magnitude/phase setups.
    """
    
    def __init__(self, name: str, node1: str, node2: str, amplitude: float, frequency: float, dc_offset: float = 0.0, ac_mag: float = 1.0, ac_phase: float = 0.0) -> None:
        # Base value is set to dc_offset for reporting
        super().__init__(name, node1, node2, dc_offset)
        # Time-domain parameters
        self.amplitude = amplitude
        self.frequency = frequency
        self.dc_offset = dc_offset
        # Small-Signal frequency domain parameters
        self.ac_mag = ac_mag
        self.ac_phase = ac_phase

    def get_voltage(self, t: float) -> float:
        """Returns the instantaneous voltage at time t using standard sine wave formula plus DC offset."""
        return self.dc_offset + self.amplitude * math.sin(2.0 * math.pi * self.frequency * t)

    @property
    def voltage(self) -> float:
        """Returns the DC offset for DC Operating Point stamping or initial transient state."""
        return self.dc_offset


class Diode(TwoTerminalPassive):
    """A non-linear PN junction diode.
    
    Using standard Shockley Diode equation parameters.
    """
    
    def __init__(
        self, 
        name: str, 
        anode: str, 
        cathode: str, 
        Is: float = 1e-14, 
        n: float = 1.0, 
        Vt: float = 0.02585,
        Vz: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        # Pass 0.0 as value - diodes are non-linear
        super().__init__(name, anode, cathode, 0.0)
        self.Is = Is
        self.n = n
        self.Vt = Vt
        self.Vz = Vz
        self.model = model
        self.spice_params = kwargs
        
    @property
    def anode(self) -> str:
        return self.node1
        
    @property
    def cathode(self) -> str:
        return self.node2


class Capacitor(TwoTerminalPassive):
    """A linear ideal capacitor element."""

    @property
    def capacitance(self) -> float:
        return self.value


class Inductor(TwoTerminalPassive):
    """An ideal inductor component for magnetic energy storage."""
    
    def __init__(self, name: str, node1: str, node2: str, inductance: float) -> None:
        super().__init__(name, node1, node2, inductance)
        self.inductance = inductance
        # Internal state history
        self.i_prev: float = 0.0
        
    @property
    def voltage(self) -> float:
        return 0.0 # Non-applicable, operates on transient Geq/Ieq


class BJT(ThreeTerminalActive):
    """An ideal NPN Bipolar Junction Transistor relying on Ebers-Moll injection model.
    
    Terminals: Collector, Base, Emitter.
    """
    
    def __init__(
        self, 
        name: str, 
        collector: str, 
        base: str, 
        emitter: str, 
        Is: float = 1e-14, 
        Bf: float = 100.0, 
        Br: float = 1.0, 
        Vt: float = 0.02585,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        super().__init__(name, collector, base, emitter)
        
        self.collector = collector
        self.base = base
        self.emitter = emitter
        
        # Physics Parameters Ebers-Moll Base
        self.Is = Is
        self.Bf = Bf
        self.Br = Br
        self.Vt = Vt
        self.model = model
        self.spice_params = kwargs

    @property
    def voltage(self) -> float:
        return 0.0


class MOSFET_N(ThreeTerminalActive):
    """Shichman-Hodges Level 1 NMOS Model."""
    
    def __init__(self, name: str, drain: str, gate: str, source: str,
                 w: float = 1e-6, l: float = 1e-6, 
                 v_th: float = 0.7, k_p: float = 250e-6, lambda_: float = 0.01,
                 model: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, drain, gate, source)
        self.gate = gate
        self.drain = drain
        self.source = source
        self.w = w
        self.l = l
        self.v_th = v_th
        self.k_p = k_p
        self.lambda_ = lambda_
        self.model = model
        self.spice_params = kwargs
        self.beta = self.k_p * (self.w / self.l)
        
    @property
    def voltage(self) -> float:
        return 0.0


class MOSFET_P(ThreeTerminalActive):
    """Shichman-Hodges Level 1 PMOS Model."""
    
    def __init__(self, name: str, drain: str, gate: str, source: str,
                 w: float = 1e-6, l: float = 1e-6, 
                 v_th: float = -0.7, k_p: float = 250e-6, lambda_: float = 0.01,
                 model: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, drain, gate, source)
        self.gate = gate
        self.drain = drain
        self.source = source
        self.w = w
        self.l = l
        self.v_th = v_th
        self.k_p = k_p
        self.lambda_ = lambda_
        self.model = model
        self.spice_params = kwargs
        self.beta = self.k_p * (self.w / self.l)
        
    @property
    def voltage(self) -> float:
        return 0.0


class OpAmp(ThreeTerminalActive):
    """An ideal Operational Amplifier acting as a linear VCVS (Voltage-Controlled Voltage Source).
    
    Terminals: Non-inverting (+), Inverting (-), Output.
    """
    
    def __init__(self, name: str, in_p: str, in_n: str, out: str, gain: float = 1e5) -> None:
        super().__init__(name, in_p, in_n, out) 
        self.in_p = in_p
        self.in_n = in_n
        self.out = out
        self.gain = gain
        
    @property
    def voltage(self) -> float:
        return 0.0


class Comparator(ThreeTerminalActive):
    """An ideal non-linear Comparator component.
    
    Terminals: Non-inverting (+), Inverting (-), Output.
    """
    
    def __init__(self, name: str, node_p: str, node_n: str, node_out: str, v_high: float = 5.0, v_low: float = 0.0, k: float = 1000.0) -> None:
        super().__init__(name, node_p, node_n, node_out) 
        self.node_p = node_p
        self.node_n = node_n
        self.node_out = node_out
        
        self.v_high = v_high
        self.v_low = v_low
        self.k = k
        
    @property
    def voltage(self) -> float:
        return 0.0


class Circuit:
    """The central netlist/container holding nodes and components."""

    def __init__(self, name: str = "EDA Circuit", ground_name: str = "0") -> None:
        self.name: str = name
        self.ground_name: str = ground_name
        self._components: List[Component] = []
        self._models: Dict[str, ModelCard] = {}

    def add_model(self, model: ModelCard) -> None:
        """Register a SPICE-like component model card."""
        self._models[model.name] = model

    def get_models(self) -> Dict[str, ModelCard]:
        """Return all registered model cards."""
        return self._models

    def add_component(self, comp: Component) -> None:
        """Register a new physical component into the network."""
        self._components.append(comp)

    def get_components(self) -> List[Component]:
        """Return a view of all registered components."""
        return self._components

    def get_unique_nodes(self) -> Set[str]:
        """Extract all unique node strings defined across all components."""
        nodes: Set[str] = set()
        for comp in self._components:
            nodes.update(comp.nodes())
        return nodes

    def validate(self):
        """Validate the circuit topology and component values."""
        from solver_sch.results import ValidationResult, ValidationError

        errors = []
        warnings = []

        seen_names: Dict[str, int] = {}
        for comp in self._components:
            seen_names[comp.name] = seen_names.get(comp.name, 0) + 1
        for name, count in seen_names.items():
            if count > 1:
                errors.append(ValidationError("error", f"Duplicate component name '{name}' appears {count} times."))

        for comp in self._components:
            if isinstance(comp, Resistor) and comp.resistance <= 0:
                errors.append(ValidationError("error", f"Resistor '{comp.name}' has invalid resistance={comp.resistance} Ω (must be > 0).", comp.name))
            if isinstance(comp, Capacitor) and comp.capacitance <= 0:
                errors.append(ValidationError("error", f"Capacitor '{comp.name}' has invalid capacitance={comp.capacitance} F (must be > 0).", comp.name))
            if isinstance(comp, Inductor) and comp.inductance <= 0:
                errors.append(ValidationError("error", f"Inductor '{comp.name}' has invalid inductance={comp.inductance} H (must be > 0).", comp.name))

        has_source = any(isinstance(c, (VoltageSource, ACVoltageSource)) for c in self._components)
        if not has_source:
            warnings.append(ValidationError("warning", "No voltage source found. DC solve may return all-zero voltages."))

        has_ac_source = any(isinstance(c, ACVoltageSource) for c in self._components)
        if not has_ac_source:
            warnings.append(ValidationError(
                "warning",
                "No ACVoltageSource found. AC sweep and transient analysis will return all-zero magnitudes (-400 dB). "
                "Add: ACVoltageSource('Vin', 'in', '0', amplitude=1.0, frequency=1000) to the circuit."
            ))

        all_nodes = self.get_unique_nodes()
        if self.ground_name not in all_nodes:
            errors.append(ValidationError("error", f"Ground node '{self.ground_name}' is not connected to any component."))

        from collections import Counter
        node_count: Counter = Counter()
        for comp in self._components:
            for node in comp.nodes():
                node_count[node] += 1
        for node, count in node_count.items():
            if node != self.ground_name and count < 2:
                warnings.append(ValidationError("warning", f"Node '{node}' is only connected to 1 component — may be floating."))

        valid = len(errors) == 0
        return ValidationResult(valid=valid, errors=errors, warnings=warnings)

    def describe(self) -> dict:
        """Return a structured human/LLM-readable description of the circuit."""
        return {
            "name": self.name,
            "ground": self.ground_name,
            "nodes": sorted(self.get_unique_nodes()),
            "components": [
                {
                    "ref": c.name,
                    "type": type(c).__name__,
                    "nodes": list(c.nodes()),
                    "value": c.value,
                }
                for c in self._components
            ]
        }

    def draw(self, filepath: str) -> bool:
        """Render the circuit into an SVG schematic using the netlistsvg engine."""
        from solver_sch.utils.svg_exporter import SVGExporter
        exporter = SVGExporter(self)
        try:
            return exporter.generate(filepath)
        except Exception as e:
            print(f"[Circuit Warning] Failed to draw schematic: {e}")
            return False

# Class Aliases for EDA Test Integrity
NMOS = MOSFET_N
PMOS = MOSFET_P
NPN = BJT
