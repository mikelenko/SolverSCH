"""
stamper.py -> The MNA Builder / Translation Layer.

Strict Rules:
- Maps the domain logic (Circuit) into the mathematical domain (Sparse Matrices).
- MUST use `scipy.sparse.lil_matrix` (List of Lists format) due to its O(1) 
  complexity for iterative structural mutations (incremental row/col modifications).
"""

from typing import Dict, Tuple, Callable

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix

from solver_sch.model.circuit import (
    Circuit, Resistor, VoltageSource, ACVoltageSource, CurrentSource, 
    Diode, Capacitor, Inductor, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator
)


class MNAStamper:
    """Algorithm layer allocating and stamping an MNA netlist into matrices.
    
    Generates sparse matrix `A` and dense column vector `z` such that A*x = z.
    """

    def __init__(self, circuit: Circuit) -> None:
        """Initialize the MNA Stamper with a given circuit.
        
        Args:
            circuit: The validated Circuit object containing components and nodes.
        """
        self.circuit: Circuit = circuit
        
        # Mappings
        self.node_to_idx: Dict[str, int] = {} # Maps independent node names to matrix indices
        self.vsrc_to_idx: Dict[str, int] = {} # Maps V-source names to independent branch equations
        self.vcvs_to_idx: Dict[str, int] = {} # Maps OpAmps names to branch equations
        
        # Matrix Dimensions
        self.n: int = 0  # Number of independent nodes
        self.m: int = 0  # Number of independent voltage sources + OpAmps
        
        self.size: int = 0
        
        # Core Matrix structures
        self.A_lil: lil_matrix | None = None
        self.z_vec: np.ndarray | None = None

        # OCP Registry for nonlinear components
        # Maps Component Type -> Handler method
        self._nl_stampers: Dict[type, Callable] = {
            Diode: self._stamp_diode_nl,
            Comparator: self._stamp_comparator_nl,
            BJT: self._stamp_bjt_nl,
            MOSFET_N: self._stamp_nmos_nl,
            MOSFET_P: self._stamp_pmos_nl,
        }

        self._map_nodes()

    def _map_nodes(self) -> None:
        """Assigns numerical array indices to electrical graph nodes and sources."""
        self.node_to_idx.clear()
        self.vsrc_to_idx.clear()
        self.vcvs_to_idx.clear()

        unique_nodes = self.circuit.get_unique_nodes()
        
        idx = 0
        for node in sorted(list(unique_nodes)):
            if node == self.circuit.ground_name:
                self.node_to_idx[node] = -1  # Ground row drops math entries
            else:
                self.node_to_idx[node] = idx
                idx += 1
                
        self.n = idx
        
        m_idx = 0
        for comp in self.circuit.get_components():
            if isinstance(comp, (VoltageSource, ACVoltageSource, Inductor)):
                self.vsrc_to_idx[comp.name] = m_idx
                m_idx += 1
            elif isinstance(comp, (OpAmp, Comparator)):
                self.vcvs_to_idx[comp.name] = m_idx
                m_idx += 1
                
        self.m = m_idx
        self.size = self.n + self.m

    def _allocate_memory(self) -> None:
        """Instantiate empty `lil_matrix` and right-hand side `ndarray` buffers."""
        self.A_lil = lil_matrix((self.size, self.size), dtype=float)
        self.z_vec = np.zeros((self.size, 1), dtype=float)

    def stamp_linear(self) -> Tuple[lil_matrix, np.ndarray]:
        """Execute the linear MNA Stamping methodology globally."""
        self._allocate_memory()
        
        if self.A_lil is None or self.z_vec is None:
            raise RuntimeError("Memory allocation failed.")
        
        components = self.circuit.get_components()
        
        for comp in components:
            if isinstance(comp, Resistor):
                g = 1.0 / comp.resistance
                i = self.node_to_idx[comp.node1]
                j = self.node_to_idx[comp.node2]
                
                if i >= 0:
                    self.A_lil[i, i] += g
                if j >= 0:
                    self.A_lil[j, j] += g
                    
                if i >= 0 and j >= 0:
                    self.A_lil[i, j] -= g
                    self.A_lil[j, i] -= g
                    
            elif isinstance(comp, (VoltageSource, ACVoltageSource, Inductor)):
                i = self.node_to_idx[comp.node1]
                j = self.node_to_idx[comp.node2]
                k = self.n + self.vsrc_to_idx[comp.name]
                
                if i >= 0:
                    self.A_lil[i, k] += 1.0
                    self.A_lil[k, i] += 1.0
                    
                if j >= 0:
                    self.A_lil[j, k] -= 1.0
                    self.A_lil[k, j] -= 1.0
                    
                if isinstance(comp, ACVoltageSource) and hasattr(comp, 'voltage'):
                    self.z_vec[k, 0] = comp.get_voltage(0.0)
                else:
                    self.z_vec[k, 0] = comp.voltage
                    
            elif isinstance(comp, CurrentSource):
                i = self.node_to_idx.get(comp.node1, -1)
                j = self.node_to_idx.get(comp.node2, -1)
                if i >= 0:
                    self.z_vec[i, 0] -= comp.current
                if j >= 0:
                    self.z_vec[j, 0] += comp.current
                    
            elif isinstance(comp, OpAmp):
                o_idx = self.node_to_idx[comp.out]
                inp_idx = self.node_to_idx[comp.in_p]
                inn_idx = self.node_to_idx[comp.in_n]
                k = self.n + self.vcvs_to_idx[comp.name]
                
                if o_idx >= 0:
                    self.A_lil[o_idx, k] += 1.0
                if o_idx >= 0:
                    self.A_lil[k, o_idx] += 1.0
                if inp_idx >= 0:
                    self.A_lil[k, inp_idx] -= comp.gain
                if inn_idx >= 0:
                    self.A_lil[k, inn_idx] += comp.gain
                self.z_vec[k, 0] = 0.0
                
            elif isinstance(comp, Comparator):
                k = self.n + self.vcvs_to_idx[comp.name]
                o_idx = self.node_to_idx[comp.node_out]
                if o_idx >= 0:
                    self.A_lil[o_idx, k] += 1.0
                    self.A_lil[k, o_idx] += 1.0
                self.z_vec[k, 0] = 0.0
                
        return self.A_lil, self.z_vec

    def stamp_nonlinear(self, x_prev: np.ndarray) -> Tuple[csr_matrix, np.ndarray]:
        """Stamps nonlinear components into isolated high-performance sparse matrices.
        
        OCP Refactored: Uses registry lookup instead of if/elif chain.
        """
        size = self.n + self.m
        z_nl = np.zeros((size, 1), dtype=float)
        
        rows = []
        cols = []
        data = []
        
        components = self.circuit.get_components()
        for comp in components:
            comp_type = type(comp)
            if comp_type in self._nl_stampers:
                stamper_fn = self._nl_stampers[comp_type]
                stamper_fn(comp, x_prev, z_nl, rows, cols, data)
                
        A_nl = csr_matrix((data, (rows, cols)), shape=(size, size), dtype=float)
        return A_nl, z_nl

    def stamp_ac(self, freq_hz: float) -> Tuple[lil_matrix, np.ndarray]:
        """Constructs the Small-Signal Frequency Domain complex matrix."""
        self._allocate_memory()
        
        A_ac = lil_matrix((self.size, self.size), dtype=np.complex128)
        z_ac = np.zeros((self.size, 1), dtype=np.complex128)
        
        omega = 2.0 * np.pi * freq_hz
        
        for comp in self.circuit.get_components():
            Y: complex = 0.0 + 0.0j
            
            if isinstance(comp, Resistor):
                Y = 1.0 / comp.resistance
            elif isinstance(comp, Capacitor):
                Y = 1j * omega * comp.capacitance
            elif isinstance(comp, Inductor):
                if omega == 0.0:
                    Y = 1.0 / (1j * 1e-12 * comp.inductance)
                else:
                    Y = 1.0 / (1j * omega * comp.inductance)
                    
            if isinstance(comp, (Resistor, Capacitor)):
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, n1_idx] += Y
                if n2_idx >= 0:
                    A_ac[n2_idx, n2_idx] += Y
                if n1_idx >= 0 and n2_idx >= 0:
                    A_ac[n1_idx, n2_idx] -= Y
                    A_ac[n2_idx, n1_idx] -= Y
                    
            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, k] += 1.0
                    A_ac[k, n1_idx] += 1.0
                if n2_idx >= 0:
                    A_ac[n2_idx, k] -= 1.0
                    A_ac[k, n2_idx] -= 1.0
                    
                A_ac[k, k] += (-1j * omega * comp.inductance)
                z_ac[k, 0] = 0.0

            elif isinstance(comp, OpAmp):
                o_idx = self.node_to_idx[comp.out]
                inp_idx = self.node_to_idx[comp.in_p]
                inn_idx = self.node_to_idx[comp.in_n]
                k = self.n + self.vcvs_to_idx[comp.name]
                
                if o_idx >= 0:
                    A_ac[o_idx, k] += 1.0
                    A_ac[k, o_idx] += 1.0 
                if inp_idx >= 0:
                    A_ac[k, inp_idx] -= comp.gain
                if inn_idx >= 0:
                    A_ac[k, inn_idx] += comp.gain
                    
            elif isinstance(comp, VoltageSource) and not isinstance(comp, ACVoltageSource):
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, k] += 1.0
                    A_ac[k, n1_idx] += 1.0
                if n2_idx >= 0:
                    A_ac[n2_idx, k] -= 1.0
                    A_ac[k, n2_idx] -= 1.0
                z_ac[k, 0] = 0.0
                
            elif isinstance(comp, ACVoltageSource):
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, k] += 1.0
                    A_ac[k, n1_idx] += 1.0
                if n2_idx >= 0:
                    A_ac[n2_idx, k] -= 1.0
                    A_ac[k, n2_idx] -= 1.0
                    
                phasor = comp.ac_mag * np.exp(1j * np.radians(comp.ac_phase))
                z_ac[k, 0] = phasor

        return A_ac, z_ac

    def stamp_transient_basis(self, A_clone: lil_matrix, dt: float) -> None:
        """Stamps pure linear structural basis components of L and C."""
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Capacitor):
                Geq = comp.capacitance / dt
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                
                if i_idx >= 0:
                    A_clone[i_idx, i_idx] += Geq
                if j_idx >= 0:
                    A_clone[j_idx, j_idx] += Geq
                if i_idx >= 0 and j_idx >= 0:
                    A_clone[i_idx, j_idx] -= Geq
                    A_clone[j_idx, i_idx] -= Geq
                    
            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                
                if i_idx >= 0:
                    A_clone[i_idx, k] += 1.0
                    A_clone[k, i_idx] += 1.0
                if j_idx >= 0:
                    A_clone[j_idx, k] -= 1.0
                    A_clone[k, j_idx] -= 1.0
                A_clone[k, k] += (-comp.inductance / dt)

    def stamp_transient_sources(self, z_clone: np.ndarray, dt: float, x_prev: np.ndarray) -> None:
        """Stamps L, C histories into clones Vectors per-timestep."""
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Capacitor):
                Geq = comp.capacitance / dt
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                
                v_i = self._get_v(i_idx, x_prev)
                v_j = self._get_v(j_idx, x_prev)
                V_prev = v_i - v_j
                
                Ieq = Geq * V_prev
                if i_idx >= 0:
                    z_clone[i_idx, 0] += Ieq
                if j_idx >= 0:
                    z_clone[j_idx, 0] -= Ieq
                    
            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                Ieq = -(comp.inductance / dt) * comp.i_prev
                z_clone[k, 0] += Ieq

    def update_states(self, x_converged: np.ndarray, dt: float) -> None:
        """Synchronizes and progresses physics-level components internal memory."""
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                i_L = x_converged[k]
                comp.i_prev = float(i_L)

    def stamp_dynamic_sources(self, z_clone: np.ndarray, t: float) -> None:
        """Stamps dynamic time-varying sources."""
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, ACVoltageSource):
                k = self.n + self.vsrc_to_idx[comp.name]
                z_clone[k, 0] = comp.get_voltage(t)

    def _get_v(self, idx: int, x_prev: np.ndarray) -> float:
        """Encapsulated retrieval of node voltage with ground-node support."""
        return float(x_prev[idx]) if idx >= 0 else 0.0

    # ── Nonlinear Handler Methods ──────────────────────────────────────

    def _stamp_diode_nl(self, comp: Diode, x_prev: np.ndarray, z_nl: np.ndarray, rows: list, cols: list, data: list) -> None:
        anode_idx = self.node_to_idx[comp.node1]
        cathode_idx = self.node_to_idx[comp.node2]

        v_anode = self._get_v(anode_idx, x_prev)
        v_cathode = self._get_v(cathode_idx, x_prev)
        Vd = v_anode - v_cathode

        if getattr(comp, 'Vz', None) is not None and Vd < -comp.Vz:
            Gz = 1e2 
            Id = Gz * (Vd + comp.Vz)
            Geq = Gz
            Ieq = Id - Geq * Vd
        else:
            nvt = getattr(comp, "n", 1.0) * comp.Vt
            Vd_safe = min(Vd, 0.8 * getattr(comp, "n", 1.0))
            exp_val = np.exp(Vd_safe / nvt)
            Id = comp.Is * (exp_val - 1.0)
            Geq = (comp.Is / nvt) * exp_val
            Ieq = Id - Geq * Vd_safe

        if anode_idx >= 0:
            z_nl[anode_idx, 0] -= Ieq
            rows.append(anode_idx); cols.append(anode_idx); data.append(Geq)
        if cathode_idx >= 0:
            z_nl[cathode_idx, 0] += Ieq
            rows.append(cathode_idx); cols.append(cathode_idx); data.append(Geq)

        if anode_idx >= 0 and cathode_idx >= 0:
            rows.append(anode_idx); cols.append(cathode_idx); data.append(-Geq)
            rows.append(cathode_idx); cols.append(anode_idx); data.append(-Geq)

    def _stamp_comparator_nl(self, comp: Comparator, x_prev: np.ndarray, z_nl: np.ndarray, rows: list, cols: list, data: list) -> None:
        k = self.n + self.vcvs_to_idx[comp.name]
        p_idx = self.node_to_idx[comp.node_p]
        n_idx = self.node_to_idx[comp.node_n]

        v_p = self._get_v(p_idx, x_prev)
        v_n = self._get_v(n_idx, x_prev)

        V_diff = v_p - v_n
        tanh_val = np.tanh(comp.k * V_diff)
        V_out_val = comp.v_low + ((comp.v_high - comp.v_low) / 2.0) * (1.0 + tanh_val)
        f_prime = ((comp.v_high - comp.v_low) / 2.0) * comp.k * (1.0 - (tanh_val ** 2))

        z_nl[k, 0] += V_out_val - (f_prime * V_diff)
        if p_idx >= 0:
            rows.append(k); cols.append(p_idx); data.append(-f_prime)
        if n_idx >= 0:
            rows.append(k); cols.append(n_idx); data.append(f_prime)

    def _stamp_bjt_nl(self, comp: BJT, x_prev: np.ndarray, z_nl: np.ndarray, rows: list, cols: list, data: list) -> None:
        c_idx = self.node_to_idx[comp.collector]
        b_idx = self.node_to_idx[comp.base]
        e_idx = self.node_to_idx[comp.emitter]

        v_c = self._get_v(c_idx, x_prev)
        v_b = self._get_v(b_idx, x_prev)
        v_e = self._get_v(e_idx, x_prev)

        Vbe = v_b - v_e
        Vbc = v_b - v_c
        Vbe_safe = min(Vbe, 0.8)
        Vbc_safe = min(Vbc, 0.8)

        exp_vbe = np.exp(Vbe_safe / comp.Vt)
        exp_vbc = np.exp(Vbc_safe / comp.Vt)

        I_be = (comp.Is / comp.Bf) * (exp_vbe - 1.0)
        I_bc = (comp.Is / comp.Br) * (exp_vbc - 1.0)
        I_ce = comp.Is * (exp_vbe - exp_vbc)

        Ib = I_be + I_bc
        Ic = I_ce - I_bc
        Ie = -Ib - Ic

        g_be = (comp.Is / (comp.Bf * comp.Vt)) * exp_vbe
        g_bc = (comp.Is / (comp.Br * comp.Vt)) * exp_vbc
        g_ce = (comp.Is / comp.Vt) * exp_vbe
        g_ec = (comp.Is / comp.Vt) * exp_vbc

        Ieq_b = Ib - (g_be * Vbe_safe + g_bc * Vbc_safe)
        Ieq_c = Ic - (g_ce * Vbe_safe - (g_ec + g_bc) * Vbc_safe)
        Ieq_e = Ie - (- (g_be + g_ce) * Vbe_safe + g_ec * Vbc_safe)

        if b_idx >= 0:
            z_nl[b_idx, 0] -= Ieq_b
            rows.append(b_idx); cols.append(b_idx); data.append(g_be + g_bc)
            if e_idx >= 0: rows.append(b_idx); cols.append(e_idx); data.append(-g_be)
            if c_idx >= 0: rows.append(b_idx); cols.append(c_idx); data.append(-g_bc)

        if c_idx >= 0:
            z_nl[c_idx, 0] -= Ieq_c
            if b_idx >= 0: rows.append(c_idx); cols.append(b_idx); data.append(g_ce - g_bc)
            if e_idx >= 0: rows.append(c_idx); cols.append(e_idx); data.append(-g_ce)
            rows.append(c_idx); cols.append(c_idx); data.append(g_ec + g_bc)

        if e_idx >= 0:
            z_nl[e_idx, 0] -= Ieq_e
            if b_idx >= 0: rows.append(e_idx); cols.append(b_idx); data.append(-g_be - g_ce)
            rows.append(e_idx); cols.append(e_idx); data.append(g_be + g_ce)
            if c_idx >= 0: rows.append(e_idx); cols.append(c_idx); data.append(-g_ec)

    def _stamp_nmos_nl(self, comp: MOSFET_N, x_prev: np.ndarray, z_nl: np.ndarray, rows: list, cols: list, data: list) -> None:
        d_idx = self.node_to_idx[comp.drain]
        g_idx = self.node_to_idx[comp.gate]
        s_idx = self.node_to_idx[comp.source]

        v_d = self._get_v(d_idx, x_prev)
        v_g = self._get_v(g_idx, x_prev)
        v_s = self._get_v(s_idx, x_prev)

        Vgs = v_g - v_s
        Vds = v_d - v_s
        Id, gm, gds = 0.0, 0.0, 0.0

        if Vgs <= comp.v_th:
            pass
        elif Vds < Vgs - comp.v_th:
            Vov = Vgs - comp.v_th
            Id = comp.beta * (Vov * Vds - 0.5 * Vds**2) * (1 + comp.lambda_ * Vds)
            gm = comp.beta * Vds * (1 + comp.lambda_ * Vds)
            gds = comp.beta * (Vov - Vds) * (1 + comp.lambda_ * Vds) + comp.beta * (Vov * Vds - 0.5 * Vds**2) * comp.lambda_
        else:
            Vov = Vgs - comp.v_th
            Vov = min(Vov, 20.0) 
            Id = 0.5 * comp.beta * Vov**2 * (1 + comp.lambda_ * Vds)
            gm = comp.beta * Vov * (1 + comp.lambda_ * Vds)
            gds = 0.5 * comp.beta * Vov**2 * comp.lambda_

        Ieq = Id - gm * Vgs - gds * Vds
        self._apply_fet_matrix_stamp(d_idx, g_idx, s_idx, gm, gds, Ieq, rows, cols, data, z_nl, current_leaves_drain=True)

    def _stamp_pmos_nl(self, comp: MOSFET_P, x_prev: np.ndarray, z_nl: np.ndarray, rows: list, cols: list, data: list) -> None:
        d_idx = self.node_to_idx[comp.drain]
        g_idx = self.node_to_idx[comp.gate]
        s_idx = self.node_to_idx[comp.source]

        v_d = self._get_v(d_idx, x_prev)
        v_g = self._get_v(g_idx, x_prev)
        v_s = self._get_v(s_idx, x_prev)

        Vsg = v_s - v_g
        Vsd = v_s - v_d
        Vth_p = abs(comp.v_th)
        Isd, gm, gds = 0.0, 0.0, 0.0

        if Vsg <= Vth_p:
            pass
        elif Vsd < Vsg - Vth_p:
            Vov = Vsg - Vth_p
            Isd = comp.beta * (Vov * Vsd - 0.5 * Vsd**2) * (1 + comp.lambda_ * Vsd)
            gm = comp.beta * Vsd * (1 + comp.lambda_ * Vsd)
            gds = comp.beta * (Vov - Vsd) * (1 + comp.lambda_ * Vsd) + comp.beta * (Vov * Vsd - 0.5 * Vsd**2) * comp.lambda_
        else:
            Vov = Vsg - Vth_p
            Vov = min(Vov, 20.0) 
            Isd = 0.5 * comp.beta * Vov**2 * (1 + comp.lambda_ * Vsd)
            gm = comp.beta * Vov * (1 + comp.lambda_ * Vsd)
            gds = 0.5 * comp.beta * Vov**2 * comp.lambda_

        Ieq = Isd - gm * Vsg - gds * Vsd
        self._apply_fet_matrix_stamp(d_idx, g_idx, s_idx, gm, gds, Ieq, rows, cols, data, z_nl, current_leaves_drain=False)

    def _apply_fet_matrix_stamp(self, d_idx, g_idx, s_idx, gm, gds, Ieq, rows, cols, data, z_nl, current_leaves_drain=True):
        """Shared matrix mapping logic for both NMOS and PMOS.
        
        Using unified Jacobian entries for FETS where:
        - gm links Gate to Source.
        - gds links Drain to Source.
        """
        # 1. Gmin injections (identical for both to prevent floating nodes)
        Gmin = 1e-12
        if g_idx >= 0:
            rows.append(g_idx); cols.append(g_idx); data.append(Gmin)
            if s_idx >= 0:
                rows.append(g_idx); cols.append(s_idx); data.append(-Gmin)
        if s_idx >= 0:
            rows.append(s_idx); cols.append(s_idx); data.append(Gmin)
            if g_idx >= 0:
                rows.append(s_idx); cols.append(g_idx); data.append(-Gmin)
            if d_idx >= 0:
                rows.append(s_idx); cols.append(d_idx); data.append(-Gmin)
        if d_idx >= 0:
            rows.append(d_idx); cols.append(d_idx); data.append(Gmin)
            if s_idx >= 0:
                rows.append(d_idx); cols.append(s_idx); data.append(-Gmin)

        # 2. RHS Contribution
        if current_leaves_drain: # NMOS: Id flows D -> S
            if d_idx >= 0: z_nl[d_idx, 0] -= Ieq
            if s_idx >= 0: z_nl[s_idx, 0] += Ieq
        else: # PMOS: Isd flows S -> D
            if s_idx >= 0: z_nl[s_idx, 0] -= Ieq
            if d_idx >= 0: z_nl[d_idx, 0] += Ieq

        # 3. Jacobian (Jacobian entries are symmetrical in structure for NMOS:Id and PMOS:Isd)
        if d_idx >= 0:
            rows.append(d_idx); cols.append(d_idx); data.append(gds)
            if s_idx >= 0: rows.append(d_idx); cols.append(s_idx); data.append(-gds - gm)
            if g_idx >= 0: rows.append(d_idx); cols.append(g_idx); data.append(gm)

        if s_idx >= 0:
            rows.append(s_idx); cols.append(s_idx); data.append(gds + gm)
            if d_idx >= 0: rows.append(s_idx); cols.append(d_idx); data.append(-gds)
            if g_idx >= 0: rows.append(s_idx); cols.append(g_idx); data.append(-gm)
