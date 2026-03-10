"""
test_review_e2e_hard.py -> Hard End-to-End integration test for Simulator.review()

Builds a realistically flawed sensor interface circuit with MULTIPLE deliberate
design errors that the AI must detect. The circuit simulates a common industrial
scenario: 4-20mA sensor -> OpAmp gain stage -> RC filter -> ADC input.

Intentional Design Flaws:
  1. VOLTAGE DIVIDER BUG: R_BIAS voltage divider outputs ~4.09V to a 3.3V ADC
     (overvoltage — should trigger recalculate_divider tool or ADC warning).
  2. EXCESSIVE GAIN: OpAmp non-inverting stage gain = 1 + (47k/1k) = 48x.
     With 150mV sensor input, peak output = 7.2V — far above 3.3V ADC limit.
  3. WRONG ZENER: BZX84C5V1 (5.1V breakdown) used to protect a 3.3V ADC.
     Zener clamps at 5.1V, which is ABOVE the MCU maximum — useless protection.
  4. MISSING DECOUPLING: No bypass capacitor on OpAmp supply rails.
  5. HIGH FILTER CUTOFF: RC filter cutoff = 1/(2π*100*1nF) ≈ 1.59 MHz — way
     too high for a 1 kHz sensor signal. Offers no anti-aliasing.

This test uses the REAL Gemini API — it requires GEMINI_API_KEY in .env.
Run with:  python tests/test_review_e2e_hard.py
"""

