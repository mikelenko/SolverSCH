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
    Diode, Capacitor, Inductor, _BJTBase, BJT_N, BJT_P, BJT,
    MOSFET_N, MOSFET_P, OpAmp, Comparator, LM5085Gate,
)
from solver_sch.constants import GMIN
from solver_sch.builder.nl_stampers import (
    stamp_diode_nl, stamp_bjt_nl, stamp_mosfet_nl, stamp_comparator_nl,
    stamp_lm5085_gate_nl,
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

        # DC operating point for AC linearization
        self._x_dc: np.ndarray | None = None

        # OCP Registry for nonlinear components
        # Maps Component Type -> Handler method
        self._nl_stampers: Dict[type, Callable] = {
            Diode: stamp_diode_nl,
            Comparator: stamp_comparator_nl,
            BJT_N: stamp_bjt_nl,
            BJT_P: stamp_bjt_nl,
            MOSFET_N: stamp_mosfet_nl,
            MOSFET_P: stamp_mosfet_nl,
            LM5085Gate: stamp_lm5085_gate_nl,
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
            elif isinstance(comp, (OpAmp, Comparator, LM5085Gate)):
                self.vcvs_to_idx[comp.name] = m_idx
                m_idx += 1
                
        self.m = m_idx
        self.size = self.n + self.m

    def _allocate_memory(self) -> None:
        """Instantiate empty `lil_matrix` and right-hand side `ndarray` buffers."""
        self.A_lil = lil_matrix((self.size, self.size), dtype=float)
        self.z_vec = np.zeros((self.size, 1), dtype=float)

    @staticmethod
    def _stamp_admittance(A, i: int, j: int, Y) -> None:
        """Stamp a 2-terminal admittance Y into MNA matrix A."""
        if i >= 0:
            A[i, i] += Y
        if j >= 0:
            A[j, j] += Y
        if i >= 0 and j >= 0:
            A[i, j] -= Y
            A[j, i] -= Y

    @staticmethod
    def _stamp_branch_kvl(A, node1_idx: int, node2_idx: int, branch_idx: int) -> None:
        """Stamp symmetric KVL entries for a 2-terminal voltage-source branch."""
        if node1_idx >= 0:
            A[node1_idx, branch_idx] += 1.0
            A[branch_idx, node1_idx] += 1.0
        if node2_idx >= 0:
            A[node2_idx, branch_idx] -= 1.0
            A[branch_idx, node2_idx] -= 1.0

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
                self._stamp_admittance(self.A_lil, i, j, g)
                    
            elif isinstance(comp, (VoltageSource, ACVoltageSource, Inductor)):
                i = self.node_to_idx[comp.node1]
                j = self.node_to_idx[comp.node2]
                k = self.n + self.vsrc_to_idx[comp.name]
                self._stamp_branch_kvl(self.A_lil, i, j, k)
                    
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

            elif isinstance(comp, LM5085Gate):
                # KVL row for PGATE: V_pgate - V_gnd = f(V_vin, V_fb) [nonlinear, stamped in NL]
                # Linear part: connect PGATE node to the auxiliary current variable
                k = self.n + self.vcvs_to_idx[comp.name]
                pg_idx = self.node_to_idx[comp.pgate]
                gnd_idx = self.node_to_idx[comp.gnd]
                self._stamp_branch_kvl(self.A_lil, pg_idx, gnd_idx, k)
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
                if comp_type in (Comparator, LM5085Gate):
                    stamper_fn(comp, x_prev, z_nl, rows, cols, data,
                               self.node_to_idx, self._get_v, self.vcvs_to_idx, self.n)
                else:
                    stamper_fn(comp, x_prev, z_nl, rows, cols, data,
                               self.node_to_idx, self._get_v)
                
        A_nl = csr_matrix((data, (rows, cols)), shape=(size, size), dtype=float)
        return A_nl, z_nl

    def set_dc_solution(self, x_dc: np.ndarray) -> None:
        """Store the DC operating point for AC small-signal linearization."""
        self._x_dc = x_dc.copy()

    def stamp_ac(self, freq_hz: float) -> Tuple[lil_matrix, np.ndarray]:
        """Constructs the Small-Signal Frequency Domain complex matrix.

        Linearizes nonlinear components (BJT, MOSFET, Diode) around the DC
        operating point stored via set_dc_solution().
        """
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
                self._stamp_admittance(A_ac, n1_idx, n2_idx, Y)

            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                self._stamp_branch_kvl(A_ac, n1_idx, n2_idx, k)
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
                self._stamp_branch_kvl(A_ac, n1_idx, n2_idx, k)
                z_ac[k, 0] = 0.0

            elif isinstance(comp, ACVoltageSource):
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                self._stamp_branch_kvl(A_ac, n1_idx, n2_idx, k)
                phasor = comp.ac_mag * np.exp(1j * np.radians(comp.ac_phase))
                z_ac[k, 0] = phasor

            # ── Nonlinear small-signal linearization at DC operating point ──
            elif isinstance(comp, Diode) and self._x_dc is not None:
                self._stamp_ac_diode(A_ac, comp)

            elif isinstance(comp, _BJTBase) and self._x_dc is not None:
                self._stamp_ac_bjt(A_ac, comp)

            elif isinstance(comp, (MOSFET_N, MOSFET_P)) and self._x_dc is not None:
                self._stamp_ac_mosfet(A_ac, comp)

        return A_ac, z_ac

    def _stamp_ac_diode(self, A_ac, comp: Diode) -> None:
        """Stamp diode small-signal conductance at DC bias into AC matrix."""
        from solver_sch.constants import DIODE_VD_LIMIT
        a_idx = self.node_to_idx[comp.node1]
        c_idx = self.node_to_idx[comp.node2]
        Va = self._get_v(a_idx, self._x_dc)
        Vc = self._get_v(c_idx, self._x_dc)
        Vd = Va - Vc
        nvt = getattr(comp, "n", 1.0) * comp.Vt
        Vd_safe = min(Vd, DIODE_VD_LIMIT * getattr(comp, "n", 1.0))
        Geq = (comp.Is / nvt) * np.exp(Vd_safe / nvt)
        self._stamp_admittance(A_ac, a_idx, c_idx, complex(Geq))

    def _stamp_ac_bjt(self, A_ac, comp: "_BJTBase") -> None:
        """Stamp BJT small-signal Ebers-Moll conductances at DC bias into AC matrix.

        Uses comp._polarity: +1 for NPN, -1 for PNP.
        """
        from solver_sch.constants import BJT_VBE_LIMIT
        p = comp._polarity
        c_idx = self.node_to_idx[comp.collector]
        b_idx = self.node_to_idx[comp.base]
        e_idx = self.node_to_idx[comp.emitter]

        # Normalized voltages (positive when forward-biased for both NPN and PNP)
        Vbe = p * (self._get_v(b_idx, self._x_dc) - self._get_v(e_idx, self._x_dc))
        Vbc = p * (self._get_v(b_idx, self._x_dc) - self._get_v(c_idx, self._x_dc))
        Vbe_safe = min(Vbe, BJT_VBE_LIMIT)
        Vbc_safe = min(Vbc, BJT_VBE_LIMIT)

        exp_vbe = np.exp(Vbe_safe / comp.Vt)
        exp_vbc = np.exp(Vbc_safe / comp.Vt)

        # Small-signal conductances (same as NR Jacobian entries)
        g_be = (comp.Is / (comp.Bf * comp.Vt)) * exp_vbe
        g_bc = (comp.Is / (comp.Br * comp.Vt)) * exp_vbc
        g_ce = (comp.Is / comp.Vt) * exp_vbe   # forward transconductance
        g_ec = (comp.Is / comp.Vt) * exp_vbc   # reverse transconductance

        # Stamp into AC matrix (same Jacobian pattern as stamp_bjt_nl)
        if b_idx >= 0:
            A_ac[b_idx, b_idx] += g_be + g_bc
            if e_idx >= 0: A_ac[b_idx, e_idx] -= g_be
            if c_idx >= 0: A_ac[b_idx, c_idx] -= g_bc

        if c_idx >= 0:
            if b_idx >= 0: A_ac[c_idx, b_idx] += g_ce - g_bc
            if e_idx >= 0: A_ac[c_idx, e_idx] -= g_ce
            A_ac[c_idx, c_idx] += g_ec + g_bc

        if e_idx >= 0:
            if b_idx >= 0: A_ac[e_idx, b_idx] -= g_be + g_ce
            A_ac[e_idx, e_idx] += g_be + g_ce
            if c_idx >= 0: A_ac[e_idx, c_idx] -= g_ec

    def _stamp_ac_mosfet(self, A_ac, comp) -> None:
        """Stamp MOSFET small-signal gm/gds at DC bias into AC matrix."""
        from solver_sch.constants import MOSFET_VOV_CLAMP
        p = comp._polarity
        d_idx = self.node_to_idx[comp.drain]
        g_idx = self.node_to_idx[comp.gate]
        s_idx = self.node_to_idx[comp.source]

        v_d = self._get_v(d_idx, self._x_dc)
        v_g = self._get_v(g_idx, self._x_dc)
        v_s = self._get_v(s_idx, self._x_dc)

        V1 = p * (v_g - v_s)  # Vgs or Vsg
        V2 = p * (v_d - v_s)  # Vds or Vsd
        Vth = abs(comp.v_th)
        gm, gds = 0.0, 0.0

        if V1 > Vth:
            if V2 < V1 - Vth:  # Linear/Triode
                Vov = V1 - Vth
                gm = comp.beta * V2 * (1 + comp.lambda_ * V2)
                gds = comp.beta * (Vov - V2) * (1 + comp.lambda_ * V2) + comp.beta * (Vov * V2 - 0.5 * V2**2) * comp.lambda_
            else:  # Saturation
                Vov = min(V1 - Vth, MOSFET_VOV_CLAMP)
                gm = comp.beta * Vov * (1 + comp.lambda_ * V2)
                gds = 0.5 * comp.beta * Vov**2 * comp.lambda_

        # Stamp gm and gds into AC matrix
        if d_idx >= 0:
            A_ac[d_idx, d_idx] += gds + GMIN
            if s_idx >= 0: A_ac[d_idx, s_idx] -= gds + gm
            if g_idx >= 0: A_ac[d_idx, g_idx] += gm
        if s_idx >= 0:
            A_ac[s_idx, s_idx] += gds + gm + GMIN
            if d_idx >= 0: A_ac[s_idx, d_idx] -= gds
            if g_idx >= 0: A_ac[s_idx, g_idx] -= gm

    def stamp_transient_basis(self, A_clone: lil_matrix, dt: float) -> None:
        """Stamps pure linear structural basis components of L and C."""
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Capacitor):
                Geq = comp.capacitance / dt
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                self._stamp_admittance(A_clone, i_idx, j_idx, Geq)
                    
            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                self._stamp_branch_kvl(A_clone, i_idx, j_idx, k)
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

