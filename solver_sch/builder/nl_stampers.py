"""
nl_stampers.py -> Nonlinear Companion Model Stamping Functions.

Standalone functions implementing Newton-Raphson linearized companion models
for nonlinear components: Diode, BJT, MOSFET_N, MOSFET_P, Comparator.

Each function receives the component, the previous solution vector, the
nonlinear RHS/matrix accumulators, and the node/source index maps from
MNAStamper. This decouples the physics math from the MNAStamper class state.
"""

from typing import Callable, Dict, List

import numpy as np

from solver_sch.constants import GMIN
from solver_sch.model.components import (
    BJT, Comparator, Diode, MOSFET_N, MOSFET_P,
)


def stamp_diode_nl(
    comp: Diode,
    x_prev: np.ndarray,
    z_nl: np.ndarray,
    rows: List[int],
    cols: List[int],
    data: List[float],
    node_to_idx: Dict[str, int],
    get_v: Callable[[int, np.ndarray], float],
) -> None:
    """Stamp the linearized Shockley diode companion model."""
    anode_idx = node_to_idx[comp.node1]
    cathode_idx = node_to_idx[comp.node2]

    v_anode = get_v(anode_idx, x_prev)
    v_cathode = get_v(cathode_idx, x_prev)
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


def stamp_bjt_nl(
    comp: BJT,
    x_prev: np.ndarray,
    z_nl: np.ndarray,
    rows: List[int],
    cols: List[int],
    data: List[float],
    node_to_idx: Dict[str, int],
    get_v: Callable[[int, np.ndarray], float],
) -> None:
    """Stamp the linearized Ebers-Moll BJT companion model."""
    c_idx = node_to_idx[comp.collector]
    b_idx = node_to_idx[comp.base]
    e_idx = node_to_idx[comp.emitter]

    v_c = get_v(c_idx, x_prev)
    v_b = get_v(b_idx, x_prev)
    v_e = get_v(e_idx, x_prev)

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
    Ieq_e = Ie - (-(g_be + g_ce) * Vbe_safe + g_ec * Vbc_safe)

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


def stamp_mosfet_nl(
    comp: "MOSFET_N | MOSFET_P",
    x_prev: np.ndarray,
    z_nl: np.ndarray,
    rows: List[int],
    cols: List[int],
    data: List[float],
    node_to_idx: Dict[str, int],
    get_v: Callable[[int, np.ndarray], float],
) -> None:
    """Stamp the linearized Shichman-Hodges MOSFET companion model (unified NMOS/PMOS).

    Uses comp._polarity: +1 for NMOS (Vgs/Vds convention), -1 for PMOS (Vsg/Vsd convention).
    """
    p = comp._polarity  # +1 NMOS, -1 PMOS
    d_idx = node_to_idx[comp.drain]
    g_idx = node_to_idx[comp.gate]
    s_idx = node_to_idx[comp.source]

    v_d = get_v(d_idx, x_prev)
    v_g = get_v(g_idx, x_prev)
    v_s = get_v(s_idx, x_prev)

    # V1 = Vgs (NMOS) or Vsg (PMOS); V2 = Vds (NMOS) or Vsd (PMOS)
    V1 = p * (v_g - v_s)
    V2 = p * (v_d - v_s)
    Vth = abs(comp.v_th)
    I_main, gm, gds = 0.0, 0.0, 0.0

    if V1 <= Vth:
        pass
    elif V2 < V1 - Vth:
        Vov = V1 - Vth
        I_main = comp.beta * (Vov * V2 - 0.5 * V2**2) * (1 + comp.lambda_ * V2)
        gm = comp.beta * V2 * (1 + comp.lambda_ * V2)
        gds = comp.beta * (Vov - V2) * (1 + comp.lambda_ * V2) + comp.beta * (Vov * V2 - 0.5 * V2**2) * comp.lambda_
    else:
        Vov = min(V1 - Vth, 20.0)
        I_main = 0.5 * comp.beta * Vov**2 * (1 + comp.lambda_ * V2)
        gm = comp.beta * Vov * (1 + comp.lambda_ * V2)
        gds = 0.5 * comp.beta * Vov**2 * comp.lambda_

    Ieq = I_main - gm * V1 - gds * V2
    _apply_fet_matrix_stamp(d_idx, g_idx, s_idx, gm, gds, Ieq, rows, cols, data, z_nl, current_leaves_drain=(p == 1))


