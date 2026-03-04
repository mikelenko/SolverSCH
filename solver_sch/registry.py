"""
registry.py -> Dynamic Component discovery registry for LLMs and API consumers.

Automatically discovers all components inside solver_sch.model.circuit
by inspecting subclasses of Component and analyzing their __init__ signatures
and docstrings.
"""

from __future__ import annotations
import inspect
import json
from typing import Dict, Any, Type

from solver_sch.model import circuit

# ── Dynamic Component Catalogue ────────────────────────────────────

def _build_component_registry() -> Dict[str, Dict[str, Any]]:
    """Dynamically builds the component registry using introspection."""
    registry = {}
    
    # Iterate over all elements in the circuit module
    for name, obj in inspect.getmembers(circuit, inspect.isclass):
        # We only care about subclasses of Component, excluding Component itself
        if issubclass(obj, circuit.Component) and obj is not circuit.Component:
            
            doc_string = inspect.getdoc(obj) or "No description provided."
            
            # Extract init signature parameters
            init_sig = inspect.signature(obj.__init__)
            params = []
            for param_name, param in init_sig.parameters.items():
                if param_name == 'self':
                    continue
                
                param_info = {"name": param_name}
                
                # Check type hint
                if param.annotation != inspect.Parameter.empty:
                    # simplistic string conversion for basic types
                    if param.annotation == float:
                        param_info["type"] = "float"
                    elif param.annotation == str:
                        param_info["type"] = "str"
                    elif param.annotation == int:
                        param_info["type"] = "int"
                    else:
                        param_info["type"] = str(param.annotation).replace("typing.", "")
                
                # Check default value
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default
                else:
                    param_info["description"] = "Required"
                
                params.append(param_info)
                
            # Create constructor signature string
            param_names = [p["name"] for p in params]
            # Try to build a nicer constructor string showing defaults
            constr_args = []
            for p in params:
                if "default" in p:
                    constr_args.append(f"{p['name']}={p['default']}")
                else:
                    constr_args.append(p["name"])
                    
            constructor_str = f"{name}({', '.join(constr_args)})"
                
            registry[name] = {
                "description": doc_string.split("\n\n")[0].strip(), # First paragraph
                "constructor": constructor_str,
                "parameters": params,
                "full_docstring": doc_string,
            }
            
    return registry

# Cache the dynamically built registry
COMPONENT_REGISTRY: Dict[str, Dict[str, Any]] = _build_component_registry()

def get_component_classes() -> Dict[str, Type]:
    """Returns a dictionary mapping component names to their actual classes.
    Useful for populating the isolated execution environment for LLMs.
    """
    classes = {}
    for name, obj in inspect.getmembers(circuit, inspect.isclass):
        if issubclass(obj, circuit.Component) and obj is not circuit.Component:
            classes[name] = obj
    return classes

# ── Available Analyses (Static) ────────────────────────────────────

AVAILABLE_ANALYSES = {
    "dc": {
        "description": "DC Operating Point. Solves steady-state node voltages and source currents.",
        "method": "sim.dc()",
        "returns": "DcAnalysisResult → .node_voltages, .source_currents, .to_json()",
    },
    "ac": {
        "description": "AC Frequency Sweep. Computes small-signal magnitude and phase across a frequency range.",
        "method": "sim.ac(f_start=100, f_stop=100e3, points_per_decade=10)",
        "returns": "AcAnalysisResult → .nodes, .frequencies, .at_frequency(f), .to_json()",
        "parameters": [
            {"name": "f_start", "default": 100.0, "unit": "Hz"},
            {"name": "f_stop", "default": 100e3, "unit": "Hz"},
            {"name": "points_per_decade", "default": 10},
        ],
    },
    "transient": {
        "description": "Time-Domain (Transient) simulation using Backward Euler integration.",
        "method": "sim.transient(t_stop=5e-3, dt=10e-6)",
        "returns": "TransientAnalysisResult → .timepoints, .voltages_at(node), .to_json()",
        "parameters": [
            {"name": "t_stop", "default": 5e-3, "unit": "s"},
            {"name": "dt", "default": 10e-6, "unit": "s"},
        ],
    },
}

def available_components() -> str:
    """Return a JSON string describing all available circuit components.

    Intended for LLM prompts / API discovery.

    Returns:
        JSON string with component names, parameters, descriptions, and examples.
    """
    return json.dumps(COMPONENT_REGISTRY, indent=2)

def available_analyses() -> str:
    """Return a JSON string describing all available simulation analyses.

    Returns:
        JSON string with analysis names, methods, parameters, and return types.
    """
    return json.dumps(AVAILABLE_ANALYSES, indent=2)

def component_help(component_name: str) -> str:
    """Return help text for a specific component.

    Args:
        component_name: Name of the component (e.g. 'Resistor', 'OpAmp').

    Returns:
        JSON string with the component schema, or error message if not found.
    """
    if component_name in COMPONENT_REGISTRY:
        return json.dumps(COMPONENT_REGISTRY[component_name], indent=2)
    return json.dumps({"error": f"Component '{component_name}' not found.", "available": list(COMPONENT_REGISTRY)})
