"""
test_mna_vs_ltspice.py — Cross-validation: MNA solver vs LTspice reference.

Runs the same circuit through both backends and compares DC, AC, and transient
results within engineering tolerances.
"""

import os
import pytest
import numpy as np

from solver_sch.model.circuit import (
    Circuit, Resistor, Capacitor, Inductor,
    VoltageSource, ACVoltageSource, CurrentSource,
    Diode, BJT, BJT_P, MOSFET_N, OpAmp,
)
from solver_sch.model.components import ModelCard
from solver_sch.simulator import Simulator
from solver_sch.parser.netlist_parser import NetlistParser


# ── Tolerances ────────────────────────────────────────────────────────────────
DC_TOL_PCT = 2.0       # 2% for DC node voltages
AC_MAG_TOL_DB = 1.0    # 1 dB for AC magnitude
AC_PHASE_TOL = 5.0     # 5 degrees for AC phase
TRAN_TOL_PCT = 5.0     # 5% for transient waveforms

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_both(circuit, analysis, **kwargs):
    """Run both MNA and LTspice backends, return (mna_result, lt_result)."""
    sim_mna = Simulator(circuit, validate_on_init=False, backend="mna")
    sim_lt = Simulator(circuit, validate_on_init=False, backend="ltspice")
    mna_result = getattr(sim_mna, analysis)(**kwargs)
    lt_result = getattr(sim_lt, analysis)(**kwargs)
    return mna_result, lt_result


def _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT, skip_ground=True):
    """Assert DC node voltages match within tolerance."""
    errors = {}
    for node, v_mna in dc_mna.node_voltages.items():
        if skip_ground and node == "0":
            continue
        v_lt = dc_lt.node_voltages.get(node, None)
        if v_lt is None:
            continue
        if abs(v_lt) < 0.01:
            # Near-zero: use absolute tolerance
            err = abs(v_mna - v_lt)
            assert err < 0.05, f"DC {node}: MNA={v_mna:.4f} LT={v_lt:.4f} abs_err={err:.4f}"
        else:
            err_pct = abs(v_mna - v_lt) / abs(v_lt) * 100
            errors[node] = err_pct
            assert err_pct < tol_pct, (
                f"DC {node}: MNA={v_mna:.4f}V LT={v_lt:.4f}V err={err_pct:.2f}% > {tol_pct}%"
            )
    return errors


def _assert_ac_match(ac_mna, ac_lt, node, tol_db=AC_MAG_TOL_DB, tol_phase=AC_PHASE_TOL):
    """Assert AC Bode data matches for a specific node."""
    r_mna = ac_mna.nodes[node]
    r_lt = ac_lt.nodes[node]
    n_pts = min(len(r_mna.magnitude_db), len(r_lt.magnitude_db))
    for i in range(n_pts):
        db_err = abs(r_mna.magnitude_db[i] - r_lt.magnitude_db[i])
        ph_err = abs(r_mna.phase_deg[i] - r_lt.phase_deg[i])
        # Wrap phase difference
        if ph_err > 180:
            ph_err = 360 - ph_err
        f = ac_mna.frequencies[i] if i < len(ac_mna.frequencies) else 0
        assert db_err < tol_db, (
            f"AC {node}@{f:.0f}Hz: mag err={db_err:.2f}dB > {tol_db}dB "
            f"(MNA={r_mna.magnitude_db[i]:.2f} LT={r_lt.magnitude_db[i]:.2f})"
        )
        # Only check phase where signal is significant (> -40 dB)
        if r_mna.magnitude_db[i] > -40 and r_lt.magnitude_db[i] > -40:
            assert ph_err < tol_phase, (
                f"AC {node}@{f:.0f}Hz: phase err={ph_err:.1f}° > {tol_phase}° "
                f"(MNA={r_mna.phase_deg[i]:.1f} LT={r_lt.phase_deg[i]:.1f})"
            )


# ── Test 1: RC Low-Pass Filter (DC + AC) ─────────────────────────────────────