def stamp_comparator_nl(
    comp: Comparator,
    x_prev: np.ndarray,
    z_nl: np.ndarray,
    rows: List[int],
    cols: List[int],
    data: List[float],
    node_to_idx: Dict[str, int],
    get_v: Callable[[int, np.ndarray], float],
    vcvs_to_idx: Dict[str, int],
    n: int,
) -> None:
    """Stamp the linearized tanh-based Comparator companion model."""
    k = n + vcvs_to_idx[comp.name]
    p_idx = node_to_idx[comp.node_p]
    n_idx = node_to_idx[comp.node_n]

    v_p = get_v(p_idx, x_prev)
    v_n = get_v(n_idx, x_prev)

    V_diff = v_p - v_n
    tanh_val = np.tanh(comp.k * V_diff)
    V_out_val = comp.v_low + ((comp.v_high - comp.v_low) / 2.0) * (1.0 + tanh_val)
    f_prime = ((comp.v_high - comp.v_low) / 2.0) * comp.k * (1.0 - (tanh_val ** 2))

    z_nl[k, 0] += V_out_val - (f_prime * V_diff)
    if p_idx >= 0:
        rows.append(k); cols.append(p_idx); data.append(-f_prime)
    if n_idx >= 0:
        rows.append(k); cols.append(n_idx); data.append(f_prime)


def _apply_fet_matrix_stamp(
    d_idx: int,
    g_idx: int,
    s_idx: int,
    gm: float,
    gds: float,
    Ieq: float,
    rows: List[int],
    cols: List[int],
    data: List[float],
    z_nl: np.ndarray,
    current_leaves_drain: bool = True,
) -> None:
    """Shared Jacobian stamp for NMOS (current_leaves_drain=True) and PMOS (False).

    Using unified Jacobian entries for FETs where:
    - gm links Gate to Source.
    - gds links Drain to Source.
    """
    # 1. GMIN injections to prevent floating nodes and singular matrices
    if g_idx >= 0:
        rows.append(g_idx); cols.append(g_idx); data.append(GMIN)
        if s_idx >= 0:
            rows.append(g_idx); cols.append(s_idx); data.append(-GMIN)
    if s_idx >= 0:
        rows.append(s_idx); cols.append(s_idx); data.append(GMIN)
        if g_idx >= 0:
            rows.append(s_idx); cols.append(g_idx); data.append(-GMIN)
        if d_idx >= 0:
            rows.append(s_idx); cols.append(d_idx); data.append(-GMIN)
    if d_idx >= 0:
        rows.append(d_idx); cols.append(d_idx); data.append(GMIN)
        if s_idx >= 0:
            rows.append(d_idx); cols.append(s_idx); data.append(-GMIN)

    # 2. RHS contribution
    if current_leaves_drain:  # NMOS: Id flows D -> S
        if d_idx >= 0: z_nl[d_idx, 0] -= Ieq
        if s_idx >= 0: z_nl[s_idx, 0] += Ieq
    else:  # PMOS: Isd flows S -> D
        if s_idx >= 0: z_nl[s_idx, 0] -= Ieq
        if d_idx >= 0: z_nl[d_idx, 0] += Ieq

    # 3. Jacobian entries
    if d_idx >= 0:
        rows.append(d_idx); cols.append(d_idx); data.append(gds)
        if s_idx >= 0: rows.append(d_idx); cols.append(s_idx); data.append(-gds - gm)
        if g_idx >= 0: rows.append(d_idx); cols.append(g_idx); data.append(gm)

    if s_idx >= 0:
        rows.append(s_idx); cols.append(s_idx); data.append(gds + gm)
        if d_idx >= 0: rows.append(s_idx); cols.append(d_idx); data.append(-gds)
        if g_idx >= 0: rows.append(s_idx); cols.append(g_idx); data.append(-gm)
