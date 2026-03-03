"""
stamper.py -> The MNA Builder / Translation Layer.

Strict Rules:
- Maps the domain logic (Circuit) into the mathematical domain (Sparse Matrices).
- MUST use `scipy.sparse.lil_matrix` (List of Lists format) due to its O(1) 
  complexity for iterative structural mutations (incremental row/col modifications).
"""

from typing import Dict, Tuple

import numpy as np
from scipy.sparse import lil_matrix, csr_matrix

from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, ACVoltageSource, Diode, Capacitor, Inductor, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator


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
        """Instantiate empty `lil_matrix` and right-hand side `ndarray` buffers.
        
        Rules:
        - Initialize the 'A' matrix as scipy.sparse.lil_matrix with size (n + m) x (n + m).
          lil_matrix is optimal for modifying structure progressively without overhead.
        - Initialize the 'z' vector as a 1D column vector size (n + m) x 1 using numpy arrays
          (most optimal format for the later sparse solver compatibility).
        """
        self.A_lil = lil_matrix((self.size, self.size), dtype=float)
        self.z_vec = np.zeros((self.size, 1), dtype=float)

    def stamp_linear(self) -> Tuple[lil_matrix, np.ndarray]:
        """Execute the linear MNA Stamping methodology globally.
        
        Iterates through the linear components (Resistor, VoltageSource) in the model 
        and stamps the base matrices A and z. Only called ONCE.
        
        Returns:
            Tuple containing the A matrix (as lil_matrix) and RHS z vector (ndarray).
        """
        # _map_nodes is now called in __init__
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
                    
                # Assign DC Value to RHS
                if isinstance(comp, ACVoltageSource) and hasattr(comp, 'voltage'):
                    self.z_vec[k, 0] = comp.get_voltage(0.0)
                else:
                    self.z_vec[k, 0] = comp.voltage
                    
            elif isinstance(comp, OpAmp):
                # An Ideal OpAmp generates a branch current at its output terminal
                # to sustain V_out = A*(V_in_p - V_in_n)
                # It behaves topologically exactly as a VoltageSource but voltage equates variable KVL.
                o_idx = self.node_to_idx[comp.out]
                inp_idx = self.node_to_idx[comp.in_p]
                inn_idx = self.node_to_idx[comp.in_n]
                k = self.n + self.vcvs_to_idx[comp.name]
                
                # 1. KCL column constraint (current leaves the output node)
                if o_idx >= 0:
                    self.A_lil[o_idx, k] += 1.0
                    
                # 2. KVL Row Definition: V_out - A * V_in_p + A * V_in_n = 0
                if o_idx >= 0:
                    self.A_lil[k, o_idx] += 1.0 # Output is positive
                
                # A -> 1e5 Matrix coefficient mappings
                if inp_idx >= 0:
                    self.A_lil[k, inp_idx] -= comp.gain
                    
                if inn_idx >= 0:
                    self.A_lil[k, inn_idx] += comp.gain
                    
                self.z_vec[k, 0] = 0.0 # Equation drives to zero structurally
                
            elif isinstance(comp, Comparator):
                k = self.n + self.vcvs_to_idx[comp.name]
                o_idx = self.node_to_idx[comp.node_out]
                if o_idx >= 0:
                    self.A_lil[o_idx, k] += 1.0
                    self.A_lil[k, o_idx] += 1.0 # Base diagonal structure for voltage constraint
                self.z_vec[k, 0] = 0.0
                
        return self.A_lil, self.z_vec

    def stamp_nonlinear(self, x_prev: np.ndarray) -> Tuple[csr_matrix, np.ndarray]:
        """Stamps nonlinear components (e.g. Diodes) into isolated high-performance sparse matrices.
        
        Parameters:
            x_prev: The solution vector derived from the previous NR iteration (`x` shape matching system).
            
        Returns:
            Tuple containing the A_nl matrix (as csr_matrix) and RHS z_nl vector (ndarray).
            This eliminates completely the severe copy() and lil_matrix memory bottlenecks.
        """
        size = self.n + self.m
        z_nl = np.zeros((size, 1), dtype=float)
        
        rows = []
        cols = []
        data = []
        
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Diode):
                # ... fetch current iteration voltage
                anode_idx = self.node_to_idx[comp.node1]
                cathode_idx = self.node_to_idx[comp.node2]
                
                v_anode = x_prev[anode_idx] if anode_idx >= 0 else 0.0
                v_cathode = x_prev[cathode_idx] if cathode_idx >= 0 else 0.0
                Vd = v_anode - v_cathode
                
                # Zener Reverse Breakdown override
                if getattr(comp, 'Vz', None) is not None and Vd < -comp.Vz:
                    # Steep linear proxy for avalanche 
                    Gz = 1e2 # More stable damping for Newton-Raphson than 1M
                    Id = Gz * (Vd + comp.Vz)
                    Geq = Gz
                    Ieq = Id - Geq * Vd
                else:
                    # Limit Vd for numerical stability
                    Vd_safe = min(Vd, 0.8)
                    
                    # Exponential forward companion model
                    exp_val = np.exp(Vd_safe / comp.Vt)
                    Id = comp.Is * (exp_val - 1.0)
                    Geq = (comp.Is / comp.Vt) * exp_val
                    Ieq = Id - Geq * Vd_safe
                
                # Map to physical Arrays
                if anode_idx >= 0:
                    z_nl[anode_idx, 0] -= Ieq
                    rows.append(anode_idx)
                    cols.append(anode_idx)
                    data.append(Geq)
                if cathode_idx >= 0:
                    z_nl[cathode_idx, 0] += Ieq
                    rows.append(cathode_idx)
                    cols.append(cathode_idx)
                    data.append(Geq)
                    
                if anode_idx >= 0 and cathode_idx >= 0:
                    rows.append(anode_idx)
                    cols.append(cathode_idx)
                    data.append(-Geq)
                    rows.append(cathode_idx)
                    cols.append(anode_idx)
                    data.append(-Geq)
                    
            elif isinstance(comp, Comparator):
                k = self.n + self.vcvs_to_idx[comp.name]
                p_idx = self.node_to_idx[comp.node_p]
                n_idx = self.node_to_idx[comp.node_n]
                
                v_p = x_prev[p_idx] if p_idx >= 0 else 0.0
                v_n = x_prev[n_idx] if n_idx >= 0 else 0.0
                
                V_diff = v_p - v_n
                tanh_val = np.tanh(comp.k * V_diff)
                
                # Smooth continuous output
                V_out_val = comp.v_low + ((comp.v_high - comp.v_low) / 2.0) * (1.0 + tanh_val)
                
                # Derivative: f'(V_diff)
                f_prime = ((comp.v_high - comp.v_low) / 2.0) * comp.k * (1.0 - (tanh_val ** 2))
                
                # Stamp RHS
                z_nl[k, 0] += V_out_val - (f_prime * V_diff)
                
                # Stamp Jacobian matrix A_nl
                if p_idx >= 0:
                    rows.append(k)
                    cols.append(p_idx)
                    data.append(-f_prime)
                if n_idx >= 0:
                    rows.append(k)
                    cols.append(n_idx)
                    data.append(f_prime)
                    
            elif isinstance(comp, BJT):
                # 1. Fetch topological pointers
                c_idx = self.node_to_idx[comp.collector]
                b_idx = self.node_to_idx[comp.base]
                e_idx = self.node_to_idx[comp.emitter]
                
                # 2. Recreate physical terminal voltages from iteration step output
                v_c = x_prev[c_idx] if c_idx >= 0 else 0.0
                v_b = x_prev[b_idx] if b_idx >= 0 else 0.0
                v_e = x_prev[e_idx] if e_idx >= 0 else 0.0
                
                Vbe = v_b - v_e
                Vbc = v_b - v_c
                
                # 3. Secure against math explosions (Critical Non-Linear Limiting!)
                Vbe_safe = min(Vbe, 0.8)
                Vbc_safe = min(Vbc, 0.8)
                
                # 4. Math: Ebers-Moll internal Injection Equations
                exp_vbe = np.exp(Vbe_safe / comp.Vt)
                exp_vbc = np.exp(Vbc_safe / comp.Vt)
                
                I_be = (comp.Is / comp.Bf) * (exp_vbe - 1.0)
                I_bc = (comp.Is / comp.Br) * (exp_vbc - 1.0)
                I_ce = comp.Is * (exp_vbe - exp_vbc)
                
                # 5. Math: Real physical Nodal Branch Currents
                Ib = I_be + I_bc
                Ic = I_ce - I_bc
                Ie = -Ib - Ic # KCL: Ie + Ib + Ic = 0
                
                # 6. Math: Linear partial Conductances (Jacobian Matrix partial-derivatives)
                g_be = (comp.Is / (comp.Bf * comp.Vt)) * exp_vbe
                g_bc = (comp.Is / (comp.Br * comp.Vt)) * exp_vbc
                g_ce = (comp.Is / comp.Vt) * exp_vbe
                g_ec = (comp.Is / comp.Vt) * exp_vbc
                
                # 7. Math: Iterative Source derivations (Newton-Raphson Companion Currents)
                Ieq_b = Ib - (g_be * Vbe_safe + g_bc * Vbc_safe)
                Ieq_c = Ic - (g_ce * Vbe_safe - (g_ec + g_bc) * Vbc_safe)  # Note factoring of Vbc_safe for Ic
                Ieq_e = Ie - (- (g_be + g_ce) * Vbe_safe + g_ec * Vbc_safe)
                
                # 8. Render Topologies to physical Arrays (O(1) isolated matrix staging)
                # Map Base Terminal
                if b_idx >= 0:
                    z_nl[b_idx, 0] -= Ieq_b
                    # Self-Conductance
                    rows.append(b_idx); cols.append(b_idx); data.append(g_be + g_bc)
                    # Mutual to Emitter
                    if e_idx >= 0:
                        rows.append(b_idx); cols.append(e_idx); data.append(-g_be)
                    # Mutual to Collector
                    if c_idx >= 0:
                        rows.append(b_idx); cols.append(c_idx); data.append(-g_bc)
                        
                # Map Collector Terminal
                if c_idx >= 0:
                    z_nl[c_idx, 0] -= Ieq_c
                    # Mutual to Base
                    if b_idx >= 0:
                        rows.append(c_idx); cols.append(b_idx); data.append(g_ce - g_bc)
                    # Mutual to Emitter
                    if e_idx >= 0:
                        rows.append(c_idx); cols.append(e_idx); data.append(-g_ce)
                    # Self-Conductance
                    rows.append(c_idx); cols.append(c_idx); data.append(g_ec + g_bc)
                    
                # Map Emitter Terminal
                if e_idx >= 0:
                    z_nl[e_idx, 0] -= Ieq_e
                    # Mutual to Base
                    if b_idx >= 0:
                        rows.append(e_idx); cols.append(b_idx); data.append(-g_be - g_ce)
                    # Self-Conductance
                    rows.append(e_idx); cols.append(e_idx); data.append(g_be + g_ce)
                    # Mutual to Collector
                    if c_idx >= 0:
                        rows.append(e_idx); cols.append(c_idx); data.append(-g_ec)
            
            elif isinstance(comp, MOSFET_N):
                # 1. Topological Pointers
                d_idx = self.node_to_idx[comp.drain]
                g_idx = self.node_to_idx[comp.gate]
                s_idx = self.node_to_idx[comp.source]
                
                # 2. Terminal Voltages
                v_d = x_prev[d_idx] if d_idx >= 0 else 0.0
                v_g = x_prev[g_idx] if g_idx >= 0 else 0.0
                v_s = x_prev[s_idx] if s_idx >= 0 else 0.0
                
                Vgs = v_g - v_s
                Vds = v_d - v_s
                
                Id, gm, gds = 0.0, 0.0, 0.0
                
                # 3. Shichman-Hodges Regions
                if Vgs <= comp.v_th:
                    # Cutoff
                    pass
                elif Vds < Vgs - comp.v_th:
                    # Linear / Triode
                    Vov = Vgs - comp.v_th
                    Id = comp.beta * (Vov * Vds - 0.5 * Vds**2) * (1 + comp.lambda_ * Vds)
                    gm = comp.beta * Vds * (1 + comp.lambda_ * Vds)
                    gds = comp.beta * (Vov - Vds) * (1 + comp.lambda_ * Vds) + comp.beta * (Vov * Vds - 0.5 * Vds**2) * comp.lambda_
                else:
                    # Saturation
                    Vov = Vgs - comp.v_th
                    # Hard limit for extremely large voltages during NR guessing
                    Vov = min(Vov, 20.0) 
                    Id = 0.5 * comp.beta * Vov**2 * (1 + comp.lambda_ * Vds)
                    gm = comp.beta * Vov * (1 + comp.lambda_ * Vds)
                    gds = 0.5 * comp.beta * Vov**2 * comp.lambda_
                
                # 4. Equivalent Current for NR
                Ieq = Id - gm * Vgs - gds * Vds
                
                # 5. Math Mapping
                Gmin = 1e-12
                
                # Gmin Gate-Source
                if g_idx >= 0:
                    rows.append(g_idx); cols.append(g_idx); data.append(Gmin)
                if s_idx >= 0:
                    rows.append(s_idx); cols.append(s_idx); data.append(Gmin)
                if g_idx >= 0 and s_idx >= 0:
                    rows.append(g_idx); cols.append(s_idx); data.append(-Gmin)
                    rows.append(s_idx); cols.append(g_idx); data.append(-Gmin)
                    
                # Gmin Drain-Source (Critical for Cutoff floating nodes)
                if d_idx >= 0:
                    rows.append(d_idx); cols.append(d_idx); data.append(Gmin)
                if s_idx >= 0:
                    rows.append(s_idx); cols.append(s_idx); data.append(Gmin)
                if d_idx >= 0 and s_idx >= 0:
                    rows.append(d_idx); cols.append(s_idx); data.append(-Gmin)
                    rows.append(s_idx); cols.append(d_idx); data.append(-Gmin)
                    
                if d_idx >= 0:
                    z_nl[d_idx, 0] -= Ieq
                    rows.append(d_idx); cols.append(d_idx); data.append(gds)
                    if s_idx >= 0:
                        rows.append(d_idx); cols.append(s_idx); data.append(-gds - gm)
                    if g_idx >= 0:
                        rows.append(d_idx); cols.append(g_idx); data.append(gm)
                        
                if s_idx >= 0:
                    z_nl[s_idx, 0] += Ieq
                    rows.append(s_idx); cols.append(s_idx); data.append(gds + gm)
                    if d_idx >= 0:
                        rows.append(s_idx); cols.append(d_idx); data.append(-gds)
                    if g_idx >= 0:
                        rows.append(s_idx); cols.append(g_idx); data.append(-gm)
                        
            elif isinstance(comp, MOSFET_P):
                # 1. Topological Pointers
                d_idx = self.node_to_idx[comp.drain]
                g_idx = self.node_to_idx[comp.gate]
                s_idx = self.node_to_idx[comp.source]
                
                # 2. Terminal Voltages
                v_d = x_prev[d_idx] if d_idx >= 0 else 0.0
                v_g = x_prev[g_idx] if g_idx >= 0 else 0.0
                v_s = x_prev[s_idx] if s_idx >= 0 else 0.0
                
                Vsg = v_s - v_g
                Vsd = v_s - v_d
                Vth_p = abs(comp.v_th) # Use absolute threshold conceptually
                
                Isd, gm, gds = 0.0, 0.0, 0.0
                
                # 3. Shichman-Hodges Regions
                if Vsg <= Vth_p:
                    # Cutoff
                    pass
                elif Vsd < Vsg - Vth_p:
                    # Linear / Triode
                    Vov = Vsg - Vth_p
                    Isd = comp.beta * (Vov * Vsd - 0.5 * Vsd**2) * (1 + comp.lambda_ * Vsd)
                    gm = comp.beta * Vsd * (1 + comp.lambda_ * Vsd)
                    gds = comp.beta * (Vov - Vsd) * (1 + comp.lambda_ * Vsd) + comp.beta * (Vov * Vsd - 0.5 * Vsd**2) * comp.lambda_
                else:
                    # Saturation
                    Vov = Vsg - Vth_p
                    # Hard limit for NR stability
                    Vov = min(Vov, 20.0) 
                    Isd = 0.5 * comp.beta * Vov**2 * (1 + comp.lambda_ * Vsd)
                    gm = comp.beta * Vov * (1 + comp.lambda_ * Vsd)
                    gds = 0.5 * comp.beta * Vov**2 * comp.lambda_
                
                # 4. Equivalent Current for NR
                Ieq = Isd - gm * Vsg - gds * Vsd
                
                # 5. Math Mapping (Source to Drain injection)
                Gmin = 1e-12
                
                # Gmin Gate-Source
                if g_idx >= 0:
                    rows.append(g_idx); cols.append(g_idx); data.append(Gmin)
                if s_idx >= 0:
                    rows.append(s_idx); cols.append(s_idx); data.append(Gmin)
                if g_idx >= 0 and s_idx >= 0:
                    rows.append(g_idx); cols.append(s_idx); data.append(-Gmin)
                    rows.append(s_idx); cols.append(g_idx); data.append(-Gmin)
                    
                # Gmin Drain-Source
                if d_idx >= 0:
                    rows.append(d_idx); cols.append(d_idx); data.append(Gmin)
                if s_idx >= 0:
                    rows.append(s_idx); cols.append(s_idx); data.append(Gmin)
                if d_idx >= 0 and s_idx >= 0:
                    rows.append(d_idx); cols.append(s_idx); data.append(-Gmin)
                    rows.append(s_idx); cols.append(d_idx); data.append(-Gmin)
                    
                if s_idx >= 0:
                    z_nl[s_idx, 0] -= Ieq
                    rows.append(s_idx); cols.append(s_idx); data.append(gds + gm)
                    if d_idx >= 0:
                        rows.append(s_idx); cols.append(d_idx); data.append(-gds)
                    if g_idx >= 0:
                        rows.append(s_idx); cols.append(g_idx); data.append(-gm)
                        
                if d_idx >= 0:
                    z_nl[d_idx, 0] += Ieq
                    rows.append(d_idx); cols.append(d_idx); data.append(gds)
                    if s_idx >= 0:
                        rows.append(d_idx); cols.append(s_idx); data.append(-gds - gm)
                    if g_idx >= 0:
                        rows.append(d_idx); cols.append(g_idx); data.append(gm)
                    
        A_nl = csr_matrix((data, (rows, cols)), shape=(size, size), dtype=float)
        return A_nl, z_nl

    def stamp_ac(self, freq_hz: float) -> Tuple[lil_matrix, np.ndarray]:
        """Constructs the Small-Signal Frequency Domain complex matrix.
        
        Evaluates purely linear AC response by computing phasors and complex 
        admittances globally (without Newton-Raphson).
        
        Args:
            freq_hz: Frequency of the current AC sweep step.
            
        Returns:
            Tuple containing the A complex matrix (as lil_matrix) and RHS z vector (ndarray).
        """
        self._allocate_memory()
        
        # Override structural precision to support complex phases natively
        A_ac = lil_matrix((self.size, self.size), dtype=np.complex128)
        z_ac = np.zeros((self.size, 1), dtype=np.complex128)
        
        omega = 2.0 * np.pi * freq_hz
        
        for comp in self.circuit.get_components():
            # Linear Passive Components Admittance Mapping (Y)
            Y: complex = 0.0 + 0.0j
            
            if isinstance(comp, Resistor):
                Y = 1.0 / comp.resistance
            elif isinstance(comp, Capacitor):
                Y = 1j * omega * comp.capacitance
            elif isinstance(comp, Inductor):
                # Avoid ZeroDivision Error for purely DC sweep starts (freq=0)
                if omega == 0.0:
                    Y = 1.0 / (1j * 1e-12 * comp.inductance)
                else:
                    Y = 1.0 / (1j * omega * comp.inductance)
                    
            if isinstance(comp, (Resistor, Capacitor)):
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                # Standard Y-Matrix Formulation
                if n1_idx >= 0:
                    A_ac[n1_idx, n1_idx] += Y
                if n2_idx >= 0:
                    A_ac[n2_idx, n2_idx] += Y
                    
                if n1_idx >= 0 and n2_idx >= 0:
                    A_ac[n1_idx, n2_idx] -= Y
                    A_ac[n2_idx, n1_idx] -= Y
                    
            elif isinstance(comp, Inductor):
                # Auxiliary branch representation for complex admittance
                # Vp - Vn - jwL * IL = 0
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

            # Macromodels and Independent Sources
            elif isinstance(comp, OpAmp):
                # Equivalent to linear static stamping (Gain is Real scalar transfer)
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
                # DC Voltage sources provide structural basis but zero AC bias (short circuit effectively)
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, k] += 1.0
                    A_ac[k, n1_idx] += 1.0
                if n2_idx >= 0:
                    A_ac[n2_idx, k] -= 1.0
                    A_ac[k, n2_idx] -= 1.0
                    
                z_ac[k, 0] = 0.0 # Zero small signal AC magnitude
                
            elif isinstance(comp, ACVoltageSource):
                # Map Phasor amplitude and phase properties structurally
                k = self.n + self.vsrc_to_idx[comp.name]
                n1_idx = self.node_to_idx[comp.node1]
                n2_idx = self.node_to_idx[comp.node2]
                
                if n1_idx >= 0:
                    A_ac[n1_idx, k] += 1.0
                    A_ac[k, n1_idx] += 1.0
                if n2_idx >= 0:
                    A_ac[n2_idx, k] -= 1.0
                    A_ac[k, n2_idx] -= 1.0
                    
                # Euler's representation: V_phasor = Mag * exp(j * Phase)
                phasor = comp.ac_mag * np.exp(1j * np.radians(comp.ac_phase))
                z_ac[k, 0] = phasor

        return A_ac, z_ac

    def stamp_transient_basis(self, A_clone: lil_matrix, dt: float) -> None:
        """Stamps pure linear structural basis components of time-differentiated elements (L, C).
        
        This matrix is structural and decoupled from instantaneous time variables. 
        It MUST be stamped exactly ONCE before the transient exterior loop (`while t <= t_stop`)
        since L and C conductances (Geq) are constant for a fixed `dt`.
        
        Parameters:
            A_clone: The mutable cloned iteration of the Jacobian LIL matrix to add basis.
            dt: Time step differential controlling Geq derivations.
        """
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Capacitor):
                # Backward Euler: Geq = C / dt
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
                # Backward Euler: Geq = dt / L over Auxiliary Branch
                k = self.n + self.vsrc_to_idx[comp.name]
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                
                # Undo DC zero-resistance short-circuit established in stamp_linear
                if i_idx >= 0:
                    A_clone[i_idx, k] += 1.0
                    A_clone[k, i_idx] += 1.0 # Base voltage definition retains +/-1 logic
                if j_idx >= 0:
                    A_clone[j_idx, k] -= 1.0
                    A_clone[k, j_idx] -= 1.0
                    
                # Add diagonal resistance definition: V_p - V_n - (L/dt) i_n = ...
                A_clone[k, k] += (-comp.inductance / dt)

    def stamp_transient_sources(self, z_clone: np.ndarray, dt: float, x_prev: np.ndarray) -> None:
        """Stamps non-linear internal states elements (L, C histories) into cloned Vectors per-timestep.
        
        Using the Backward Euler Method:
        - Capacitor (Ieq = Geq * V_prev)
        - Inductor (Ieq = i_prev)
        
        This occurs EVERY outer time loop step but does NOT deform structural A_matrix representations.
        
        Parameters:
            z_clone: The mutable cloned iteration of the RHS vector.
            dt: Time step differential.
            x_prev: The numerical physical state historically accepted from the previous iteration.
        """
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Capacitor):
                Geq = comp.capacitance / dt
                
                i_idx = self.node_to_idx[comp.node1]
                j_idx = self.node_to_idx[comp.node2]
                
                v_i = x_prev[i_idx] if i_idx >= 0 else 0.0
                v_j = x_prev[j_idx] if j_idx >= 0 else 0.0
                V_prev = v_i - v_j
                
                # Injects Memory
                Ieq = Geq * V_prev
                if i_idx >= 0:
                    z_clone[i_idx, 0] += Ieq
                if j_idx >= 0:
                    z_clone[j_idx, 0] -= Ieq
                    
            elif isinstance(comp, Inductor):
                k = self.n + self.vsrc_to_idx[comp.name]
                
                # Injects Memory to the auxiliary dimension RHS
                # RHS: - (L/dt) * i_{n-1}
                Ieq = -(comp.inductance / dt) * comp.i_prev
                z_clone[k, 0] += Ieq

    def update_states(self, x_converged: np.ndarray, dt: float) -> None:
        """Synchronizes and progresses physics-level components internal memory (Backward Euler integration).
        Called strictly AFTER full iteration Newton-Raphson nonlinear convergence mathematically occurs inside the solver.
        
        Parameters:
            x_converged: Fully relaxed physical equilibrium values per given `t` increment.
            dt: Timestep differential for derivation scaling.
        """
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, Inductor):
                # Retrieve the solved exact auxiliary current scalar from the numerical array
                k = self.n + self.vsrc_to_idx[comp.name]
                i_L = x_converged[k]
                
                # Register internal state
                comp.i_prev = float(i_L)

    def stamp_dynamic_sources(self, z_clone: np.ndarray, t: float) -> None:
        """Stamps dynamic time-varying sources into the cloned RHS vector.
        
        Evaluates functions like get_voltage(t) at the current simulation time 't' 
        and updates the corresponding vector slots before numerical solution.
        
        Parameters:
            z_clone: Mutable RHS vector for the current time step.
            t: Instantaneous time in seconds.
        """
        components = self.circuit.get_components()
        for comp in components:
            if isinstance(comp, ACVoltageSource):
                k = self.n + self.vsrc_to_idx[comp.name]
                # Inject the instantaneous wave value evaluated exactly at 't'
                z_clone[k, 0] = comp.get_voltage(t)