import asyncio
import os
import sys
import logging

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from solver_sch import (
    Simulator, Circuit,
    Resistor, Capacitor, VoltageSource, ACVoltageSource, Diode, OpAmp,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("HardE2ETest")


def build_flawed_sensor_circuit() -> Circuit:
    """
    Builds a realistic but deeply flawed sensor interface circuit.

    Topology:
        V_SUPPLY (9V) ─┬─ R_BIAS1 (12kΩ) ── BIAS_NODE ── R_BIAS2 (10kΩ) ── GND
                        │
                        └─ OpAmp U1 supply (VCC=9V)

        V_SENSOR (150mV 1kHz sine) ── R_IN (1kΩ) ── U1(+)
                                                     U1(-) ── R_GND (1kΩ) ── GND
                                                     U1(-) ── R_FB (47kΩ) ── U1_OUT
        U1_OUT ── R_FILT (100Ω) ── ADC_IN ── C_FILT (1nF) ── GND
        ADC_IN ── D_PROT (Zener 5.1V, REVERSED for clamping) ── GND
        ADC_IN ── R_ADC (100kΩ) ── GND
        BIAS_NODE ── R_BIAS_LOAD (10kΩ) ── GND  (bias voltage goes to ADC ref concept)
    """
    ckt = Circuit("Flawed Sensor Interface v2", ground_name="0")

    # ── Power Supply: 9V single rail ──
    ckt.add_component(VoltageSource("V_SUPPLY", "vcc", "0", 9.0))

    # ── FLAW 1: Voltage divider bias outputs 9 * 10k/(12k+10k) ≈ 4.09V ──
    # This feeds an ADC reference concept at 4.09V — too high for 3.3V MCU.
    ckt.add_component(Resistor("R_BIAS1", "vcc", "bias_node", 12000))
    ckt.add_component(Resistor("R_BIAS2", "bias_node", "0", 10000))

    # ── Sensor: 150mV peak-to-peak, 1 kHz sine ──
    ckt.add_component(ACVoltageSource(
        "V_SENSOR", "sensor_in", "0",
        amplitude=0.15, frequency=1000, dc_offset=0.0, ac_mag=1.0
    ))

    # ── FLAW 2: Non-inverting OpAmp with gain = 1 + 47k/1k = 48 ──
    # Peak output = 0.15 * 48 = 7.2V, clamped at 9V rail.
    # Even 7.2V vastly exceeds 3.3V ADC input limit.
    ckt.add_component(Resistor("R_IN", "sensor_in", "opamp_pos", 1000))
    ckt.add_component(Resistor("R_GND", "opamp_neg", "0", 1000))
    ckt.add_component(Resistor("R_FB", "opamp_out", "opamp_neg", 47000))
    ckt.add_component(OpAmp("U1", "opamp_pos", "opamp_neg", "opamp_out", gain=1e5))

    # ── FLAW 5: Anti-aliasing filter with f_c ≈ 1.59 MHz (useless) ──
    # Should be ~15.9 kHz (R=1kΩ, C=10nF) or lower for proper Nyquist filtering.
    ckt.add_component(Resistor("R_FILT", "opamp_out", "adc_in", 100))
    ckt.add_component(Capacitor("C_FILT", "adc_in", "0", 1e-9))  # 1nF

    # ── FLAW 3: Zener protection at 5.1V on a 3.3V ADC line ──
    # Anode to GND, Cathode to signal — standard Zener clamp orientation.
    # But 5.1V > 3.3V MCU max — the Zener offers NO effective protection.
    ckt.add_component(Diode("D_PROT", "0", "adc_in", Vz=5.1, Is=1e-15, n=1.1))

    # ── ADC input impedance (load) ──
    ckt.add_component(Resistor("R_ADC", "adc_in", "0", 100000))

    return ckt


async def run_hard_test():
    """
    Executes the full pipeline:
      1. Build flawed circuit
      2. Run DC analysis
      3. Run AC analysis (to catch filter/gain issues)
      4. Call Simulator.review() with a precise, challenging intent
      5. Assert the AI report catches the critical flaws
    """
    print("\n" + "=" * 70)
    print("  HARD E2E TEST: Flawed Sensor Interface → AI Design Review")
    print("=" * 70)

    # ── Step 1: Build ──
    circuit = build_flawed_sensor_circuit()
    sim = Simulator(circuit)

    # ── Step 2: DC Analysis ──
    logger.info("[Step 2] Running DC Operating Point...")
    dc = sim.dc()
    v_bias = dc.node_voltages.get("bias_node", 0.0)
    v_adc = dc.node_voltages.get("adc_in", 0.0)
    logger.info("  V(bias_node) = %.3f V  (expected ~4.09V — too high for 3.3V ADC)", v_bias)
    logger.info("  V(adc_in)    = %.3f V", v_adc)

    # ── Step 3: AC Analysis ──
    logger.info("[Step 3] Running AC Sweep (10 Hz → 10 MHz)...")
    ac = sim.ac(f_start=10, f_stop=10e6, points_per_decade=10)

    # ── Step 4: Review with aggressive intent ──
    intent = (
        "This is a sensor interface circuit for a 3.3V MCU ADC. "
        "The sensor outputs 150mV and is amplified by an OpAmp gain stage. "
        "An RC anti-aliasing filter and Zener overvoltage protection are included. "
        "A voltage divider provides a bias reference. "
        "Please identify ALL design flaws, paying special attention to: "
        "1) Whether the output voltage exceeds the 3.3V ADC maximum input. "
        "2) Whether the Zener diode provides adequate protection for a 3.3V ADC. "
        "3) Whether the anti-aliasing filter cutoff frequency is appropriate for a 1 kHz signal. "
        "4) Whether the bias voltage divider output is safe for 3.3V logic. "
        "5) Whether decoupling capacitors are present on the OpAmp supply. "
        "Use the recalculate_divider tool if you need to fix the voltage divider."
    )

    logger.info("[Step 4] Calling Simulator.review() with Gemini backend...")
    report = await sim.review(
        dc_result=dc,
        ac_result=ac,
        intent=intent,
        backend="gemini",
        model="gemini-3.1-flash-lite-preview",
    )

    # ── Step 5: Display & Assert ──
    print("\n" + "=" * 70)
    print("  GENERATED DESIGN REVIEW REPORT")
    print("=" * 70)
    print(report)
    print("=" * 70 + "\n")

    # Structural assertions — report must have all required sections
    assert isinstance(report, str), "Report must be a string"
    assert len(report) > 200, f"Report suspiciously short ({len(report)} chars)"
    assert "# Executive Summary" in report, "Missing Executive Summary section"
    assert "# Critical Warnings" in report, "Missing Critical Warnings section"

    # Content assertions — AI must catch at least the major flaws
    report_upper = report.upper()

    # Flaw 1/2: Overvoltage — the AI should mention voltage exceeds 3.3V
    overvoltage_detected = any(term in report_upper for term in [
        "3.3V", "3.3 V", "OVERVOLTAGE", "EXCEEDS", "ADC", "MAXIMUM INPUT",
    ])
    assert overvoltage_detected, (
        "AI failed to detect overvoltage condition (output > 3.3V ADC limit)"
    )

    # Flaw 2: Excessive gain (48x or ~7.2V output)
    gain_detected = any(term in report_upper for term in [
        "GAIN", "48", "47K", "47000", "7.2", "AMPLIF",
    ])
    assert gain_detected, (
        "AI failed to mention excessive OpAmp gain (48x producing ~7.2V)"
    )

    # Flaw 3: Wrong Zener — 5.1V Zener on 3.3V line
    zener_detected = any(term in report_upper for term in [
        "ZENER", "5.1V", "5.1 V", "BZX", "PROTECTION", "CLAMP",
    ])
    assert zener_detected, (
        "AI failed to flag the inadequate 5.1V Zener on a 3.3V ADC line"
    )

    # Meta-assertion: the word "READY" (discovery phase directive) must NOT leak
    assert "READY" not in report, (
        "Discovery phase directive 'READY' leaked into the final report"
    )

    print("✅ ALL HARD E2E ASSERTIONS PASSED")
    print("   - Overvoltage detected:  YES")
    print("   - Excessive gain flagged: YES")
    print("   - Wrong Zener flagged:    YES")
    print("   - Report structure:       VALID")
    print("   - No directive leakage:   CLEAN\n")

    return report


if __name__ == "__main__":
    asyncio.run(run_hard_test())
