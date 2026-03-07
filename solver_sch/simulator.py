"""
simulator.py -> High-level Simulator facade for SolverSCH.

This is the PRIMARY entry point for LLMs and API consumers.
Hides all MNA complexity behind a clean, one-liner interface.

Usage:
    from solver_sch import Simulator, Circuit, Resistor, Capacitor

    circuit = Circuit("RC Filter")
    circuit.add_component(...)

    sim = Simulator(circuit)
    dc  = sim.dc()
    ac  = sim.ac(f_start=100, f_stop=100e3)
    tr  = sim.transient(t_stop=5e-3, dt=10e-6)
    sim.report("output/report.xlsx")

All methods return JSON-serializable result objects with .to_dict() and .to_json().
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Union

import numpy as np

from solver_sch.model.circuit import Circuit
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.results import (
    AcAnalysisResult,
    DcAnalysisResult,
    NodeAcResult,
    TransientAnalysisResult,
    TransientTimepoint,
    ValidationResult,
    ValidationError,
    CircuitValidationError,
)

logger = logging.getLogger("solver_sch.simulator")


class Simulator:
    """High-level, LLM-friendly interface to SolverSCH simulation.

    Wraps MNAStamper and SparseSolver behind a single class.
    All methods return JSON-serializable result objects.

    Args:
        circuit: A configured Circuit object with components.
        validate_on_init: If True (default), validate the circuit on creation
                          and raise CircuitValidationError for fatal issues.

    Example:
        sim = Simulator(circuit)
        ac_result = sim.ac(f_start=100, f_stop=100e3)
        print(ac_result.to_json())
    """

    def __init__(self, circuit: Circuit, validate_on_init: bool = True, backend: str = "auto") -> None:
        self.circuit = circuit
        self._stamper: Optional[MNAStamper] = None
        self._solver: Optional[SparseSolver] = None
        self.backend = backend
        
        # Decide active backend based on complexity
        if backend == "auto":
            from solver_sch.model.circuit import Diode, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator
            has_nonlinear = any(isinstance(c, (Diode, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator)) 
                                for c in self.circuit.get_components())
            self.active_backend = "ltspice" if has_nonlinear else "mna"
        else:
            self.active_backend = backend

        if validate_on_init:
            validation = circuit.validate()
            if not validation.valid:
                validation.raise_if_invalid()
            for w in validation.warnings:
                logger.warning("[Circuit Warning] %s", w.message)

    # ── Internal ──────────────────────────────────────────────────

    def _build(self) -> None:
        """Lazily compile MNA matrices. Called once on first analysis."""
        if self._stamper is not None:
            return

        logger.debug("Building MNA matrices for circuit '%s'", self.circuit.name)
        
        # Map SPICE ModelCard parameters to numerical values in internal components
        from solver_sch.model.circuit import Diode, BJT, MOSFET_N, MOSFET_P
        from solver_sch.parser.netlist_parser import NetlistParser
        
        models = self.circuit.get_models()
        for comp in self.circuit.get_components():
            if hasattr(comp, "model") and getattr(comp, "model") in models:
                mc = models[comp.model]
                # Combine ModelCard parameters with individual component overrides
                merged_params = {k.lower(): v for k, v in mc.parameters.items()}
                merged_params.update({k.lower(): v for k, v in getattr(comp, "spice_params", {}).items()})
                
                def parse_val(v):
                    if isinstance(v, str):
                        try: return NetlistParser._parse_value(v)
                        except Exception: return v
                    return v
                    
                if isinstance(comp, Diode):
                    if "is" in merged_params: comp.Is = parse_val(merged_params["is"])
                    if "n" in merged_params: comp.n = parse_val(merged_params["n"])
                    if "bv" in merged_params: comp.Vz = parse_val(merged_params["bv"])
                elif isinstance(comp, BJT):
                    if "is" in merged_params: comp.Is = parse_val(merged_params["is"])
                    if "bf" in merged_params: comp.Bf = parse_val(merged_params["bf"])
                    if "br" in merged_params: comp.Br = parse_val(merged_params["br"])
                elif isinstance(comp, (MOSFET_N, MOSFET_P)):
                    if "vto" in merged_params: comp.v_th = parse_val(merged_params["vto"])
                    if "kp" in merged_params: comp.k_p = parse_val(merged_params["kp"])
                    if "lambda" in merged_params: comp.lambda_ = parse_val(merged_params["lambda"])

        self._stamper = MNAStamper(self.circuit)
        A_lil, z_vec = self._stamper.stamp_linear()

        self._solver = SparseSolver(
            A_lil, z_vec,
            self._stamper.node_to_idx,
            self._stamper.vsrc_to_idx,
            self._stamper.n,
        )
        self._solver.set_nonlinear_stamper(self._stamper.stamp_nonlinear)
        self._solver.set_ac_stamper(self._stamper.stamp_ac)
        self._solver.set_transient_stampers(
            self._stamper.stamp_transient_basis,
            self._stamper.stamp_transient_sources,
            self._stamper.update_states,
        )
        self._solver.set_dynamic_stamper(self._stamper.stamp_dynamic_sources)

    # ── Public API ────────────────────────────────────────────────

    def dc(self) -> DcAnalysisResult:
        """Run DC operating point analysis.

        Returns:
            DcAnalysisResult with node voltages and source currents.

        Example:
            result = sim.dc()
            print(result.to_json())
            v_out = result.node_voltages["out"]
        """
        if self.active_backend == "ltspice":
            from solver_sch.utils.ltspice_runner import LTspiceRunner
            import os
            os.makedirs("ltspice_sim", exist_ok=True)
            voltages, currents = LTspiceRunner.run_dc(self.circuit, workdir="ltspice_sim")
            return DcAnalysisResult(
                node_voltages=voltages,
                source_currents=currents,
            )

        self._build()
        raw = self._solver.solve()
        return DcAnalysisResult(
            node_voltages=dict(raw.node_voltages),
            source_currents=dict(raw.voltage_source_currents),
        )

    def ac(
        self,
        f_start: float = 100.0,
        f_stop: float = 100e3,
        points_per_decade: int = 10,
    ) -> AcAnalysisResult:
        """Run AC frequency sweep analysis.

        Args:
            f_start: Starting frequency in Hz. Default: 100 Hz.
            f_stop: Ending frequency in Hz. Default: 100 kHz.
            points_per_decade: Number of logarithmically-spaced points per decade. Default: 10.

        Returns:
            AcAnalysisResult with magnitude [V], [dB] and phase [°] for each node.

        Example:
            result = sim.ac(f_start=1, f_stop=1e6)
            print(result.to_json())
            at_1khz = result.at_frequency(1000)
            v_out_db = at_1khz["out"]["magnitude_dB"]
        """
        if self.active_backend == "ltspice":
            from solver_sch.utils.ltspice_runner import LTspiceRunner
            import os
            os.makedirs("ltspice_sim", exist_ok=True)
            lt_freqs, lt_ac = LTspiceRunner.run_ac(self.circuit, f_start=f_start, f_stop=f_stop, points=points_per_decade, workdir="ltspice_sim")
            
            node_results = {}
            for node, cmplx_vals in lt_ac.items():
                mags = [abs(v) for v in cmplx_vals]
                dbs = [20 * np.log10(max(m, 1e-20)) for m in mags]
                phases = [float(np.degrees(np.angle(v))) for v in cmplx_vals]
                node_results[node] = NodeAcResult(node=node, magnitude=mags, magnitude_db=dbs, phase_deg=phases)
                
            return AcAnalysisResult(
                frequencies=lt_freqs,
                nodes=node_results,
                f_start=f_start,
                f_stop=f_stop,
            )

        self._build()

        num_decades = np.log10(f_stop / f_start)
        num_points = int(num_decades * points_per_decade) + 1
        freqs = np.logspace(np.log10(f_start), np.log10(f_stop), num_points)

        raw_results = self._solver.simulate_ac(
            f_start=freqs.tolist(),
            stamper_ref=self._stamper,
        )

        # Collect node names (skip ground)
        _, first_mna = raw_results[0]
        node_names = sorted([
            n for n in first_mna.node_voltages
            if n != self.circuit.ground_name
        ])

        # Build per-node arrays
        node_results: dict[str, NodeAcResult] = {}
        for node in node_names:
            mags, dbs, phases = [], [], []
            for _, mna_res in raw_results:
                v = mna_res.node_voltages.get(node, 0)
                mag = abs(v)
                mags.append(mag)
                dbs.append(20 * np.log10(max(mag, 1e-20)))
                phases.append(float(np.degrees(np.angle(v))))
            node_results[node] = NodeAcResult(node=node, magnitude=mags, magnitude_db=dbs, phase_deg=phases)

        return AcAnalysisResult(
            frequencies=[f for f, _ in raw_results],
            nodes=node_results,
            f_start=f_start,
            f_stop=f_stop,
        )

    def transient(
        self,
        t_stop: float = 5e-3,
        dt: float = 10e-6,
    ) -> TransientAnalysisResult:
        """Run time-domain (transient) simulation.

        Args:
            t_stop: Total simulation time in seconds. Default: 5 ms.
            dt: Time step in seconds. Default: 10 µs.

        Returns:
            TransientAnalysisResult with timestep-by-timestep node voltages.

        Example:
            result = sim.transient(t_stop=10e-3, dt=5e-6)
            out_signal = result.voltages_at("out")  # {"time": [...], "voltage": [...]}
        """
        if self.active_backend == "ltspice":
            from solver_sch.utils.ltspice_runner import LTspiceRunner
            import os
            os.makedirs("ltspice_sim", exist_ok=True)
            times, tr_results = LTspiceRunner.run_transient(self.circuit, t_stop=t_stop, t_step=dt, workdir="ltspice_sim")
            
            timepoints = []
            for i, t in enumerate(times):
                node_v = {n: float(vals[i]) for n, vals in tr_results.items() if n != self.circuit.ground_name}
                timepoints.append(TransientTimepoint(time=float(t), node_voltages=node_v))
                
            return TransientAnalysisResult(
                timepoints=timepoints,
                t_stop=t_stop,
                dt=dt,
            )

        self._build()

        raw_results = self._solver.simulate_transient(t_stop, dt)
        timepoints = [
            TransientTimepoint(
                time=t,
                node_voltages={
                    node: v for node, v in mna_res.node_voltages.items()
                    if node != self.circuit.ground_name
                }
            )
            for t, mna_res in raw_results
        ]

        return TransientAnalysisResult(
            timepoints=timepoints,
            t_stop=t_stop,
            dt=dt,
        )

    def report(
        self,
        filepath: str,
        analyses: Optional[List[str]] = None,
        ac_params: Optional[dict] = None,
        transient_params: Optional[dict] = None,
        ltspice_results: Optional[dict] = None,
        auto_open: bool = True,
    ) -> str:
        """Generate a full multi-sheet Excel report.

        Args:
            filepath: Path to save the .xlsx file.
            analyses: List of analyses to include. Options: "summary", "dc", "ac", "transient", "bom".
                      Defaults to all.
            ac_params: Dict with "f_start", "f_stop", "ppd" keys.
            transient_params: Dict with "t_stop", "dt" keys.
            ltspice_results: (Optional) Output from compare_with_ltspice() to include a diff sheet.
            auto_open: Automatically open the file after generation.

        Returns:
            Absolute path to the generated .xlsx file.
        """
        from solver_sch.utils.excel_report import ExcelReportGenerator
        gen = ExcelReportGenerator(self.circuit, ltspice_results=ltspice_results)
        return gen.generate(filepath, analyses=analyses, ac_params=ac_params,
                            transient_params=transient_params, auto_open=auto_open)

    def validate(self) -> ValidationResult:
        """Validate the circuit before simulation.

        Returns:
            ValidationResult with .valid, .errors, and .warnings.

        Example:
            result = sim.validate()
            if not result.valid:
                print(result.to_json())
        """
        return self.circuit.validate()

    def info(self) -> dict:
        """Return a structured description of the circuit for LLM context.

        Returns:
            Dict with circuit name, ground, component list, and available analyses.
        """
        from solver_sch.registry import COMPONENT_REGISTRY
        nodes = sorted(self.circuit.get_unique_nodes())
        components = [
            {
                "ref": c.name,
                "type": type(c).__name__,
                "nodes": list(c.nodes()),
            }
            for c in self.circuit.get_components()
        ]
        return {
            "circuit_name": self.circuit.name,
            "ground_node": self.circuit.ground_name,
            "nodes": nodes,
            "components": components,
            "component_count": len(components),
            "available_analyses": ["dc", "ac", "transient"],
            "available_report_sheets": ["summary", "dc", "ac", "transient", "bom"],
        }
        
    def compare_with_ltspice(
        self,
        analyses: List[str] = ["dc", "ac"],
        tolerance_pct: float = 1.0,
        workdir: str = "ltspice_signoff",
        ac_params: Optional[dict] = None,
        transient_params: Optional[dict] = None
    ) -> Dict[str, 'ComparisonResult']:
        """Run SolverSCH and LTspice in parallel, then compare the results.
        
        Args:
            analyses: List of analyses to compare ("dc", "ac", "transient").
            tolerance_pct: Maximum allowed percentage difference for PASS.
            workdir: Directory to save LTspice intermediate files.
            ac_params: Parameters for AC sweep (f_start, f_stop, points).
            transient_params: Parameters for Transient analysis (t_stop, dt).
            
        Returns:
            Dictionary mapped by analysis type to ComparisonResult objects.
        """
        import os
        from solver_sch.utils.ltspice_runner import LTspiceRunner
        from solver_sch.utils.ltspice_comparator import LTspiceComparator
        
        os.makedirs(workdir, exist_ok=True)
        results = {}
        
        if "dc" in analyses:
            solver_dc = self.dc()
            ltspice_voltages, ltspice_currents = LTspiceRunner.run_dc(self.circuit, workdir=workdir)
            
            comp_dc = LTspiceComparator.compare_dc(solver_dc, ltspice_voltages, tolerance_pct=0.1)
            results["dc"] = comp_dc
            
        if "ac" in analyses:
            ac_settings = ac_params or {"f_start": 10, "f_stop": 100e3, "points_per_decade": 20}
            # MNA
            solver_ac = self.ac(**ac_settings)
            
            # LTspice
            f_start = ac_settings.get("f_start", 10)
            f_stop = ac_settings.get("f_stop", 100e3)
            pts = int(ac_settings.get("points_per_decade", 20))
            
            lt_freqs, lt_ac = LTspiceRunner.run_ac(
                self.circuit, f_start=f_start, f_stop=f_stop, points=pts, workdir=workdir
            )
            
            comp_ac = LTspiceComparator.compare_ac(solver_ac, lt_freqs, lt_ac, tolerance_pct=tolerance_pct)
            results["ac"] = comp_ac
            
        if "transient" in analyses:
            transient_settings = transient_params or {"t_stop": 5e-3, "dt": 10e-6}
            
            # MNA
            solver_tr = self.transient(**transient_settings)
            
            # LTspice
            t_stop = transient_settings.get("t_stop", 5e-3)
            dt = transient_settings.get("dt", 10e-6)
            
            lt_times, lt_tr = LTspiceRunner.run_transient(
                self.circuit, t_stop=t_stop, t_step=dt, workdir=workdir
            )
            
            comp_tr = LTspiceComparator.compare_transient(
                solver_tr.timepoints, lt_times, lt_tr, tolerance_pct=tolerance_pct
            )
            results["transient"] = comp_tr

        return results