def test_rc_lowpass_dc_ac():
    """RC low-pass: R=1k, C=1uF → fc=159Hz. Validates linear AC baseline."""
    ckt = Circuit("RC LPF Crossval", ground_name="0")
    ckt.add_component(ACVoltageSource(
        "Vin", "in", "0",
        dc_offset=0.0, amplitude=0.0, frequency=0.0,
        ac_mag=1.0, ac_phase=0.0,
    ))
    ckt.add_component(Resistor("R1", "in", "out", 1000.0))
    ckt.add_component(Capacitor("C1", "out", "0", 1e-6))

    # DC
    dc_mna, dc_lt = _run_both(ckt, "dc")
    _assert_dc_match(dc_mna, dc_lt)

    # AC
    ac_mna, ac_lt = _run_both(ckt, "ac", f_start=10, f_stop=100e3, points_per_decade=10)
    _assert_ac_match(ac_mna, ac_lt, "out")

    # Verify -3dB point near 159 Hz
    fc_expected = 1.0 / (2 * np.pi * 1000 * 1e-6)  # 159.15 Hz
    r = ac_mna.nodes["out"]
    midband_db = r.magnitude_db[0]  # low-frequency gain
    for i, f in enumerate(ac_mna.frequencies):
        if r.magnitude_db[i] < midband_db - 3.0:
            assert abs(f - fc_expected) / fc_expected < 0.3, (
                f"fc={f:.0f}Hz expected ~{fc_expected:.0f}Hz"
            )
            break


# ── Test 2: Series RLC Bandpass (AC) ──────────────────────────────────────────

def test_rlc_bandpass_ac():
    """Series RLC: R=100, L=10mH, C=100nF → f0≈5033Hz. Validates inductor AC."""
    ckt = Circuit("RLC BPF Crossval", ground_name="0")
    ckt.add_component(ACVoltageSource(
        "Vin", "in", "0",
        dc_offset=0.0, amplitude=0.0, frequency=0.0,
        ac_mag=1.0, ac_phase=0.0,
    ))
    ckt.add_component(Resistor("R1", "in", "n1", 100.0))
    ckt.add_component(Inductor("L1", "n1", "out", 10e-3))
    ckt.add_component(Capacitor("C1", "out", "0", 100e-9))

    ac_mna, ac_lt = _run_both(ckt, "ac", f_start=100, f_stop=100e3, points_per_decade=20)

    # Check voltage across R (= current * R), which is the "out" node voltage
    # Actually, "out" is between L and C. Let's check node "n1" or "out".
    # For series RLC driven by voltage source, V(out) = voltage across C.
    _assert_ac_match(ac_mna, ac_lt, "out", tol_db=AC_MAG_TOL_DB)

    # Verify resonance peak exists near f0 = 1/(2*pi*sqrt(LC))
    f0_expected = 1.0 / (2 * np.pi * np.sqrt(10e-3 * 100e-9))  # ~5033 Hz
    r = ac_mna.nodes["out"]
    peak_idx = np.argmax(r.magnitude_db)
    peak_freq = ac_mna.frequencies[peak_idx]
    assert abs(peak_freq - f0_expected) / f0_expected < 0.15, (
        f"Resonance peak at {peak_freq:.0f}Hz, expected ~{f0_expected:.0f}Hz"
    )


# ── Test 3: Diode Half-Wave Rectifier (DC + Transient) ───────────────────────

def test_diode_rectifier_dc_tran():
    """Half-wave rectifier: validates diode nonlinear in DC and transient."""
    ckt = Circuit("Diode Rectifier Crossval", ground_name="0")
    model = ModelCard("1N4148", "D", {"Is": "2.52n", "N": "1.752"})
    ckt.add_model(model)
    ckt.add_component(ACVoltageSource(
        "Vin", "in", "0",
        dc_offset=0.0, amplitude=5.0, frequency=1000.0,
        ac_mag=1.0, ac_phase=0.0,
    ))
    ckt.add_component(Diode("D1", "in", "out", model="1N4148"))
    ckt.add_component(Resistor("R1", "out", "0", 1000.0))

    # DC: with DC offset=0, diode off, V(out) ≈ 0
    dc_mna, dc_lt = _run_both(ckt, "dc")
    assert abs(dc_mna.node_voltages.get("out", 0)) < 0.1
    assert abs(dc_lt.node_voltages.get("out", 0)) < 0.1

    # Transient: half-wave rectified sine
    tr_mna, tr_lt = _run_both(ckt, "transient", t_stop=2e-3, dt=10e-6)

    # Compare peak output voltage (should be ~4.3V = 5V - Vf)
    data_mna = tr_mna.voltages_at("out")
    data_lt = tr_lt.voltages_at("out")
    peak_mna = max(data_mna["voltage"])
    peak_lt = max(data_lt["voltage"])
    assert abs(peak_mna - peak_lt) / max(abs(peak_lt), 0.1) < TRAN_TOL_PCT / 100, (
        f"Transient peak: MNA={peak_mna:.3f}V LT={peak_lt:.3f}V"
    )
    # Peak should be roughly 5V - 0.7V = 4.3V (forward drop)
    assert 3.5 < peak_mna < 5.0, f"Peak voltage {peak_mna:.2f}V out of expected range"


