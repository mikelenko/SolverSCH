"""
sparse_solver.py -> The Numerical Solvency Layer.

Strict Rules:
- Mathematical purity. Complete isolation from electrical abstractions.
- Operates SOLELY on general sparse matrices A and dense vector z.
- Receives A (usually heavily fragmented LIL structures), converts them to CSR
  (Compressed Sparse Row) and uses optimal solver spsolve from sparse.linalg.
- Parses the mathematical raw vector into structured human-readable/API results.
"""
from typing import Dict, Optional, Callable, Tuple, List, Union
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse import lil_matrix, csr_matrix
import scipy.sparse.linalg as splalg
from scipy.sparse.linalg import spsolve
import logging

from solver_sch.constants import GMIN, NR_MAX_ITER_DC, NR_MAX_ITER_TRANSIENT, NR_TOLERANCE

logger = logging.getLogger("solver_sch.solver.sparse_solver")


@dataclass
class MNAResult:
    """Structured container for the solved MNA variables."""
    node_voltages: Dict[str, float | complex]
    voltage_source_currents: Dict[str, float | complex]
    x_converged: Optional[np.ndarray] = None


class SparseSolver:
    """Mathematical linear system solver adapted for ultra-large sparsity patterns."""

    def __init__(
        self, 
        A_matrix: lil_matrix, 
        z_vector: np.ndarray,
        node_to_idx: Dict[str, int],
        vsrc_to_idx: Dict[str, int],
        n_independent_nodes: int
    ) -> None:
        """Inject generic mathematical problem representations.
        
        Parameters:
            A_matrix            : LIL matrix representing the system correlations (Usually NxN).
            z_vector            : Unidimensional dense array representing static force conditions.
            node_to_idx         : Dictionary mapping node names to array indices.
            vsrc_to_idx         : Dictionary mapping voltage sources to auxiliary array indices.
            n_independent_nodes : Total number of independent nodes (used as an offset for source currents).
        """
        self.A_lil = A_matrix
        self.z_vec = z_vector
        self.node_to_idx = node_to_idx
        self.vsrc_to_idx = vsrc_to_idx
        self.n = n_independent_nodes
        
        # To be computed during the solution phase optimally
        self.A_csr: csr_matrix | None = None
        self.x_vec: np.ndarray | None = None
        
        # Callback to inject non-linear dependencies
        self.stamper_nonlinear = None
        
        # Callback to inject linear AC frequency logic
        self.stamper_ac = None
        
        # Callbacks to inject transient derivatives & physics internal states
        self.stamper_transient_basis = None
        self.stamper_transient_sources = None
        self.stamper_update_states = None
        
        # Callback for AC time-bound continuous functions
        self.stamper_dynamic = None

    @staticmethod
    def _inject_gmin(A_csr, n: int) -> None:
        """Add GMIN to the node-portion diagonal to prevent singular matrices."""
        diag = A_csr.diagonal()
        diag[:n] += GMIN
        A_csr.setdiag(diag)

    def _build_mna_result(self, x_vec) -> "MNAResult":
        """Parse raw solution vector into structured MNAResult."""
        voltages = {node: (0.0 if idx == -1 else float(x_vec[idx]))
                    for node, idx in self.node_to_idx.items()}
        currents = {name: float(x_vec[self.n + idx])
                    for name, idx in self.vsrc_to_idx.items()}
        return MNAResult(node_voltages=voltages, voltage_source_currents=currents)

    def set_nonlinear_stamper(self, callback) -> None:
        """Inject the non-linear stamping algorithm via callback to maintain strict DB isolation."""
        self.stamper_nonlinear = callback

    def set_transient_stampers(self, basis_cb, sources_cb, update_states_cb) -> None:
        """Inject separated backward Euler stamping delegates.
        
        Resolves matrices cloning performance issues by keeping time constant physical bindings
        (Resistors, Capacitors Geq) completely untied from iterative history variables (Ieq).
        """
        self.stamper_transient_basis = basis_cb
        self.stamper_transient_sources = sources_cb
        self.stamper_update_states = update_states_cb

    def set_dynamic_stamper(self, callback) -> None:
        """Inject the dynamic time-varying source stamper via callback."""
        self.stamper_dynamic = callback
        
    def set_ac_stamper(self, callback) -> None:
        """Inject the Small-Signal Frequency representation builder."""
        self.stamper_ac = callback

    def _nr_converge(self, A_base_csr: csr_matrix, z_base: np.ndarray,
                     x_init: np.ndarray, max_iter: int, tol: float,
                     warn_context: str = "") -> np.ndarray:
        """Newton-Raphson iteration until convergence. Returns converged x vector."""
        x = x_init.copy()
        diff = np.inf
        for _ in range(max_iter):
            if self.stamper_nonlinear is not None:
                A_nl, z_nl = self.stamper_nonlinear(x)
                A_csr = A_base_csr + A_nl
                z_iter = z_base + z_nl
            else:
                A_csr = A_base_csr
                z_iter = z_base
            self._inject_gmin(A_csr, self.n)
            x_new = spsolve(A_csr, z_iter)
            diff = np.max(np.abs(x_new - x))
            x = x_new
            if diff < tol:
                return x
        logger.warning("NR did not converge%s. Last diff: %.2e", warn_context, diff)
        return x

    def solve(self) -> MNAResult:
        """Solves the Ax = z system using Sparse Newton-Raphson.

        Returns:
            MNAResult containing mapped node voltages and source currents.
        """
        size = self.A_lil.shape[0]
        if size == 0:
            return MNAResult({}, {})

        A_base_csr = self.A_lil.tocsr()
        z_base = self.z_vec.copy()
        self.x_vec = self._nr_converge(
            A_base_csr, z_base, np.zeros(size, dtype=float),
            NR_MAX_ITER_DC, NR_TOLERANCE,
            f" after {NR_MAX_ITER_DC} iterations"
        )
        return self._build_mna_result(self.x_vec)

    def simulate_transient(self, t_stop: float, dt: float) -> list[tuple[float, MNAResult]]:
        """Executes Time-Domain (Transient) analysis using Backward Euler integration.

        Parameters:
            t_stop: Total simulation time in seconds.
            dt: Time delta step in seconds.
        """
        size = self.A_lil.shape[0]
        if size == 0:
            return []

        # PERFORMANCE: stamp C/dt and L/dt basis ONCE, extract CSR
        A_trans = self.A_lil.copy()
        if self.stamper_transient_basis is not None:
            self.stamper_transient_basis(A_trans, dt)
        A_trans_csr = A_trans.tocsr()

        results = []
        # Initialize from DC operating point if available (proper initial conditions)
        if self.x_vec is not None:
            x_prev = self.x_vec.copy()
        else:
            x_prev = np.zeros(size, dtype=float)
        t = 0.0
        while t <= t_stop:
            z_trans = self.z_vec.copy()
            if self.stamper_transient_sources is not None:
                self.stamper_transient_sources(z_trans, dt, x_prev)
            if self.stamper_dynamic is not None:
                self.stamper_dynamic(z_trans, t)

            x_prev = self._nr_converge(
                A_trans_csr, z_trans, x_prev,
                NR_MAX_ITER_TRANSIENT, NR_TOLERANCE,
                f" at t={t:.5f}"
            )

            if self.stamper_update_states is not None:
                self.stamper_update_states(x_prev, dt)

            mna_res = self._build_mna_result(x_prev)
            mna_res.x_converged = x_prev
            results.append((t, mna_res))
            t += dt

        return results

    def _solve_single_ac_freq(self, freq: float, callback: Callable[[float], Tuple[sp.lil_matrix, np.ndarray]]) -> np.ndarray:
        """Core complex matrix solver for a single AC frequency point."""
        # Formulate Complex Linear Matrix for this frequency
        A_ac_lil, z_ac_np = callback(freq)
        
        # Convert and solve
        A_ac_csr = A_ac_lil.tocsr()
        self._inject_gmin(A_ac_csr, self.n)
        
        try:
            x_ac = splalg.spsolve(A_ac_csr, z_ac_np)
            if len(x_ac.shape) > 1:
                x_ac = x_ac.flatten()
            return x_ac
        except Exception as e:
            logger.error(f"Failed to solve AC at {freq} Hz: {e}")
            return np.zeros(self.A_lil.shape[0], dtype=np.complex128)

    def simulate_ac_sweep(self, f_start: float, f_stop: float, 
                          points_per_decade: int = 10, stamper_ref: Optional[object] = None) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray]]:
        """Performs a logarithmic AC frequency sweep, returning Bode plot data (Mag/Phase)."""
        callback = getattr(stamper_ref, 'stamp_ac', None) if stamper_ref else getattr(self, 'stamper_ac', None)
        if callback is None:
            raise ValueError("AC Analysis requires an AC stamper callback.")

        # 1. Generate Logarithmic Frequency Points
        num_decades = np.log10(f_stop) - np.log10(f_start)
        num_points = int(num_decades * points_per_decade) + 1
        freqs = np.logspace(np.log10(f_start), np.log10(f_stop), num_points)
        
        nodes = [node for node, idx in self.node_to_idx.items() if idx >= 0]
        mags_db: Dict[str, np.ndarray] = {node: np.zeros(num_points) for node in nodes}
        phases_deg: Dict[str, np.ndarray] = {node: np.zeros(num_points) for node in nodes}

        for idx, freq in enumerate(freqs):
            x_ac = self._solve_single_ac_freq(freq, callback)
            
            # Extract Mag/Phase for all nodes
            for node in nodes:
                n_idx = self.node_to_idx[node]
                val = x_ac[n_idx]
                mags_db[node][idx] = 20 * np.log10(max(np.abs(val), 1e-20))
                phases_deg[node][idx] = np.degrees(np.angle(val))
                
        return freqs, mags_db, phases_deg

    def simulate_ac_discrete(self, frequencies: List[float], 
                             stamper_ref: Optional[object] = None) -> List[Tuple[float, MNAResult]]:
        """Performs AC analysis at discrete frequency points, returning structured results."""
        callback = getattr(stamper_ref, 'stamp_ac', None) if stamper_ref else getattr(self, 'stamper_ac', None)
        if callback is None:
            raise ValueError("AC Analysis requires an AC stamper callback.")

        results: List[Tuple[float, MNAResult]] = []

        for freq in frequencies:
            x_ac = self._solve_single_ac_freq(freq, callback)
            
            voltages: Dict[str, complex] = {}
            currents: Dict[str, complex] = {}
            for node, n_idx in self.node_to_idx.items():
                voltages[node] = complex(x_ac[n_idx]) if n_idx >= 0 else 0j
            for vsrc_name, v_idx in self.vsrc_to_idx.items():
                currents[vsrc_name] = complex(x_ac[self.n + v_idx])
            
            mna_res = MNAResult(node_voltages=voltages, voltage_source_currents=currents)
            mna_res.x_converged = x_ac
            results.append((freq, mna_res))
            
        return results

