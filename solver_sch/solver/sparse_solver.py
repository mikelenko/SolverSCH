"""
sparse_solver.py -> The Numerical Solvency Layer.

Strict Rules:
- Mathematical purity. Complete isolation from electrical abstractions.
- Operates SOLELY on general sparse matrices A and dense vector z.
- Receives A (usually heavily fragmented LIL structures), converts them to CSR
  (Compressed Sparse Row) and uses optimal solver spsolve from sparse.linalg.
- Parses the mathematical raw vector into structured human-readable/API results.
"""
import time
from typing import Dict, Optional, Callable, Tuple, List, Union
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse import lil_matrix, csr_matrix
import scipy.sparse.linalg as splalg
import scipy.sparse.linalg as splalg
from scipy.sparse.linalg import spsolve
import logging

logger = logging.getLogger("solver_sch.solver.sparse_solver")


@dataclass
class MNAResult:
    """Structured container for the solved MNA variables."""
    node_voltages: Dict[str, float]
    voltage_source_currents: Dict[str, float]
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

    def solve(self) -> MNAResult:
        """Solves the Ax = z system numerically using Sparse Newton-Raphson NR loop.
        
        Steps:
        1. Initialize `x` vector purely with zeros (initial guess).
        2. Iterate (max 50) NR loops cloning base A_lil and z_vec.
        3. Call inject stamper_nonlinear(A_clone, z_clone, x_prev) to update companion models.
        4. Convert purely to CSR format (`tocsr()`) and solve numerical equation.
        5. Verify local convergence to 1e-6 delta max.
        
        Returns:
            MNAResult datastructure containing mapped float voltages and currents.
        """
        size = self.A_lil.shape[0]
        if size == 0:
            return MNAResult({}, {})

        max_iter = 100
        tol = 1e-6
        x = np.zeros(size, dtype=float)

        # Non-Linear Newton Raphson Loop
        A_base_csr = self.A_lil.tocsr()
        z_base = self.z_vec.copy()
        A_csr = A_base_csr # Initialize for scope
        
        for i in range(max_iter):
            # 1. Ask Builder to dynamically inject Diode companion models 
            # Output mathematically returned as highly optimized independent CSR + dense numpy vectors
            if self.stamper_nonlinear is not None:
                A_nl, z_nl = self.stamper_nonlinear(x)
                # O(1) ultra-fast sparse algebra overriding O(N^2) clone+mutation
                A_csr = A_base_csr + A_nl
                z_iter = z_base + z_nl
            else:
                A_csr = A_base_csr
                z_iter = z_base
            
            # 2. Numerically solve x_new = inv(A)*z
            # Inject Gmin to guarantee diagonal dominance and prevent singularities
            A_csr.setdiag(A_csr.diagonal() + 1e-12)
            x_new = spsolve(A_csr, z_iter)
            
            # 3. Assess convergence vector variance
            diff = np.max(np.abs(x_new - x))
            x = x_new
            
            if diff < tol:
                break
        else:
            logger.warning("Newton-Raphson did not converge after 100 iterations. Last diff: %.2e", diff)

        self.A_csr = A_csr 
        self.x_vec = x
        
        # Parse the raw vector into clean structures
        voltages: Dict[str, float] = {}
        currents: Dict[str, float] = {}
        
        # Parse node voltages
        for node, idx in self.node_to_idx.items():
            if idx == -1:
                voltages[node] = 0.0  # Ground is strictly 0V
            else:
                voltages[node] = float(self.x_vec[idx])
                
        # Parse voltage source currents
        for vsrc_name, idx in self.vsrc_to_idx.items():
            # MNA adds source currents after all n independent nodes
            k_idx = self.n + idx
            currents[vsrc_name] = float(self.x_vec[k_idx])
            
        return MNAResult(node_voltages=voltages, voltage_source_currents=currents)

    def simulate_transient(self, t_stop: float, dt: float) -> list[tuple[float, MNAResult]]:
        """Executes a Time-Domain (Transient) analysis using Backward Euler integration.
        
        Evaluates a nested loop architecture:
        - Outer Loop: Time progression from t=0 to t_stop stepping by dt.
        - Inner Loop: Newton-Raphson convergence per timestep for non-linear stabilization.
        
        Parameters:
            t_stop: Total simulation time in seconds.
            dt: Time delta step in seconds.
        """
        size = self.A_lil.shape[0]
        if size == 0:
            return []
            
        results = []
        # Initial condition (x_prev) assumed 0 for all nodes (discharged state)
        x_prev = np.zeros(size, dtype=float)
        
        # Max NR limits
        max_iter = 50
        tol = 1e-6
        
        # PERFORMANCE: A_trans basis is entirely independent of time integration variants.
        # Stamp `dt / L` and `C / dt` explicitly ONLY ONCE and extract the rigid CSR form.
        A_trans = self.A_lil.copy()
        if self.stamper_transient_basis is not None:
            self.stamper_transient_basis(A_trans, dt)
        
        A_trans_csr = A_trans.tocsr()
        
        t = 0.0
        while t <= t_stop:
            # Outer Loop (Time Step): 
            # Reconstruct pristine RHS excitation array iteratively relying onto memory inputs.
            z_trans = self.z_vec.copy()
            
            # Step variables fetching (Ieq histories)
            if self.stamper_transient_sources is not None:
                self.stamper_transient_sources(z_trans, dt, x_prev)
                
            # AC Source inputs rendering
            if self.stamper_dynamic is not None:
                self.stamper_dynamic(z_trans, t)
            
            # Start Newton-Raphson prediction with previous state as guess
            x_guess = x_prev.copy()
            
            # Inner Loop (NR Solver): Resolve nonlinearities mathematically against rigid basis
            for i in range(max_iter):
                if self.stamper_nonlinear is not None:
                    A_nl, z_nl = self.stamper_nonlinear(x_guess)
                    # Isolated Sparse Matrix Addition (CSR + CSR form Scipy)
                    A_csr = A_trans_csr + A_nl
                    z_iter = z_trans + z_nl
                else:
                    A_csr = A_trans_csr
                    z_iter = z_trans
                    
                # Inject Gmin to prevent singular matrices from floating nodes/cutoff
                A_csr.setdiag(A_csr.diagonal() + 1e-12)
                x_new = spsolve(A_csr, z_iter)
                
                diff = np.max(np.abs(x_new - x_guess))
                x_guess = x_new
                
                if diff < tol:
                    break
            else:
                logger.warning("NR did not converge at t=%.5f", t)
            
            # Finalize numerical timestep states
            x_prev = x_guess
            
            # CRITICAL DOMAIN DELEGATION: Update component physics (Internal Resonances / Charge memory)
            if self.stamper_update_states is not None:
                self.stamper_update_states(x_prev, dt)
            
            # Map mathematically derived values to structured MNAResult object
            voltages: Dict[str, float] = {}
            currents: Dict[str, float] = {}
            
            for node, idx in self.node_to_idx.items():
                voltages[node] = 0.0 if idx == -1 else float(x_prev[idx])
                    
            for vsrc_name, idx in self.vsrc_to_idx.items():
                k_idx = self.n + idx
                currents[vsrc_name] = float(x_prev[k_idx])
                
            mna_res = MNAResult(node_voltages=voltages, voltage_source_currents=currents)
            mna_res.x_converged = x_prev
            results.append((t, mna_res))
            
            t += dt
            
        return results

    def simulate_ac(self, f_start: float | List[float] = 1.0, f_stop: float = 1e6, 
                    points_per_decade: int = 10, stamper_ref: Optional[any] = None) -> Union[Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray]], List[Tuple[float, MNAResult]]]:
        """Performs a logarithmic AC frequency sweep OR a list-based point analysis.
        
        Args:
            f_start: Starting frequency (float) OR a list of frequencies to analyze.
            f_stop: Ending frequency in Hz (if f_start is float).
            points_per_decade: Logarithmic density (if f_start is float).
            stamper_ref: A reference to the MNAStamper instance.
            
        Returns:
            If sweep: (freqs_array, magnitudes_db_dict, phases_deg_dict)
            If list: List[Tuple[float, MNAResult]]
        """
        callback = stamper_ref.stamp_ac if stamper_ref else getattr(self, 'stamper_ac', None)
        if callback is None:
            raise ValueError("AC Analysis requires an AC stamper callback (via stamper_ref or set_ac_stamper).")

        is_list_mode = isinstance(f_start, (list, np.ndarray))
        
        if is_list_mode:
            freqs = np.array(f_start)
        else:
            # 1. Generate Logarithmic Frequency Points
            num_decades = np.log10(f_stop) - np.log10(f_start)
            num_points = int(num_decades * points_per_decade) + 1
            freqs = np.logspace(np.log10(f_start), np.log10(f_stop), num_points)
        
        num_points = len(freqs)
        nodes = [node for node, idx in self.node_to_idx.items() if idx >= 0]
        
        # Results structures for Sweep Mode
        mags_db: Dict[str, np.ndarray] = {node: np.zeros(num_points) for node in nodes}
        phases_deg: Dict[str, np.ndarray] = {node: np.zeros(num_points) for node in nodes}
        
        # Results structure for List Mode
        list_results: List[Tuple[float, MNAResult]] = []
        
        logger.debug("[AC Analysis] Analyzing %d points...", num_points)
        
        for idx, freq in enumerate(freqs):
            # Formulate Complex Linear Matrix for this frequency
            A_ac_lil, z_ac_np = callback(freq)
            
            # Convert and solve
            A_ac_csr = A_ac_lil.tocsr()
            # Gmin for stability
            A_ac_csr.setdiag(A_ac_csr.diagonal() + 1e-12)
            
            try:
                x_ac = splalg.spsolve(A_ac_csr, z_ac_np)
                if len(x_ac.shape) > 1:
                    x_ac = x_ac.flatten()
            except Exception:
                x_ac = np.zeros(self.A_lil.shape[0], dtype=np.complex128)
            
            if is_list_mode:
                voltages: Dict[str, complex] = {}
                currents: Dict[str, complex] = {}
                for node, n_idx in self.node_to_idx.items():
                    voltages[node] = complex(x_ac[n_idx]) if n_idx >= 0 else 0j
                for vsrc_name, v_idx in self.vsrc_to_idx.items():
                    currents[vsrc_name] = complex(x_ac[self.n + v_idx])
                
                mna_res = MNAResult(node_voltages=voltages, voltage_source_currents=currents)
                mna_res.x_converged = x_ac # Ad-hoc injection for RLC tests
                list_results.append((freq, mna_res))
            else:
                # Extract Mag/Phase for all nodes
                for node in nodes:
                    n_idx = self.node_to_idx[node]
                    val = x_ac[n_idx]
                    mags_db[node][idx] = 20 * np.log10(max(np.abs(val), 1e-20))
                    phases_deg[node][idx] = np.degrees(np.angle(val))
                    
        if is_list_mode:
            return list_results
        return freqs, mags_db, phases_deg