# ── Test 4: BJT Common-Emitter Amplifier (DC + AC) ───────────────────────────

def test_bjt_ce_amp_dc_ac():
    """BJT CE amp from bjt_ce_amp.cir: validates BJT linearization."""
    cir_path = os.path.join(os.path.dirname(__file__), "..", "bjt_ce_amp.cir")
    if not os.path.exists(cir_path):
        pytest.skip("bjt_ce_amp.cir not found")

    with open(cir_path) as f:
        text = f.read()

    circuit = NetlistParser.parse_netlist(text)

    # DC
    dc_mna, dc_lt = _run_both(circuit, "dc")
    errors = _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT)

    # Verify expected DC bias points
    assert 1.4 < dc_mna.node_voltages["base"] < 1.8, "VB out of range"
    assert 6.5 < dc_mna.node_voltages["col"] < 9.0, "VC out of range"
    assert 0.7 < dc_mna.node_voltages["emitter"] < 1.1, "VE out of range"

    # AC
    ac_mna, ac_lt = _run_both(circuit, "ac", f_start=10, f_stop=1e6, points_per_decade=10)
    _assert_ac_match(ac_mna, ac_lt, "out_node", tol_db=AC_MAG_TOL_DB)
    _assert_ac_match(ac_mna, ac_lt, "col", tol_db=AC_MAG_TOL_DB)

    # Mid-band gain should be ~42 dB (≈ -gm * RC || RL)
    r = ac_mna.nodes["out_node"]
    midband_db = max(r.magnitude_db)
    assert 38 < midband_db < 46, f"Mid-band gain {midband_db:.1f}dB, expected ~42dB"


# ── Test 5: NMOS Common-Source Amplifier (DC + AC) ────────────────────────────

def test_mosfet_cs_amp_dc_ac():
    """NMOS CS amp: validates MOSFET AC linearization."""
    ckt = Circuit("NMOS CS Amp Crossval", ground_name="0")

    # Model card for consistent parameters between MNA and LTspice
    nmos_model = ModelCard("NMOS_CS", "NMOS", {
        "Kp": "250e-6", "Vto": "0.7", "Lambda": "0.01",
    })
    ckt.add_model(nmos_model)

    # Supply
    ckt.add_component(VoltageSource("VDD", "vdd", "0", 5.0))

    # Bias: voltage divider to set Vgs ≈ 1.5V
    ckt.add_component(Resistor("R1", "vdd", "gate", 100e3))
    ckt.add_component(Resistor("R2", "gate", "0", 47e3))

    # MOSFET
    ckt.add_component(MOSFET_N(
        "M1", "drain", "gate", "source",
        w=10e-6, l=1e-6, v_th=0.7, k_p=250e-6, lambda_=0.01,
        model="NMOS_CS",
    ))

    # Drain resistor and source degeneration
    ckt.add_component(Resistor("RD", "vdd", "drain", 2200.0))
    ckt.add_component(Resistor("RS", "source", "0", 470.0))

    # AC input coupling
    ckt.add_component(Capacitor("Cin", "ac_in", "gate", 10e-6))
    ckt.add_component(ACVoltageSource(
        "Vin", "ac_in", "0",
        dc_offset=0.0, amplitude=0.0, frequency=0.0,
        ac_mag=1.0, ac_phase=0.0,
    ))

    # Output coupling + load
    ckt.add_component(Capacitor("Cout", "drain", "out", 10e-6))
    ckt.add_component(Resistor("RL", "out", "0", 10e3))

    # DC
    dc_mna, dc_lt = _run_both(ckt, "dc")
    _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT)

    # Verify MOSFET is in saturation: Vds > Vgs - Vth
    vg = dc_mna.node_voltages["gate"]
    vs = dc_mna.node_voltages["source"]
    vd = dc_mna.node_voltages["drain"]
    vgs = vg - vs
    vds = vd - vs
    assert vgs > 0.7, f"MOSFET off: Vgs={vgs:.2f}V < Vth=0.7V"
    assert vds > vgs - 0.7, f"MOSFET in triode: Vds={vds:.2f}V < Vov={vgs-0.7:.2f}V"

    # AC
    ac_mna, ac_lt = _run_both(ckt, "ac", f_start=10, f_stop=1e6, points_per_decade=10)
    _assert_ac_match(ac_mna, ac_lt, "out", tol_db=AC_MAG_TOL_DB)


