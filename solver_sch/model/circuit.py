"""
circuit.py -> Core Domain Model (Physical Representation).

Strict Rules:
- This module must represent the real-world connectivity of an electrical circuit.
- NO arrays, NO matrices, NO numerical solvers, NO numpy, NO scipy dependencies.

Component classes have been extracted to components.py.
This module re-exports them for full backward compatibility.
"""

from collections import Counter
from typing import Dict, List, Set

from solver_sch.model.components import (
    Component, TwoTerminalPassive, ThreeTerminalActive,
    ModelCard, Resistor, VoltageSource, CurrentSource, ACVoltageSource,
    Capacitor, Inductor, Diode, _BJTBase, BJT, BJT_N, BJT_P,
    MOSFET_N, MOSFET_P,
    OpAmp, Comparator, NMOS, PMOS, NPN, PNP, LM5085Gate,
)

__all__ = [
    "Circuit",
    "Component", "TwoTerminalPassive", "ThreeTerminalActive",
    "ModelCard",
    "Resistor", "VoltageSource", "CurrentSource", "ACVoltageSource",
    "Capacitor", "Inductor", "Diode",
    "BJT", "BJT_N", "BJT_P", "_BJTBase",
    "MOSFET_N", "MOSFET_P", "OpAmp", "Comparator",
    "NMOS", "PMOS", "NPN", "PNP", "LM5085Gate",
]


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

        node_count: Counter = Counter()
        for comp in self._components:
            for node in comp.nodes():
                node_count[node] += 1
        for node, count in node_count.items():
            if node != self.ground_name and count < 2:
                warnings.append(ValidationError("warning", f"Node '{node}' is only connected to 1 component — may be floating."))

        valid = len(errors) == 0
        return ValidationResult(valid=valid, errors=errors, warnings=warnings)

    def apply_models(self) -> None:
        """Merge registered ModelCard parameters into component instances."""
        from solver_sch.parser.netlist_parser import NetlistParser

        models = self._models
        for comp in self._components:
            if not (hasattr(comp, "model") and getattr(comp, "model") in models):
                continue
            mc = models[comp.model]
            merged = {k.lower(): v for k, v in mc.parameters.items()}
            merged.update({k.lower(): v for k, v in getattr(comp, "spice_params", {}).items()})

            def _parse(v):
                if isinstance(v, str):
                    try:
                        return NetlistParser._parse_value(v)
                    except Exception:
                        return v
                return v

            if isinstance(comp, Diode):
                if "is" in merged: comp.Is = _parse(merged["is"])
                if "n" in merged: comp.n = _parse(merged["n"])
                if "bv" in merged: comp.Vz = _parse(merged["bv"])
            elif isinstance(comp, _BJTBase):
                if "is" in merged: comp.Is = _parse(merged["is"])
                if "bf" in merged: comp.Bf = _parse(merged["bf"])
                if "br" in merged: comp.Br = _parse(merged["br"])
            elif isinstance(comp, (MOSFET_N, MOSFET_P)):
                if "vto" in merged: comp.v_th = _parse(merged["vto"])
                if "kp" in merged: comp.k_p = _parse(merged["kp"])
                if "lambda" in merged: comp.lambda_ = _parse(merged["lambda"])

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

