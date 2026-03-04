"""
results.py -> JSON-serializable wrappers for SolverSCH analysis outputs.

Allows LLMs and APIs to consume simulation results without knowing
the internal MNA matrix structure. All results are plain dicts/JSON.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NodeAcResult:
    """Frequency-domain result for a single node across all frequencies."""
    node: str
    magnitude: List[float]      # linear magnitude [V]
    magnitude_db: List[float]   # 20*log10(|V|) [dB]
    phase_deg: List[float]      # phase angle [degrees]

    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "magnitude_V": self.magnitude,
            "magnitude_dB": self.magnitude_db,
            "phase_deg": self.phase_deg,
        }


@dataclass
class AcAnalysisResult:
    """Complete AC sweep result — JSON-serializable."""
    frequencies: List[float]
    nodes: Dict[str, NodeAcResult]
    f_start: float
    f_stop: float

    def to_dict(self) -> dict:
        return {
            "analysis": "ac",
            "f_start_hz": self.f_start,
            "f_stop_hz": self.f_stop,
            "frequencies": self.frequencies,
            "nodes": {n: r.to_dict() for n, r in self.nodes.items()},
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def at_frequency(self, freq_hz: float) -> Dict[str, Dict[str, float]]:
        """Return all node values at the closest available frequency point.

        Args:
            freq_hz: Target frequency in Hz.

        Returns:
            Dict mapping node name → {"magnitude_V", "magnitude_dB", "phase_deg"}
        """
        import bisect
        idx = min(range(len(self.frequencies)),
                  key=lambda i: abs(self.frequencies[i] - freq_hz))
        return {
            node: {
                "magnitude_V": r.magnitude[idx],
                "magnitude_dB": r.magnitude_db[idx],
                "phase_deg": r.phase_deg[idx],
            }
            for node, r in self.nodes.items()
        }


@dataclass
class TransientTimepoint:
    """Single timestep in a transient simulation."""
    time: float
    node_voltages: Dict[str, float]

    def to_dict(self) -> dict:
        return {"time_s": self.time, "voltages": self.node_voltages}


@dataclass
class TransientAnalysisResult:
    """Complete time-domain (transient) simulation result — JSON-serializable."""
    timepoints: List[TransientTimepoint]
    t_stop: float
    dt: float

    def to_dict(self) -> dict:
        return {
            "analysis": "transient",
            "t_stop_s": self.t_stop,
            "dt_s": self.dt,
            "timepoints": [tp.to_dict() for tp in self.timepoints],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def voltages_at(self, node: str) -> Dict[str, List]:
        """Return time-series voltage for a specific node.

        Args:
            node: Node name (e.g. 'out', 'node_l').

        Returns:
            Dict with "time" and "voltage" lists.
        """
        return {
            "time": [tp.time for tp in self.timepoints],
            "voltage": [tp.node_voltages.get(node, 0.0) for tp in self.timepoints],
        }


@dataclass
class DcAnalysisResult:
    """DC operating point result — JSON-serializable."""
    node_voltages: Dict[str, float]
    source_currents: Dict[str, float]

    def to_dict(self) -> dict:
        return {
            "analysis": "dc",
            "node_voltages_V": self.node_voltages,
            "source_currents_A": self.source_currents,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class ValidationError:
    """A single circuit validation error or warning."""
    severity: str   # "error" | "warning"
    message: str
    component: Optional[str] = None

    def to_dict(self) -> dict:
        return {"severity": self.severity, "message": self.message, "component": self.component}


@dataclass
class ValidationResult:
    """Full result of Circuit.validate()."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def raise_if_invalid(self):
        """Raise CircuitValidationError if the circuit has errors."""
        if not self.valid:
            msgs = "\n".join(f"  [{e.severity.upper()}] {e.message}" for e in self.errors)
            raise CircuitValidationError(f"Circuit is invalid:\n{msgs}")


class CircuitValidationError(Exception):
    """Raised when Circuit.validate() finds fatal circuit errors."""
    pass