# ── Test 6: OpAmp Inverting Amplifier (DC) ────────────────────────────────────

def test_opamp_inverting_dc():
    """OpAmp inverting amp: Av=-10. Validates VCVS model accuracy."""
    ckt = Circuit("OpAmp Inv Crossval", ground_name="0")

    # Input: 1V DC
    ckt.add_component(VoltageSource("Vin", "in", "0", 1.0))

    # Feedback network: Rin=1k, Rf=10k → Av = -Rf/Rin = -10
    ckt.add_component(Resistor("Rin", "in", "inv", 1000.0))
    ckt.add_component(Resistor("Rf", "inv", "out", 10000.0))

    # OpAmp: non-inverting input to ground, gain=100000
    ckt.add_component(OpAmp("U1", "0", "inv", "out", gain=100000))

    # DC
    dc_mna, dc_lt = _run_both(ckt, "dc")
    _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT)

    # Verify gain: Vout should be approximately -10V
    v_out = dc_mna.node_voltages["out"]
    assert abs(v_out - (-10.0)) < 0.1, f"Vout={v_out:.4f}V, expected -10.0V"


# ── Test 7: signoff.cir File Parse + Cross-Validation ─────────────────────────

def test_signoff_cir_parsed():
    """Parse signoff.cir (OpAmp inverting amp) and cross-validate MNA vs LTspice."""
    cir_path = os.path.join(os.path.dirname(__file__), "..", "signoff.cir")
    if not os.path.exists(cir_path):
        pytest.skip("signoff.cir not found")

    with open(cir_path) as f:
        text = f.read()

    circuit = NetlistParser.parse_netlist(text)

    # DC
    dc_mna, dc_lt = _run_both(circuit, "dc")
    _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT)

    # Non-inverting amp: Av = 1 + Rf/Rg = 1 + 10k/1k = 11, Vin=1V → Vout ≈ 11V
    v_out = dc_mna.node_voltages.get("out", 0)
    assert abs(v_out - 11.0) < 0.2, f"Vout={v_out:.4f}V, expected 11.0V"


# ── Test 8: PNP Emitter Follower (DC + AC) ────────────────────────────────────

def test_pnp_emitter_follower_dc_ac():
    """PNP emitter follower: validates PNP BJT polarity support."""
    ckt = Circuit("PNP Emitter Follower Crossval", ground_name="0")

    pnp_model = ModelCard("PNP_TEST", "PNP", {"Is": "1e-14", "Bf": "100", "Br": "1"})
    ckt.add_model(pnp_model)

    # Negative supply
    ckt.add_component(VoltageSource("VEE", "0", "vee", 12.0))  # VEE = -12V

    # Bias: voltage divider to set base voltage
    ckt.add_component(Resistor("R1", "0", "base", 47e3))
    ckt.add_component(Resistor("R2", "base", "vee", 100e3))

    # PNP BJT: emitter follower configuration
    # PNP: E=emitter (output, goes to load), B=base, C=collector (to VEE)
    ckt.add_component(BJT_P("Q1", "vee", "base", "emitter", model="PNP_TEST"))

    # Emitter load resistor
    ckt.add_component(Resistor("RE", "emitter", "0", 2200.0))

    # AC input coupling
    ckt.add_component(Capacitor("Cin", "ac_in", "base", 10e-6))
    ckt.add_component(ACVoltageSource(
        "Vin", "ac_in", "0",
        dc_offset=0.0, amplitude=0.0, frequency=0.0,
        ac_mag=1.0, ac_phase=0.0,
    ))

    # Output coupling + load
    ckt.add_component(Capacitor("Cout", "emitter", "out", 10e-6))
    ckt.add_component(Resistor("RL", "out", "0", 10e3))

    # DC
    dc_mna, dc_lt = _run_both(ckt, "dc")
    _assert_dc_match(dc_mna, dc_lt, tol_pct=DC_TOL_PCT)

    # Verify PNP is active: Veb > 0 (emitter more positive than base)
    v_b = dc_mna.node_voltages["base"]
    v_e = dc_mna.node_voltages["emitter"]
    veb = v_e - v_b  # PNP: Veb should be positive (~0.7V)
    assert veb > 0.3, f"PNP not active: Veb={veb:.3f}V (expected > 0.3V)"
    assert veb < 1.0, f"PNP Veb too high: Veb={veb:.3f}V"

    # AC
    ac_mna, ac_lt = _run_both(ckt, "ac", f_start=10, f_stop=1e6, points_per_decade=10)
    _assert_ac_match(ac_mna, ac_lt, "out", tol_db=2.0)
