"""
signal_analyzer.py -> Signal Metrics Extractor for AC and Transient results.

Converts raw numpy arrays into compact engineering metric dicts safe for LLM context.
NO raw array data is returned — only scalar summaries.
"""

from typing import Dict, Optional
import numpy as np


def extract_ac_metrics(
    freqs: np.ndarray,
    mags_db: np.ndarray,
    phases_deg: np.ndarray,
) -> Dict[str, Optional[float]]:
    """Extract key AC/Bode metrics from frequency sweep arrays.

    Returns:
        peak_gain_db:       Maximum gain [dB]
        peak_gain_freq_hz:  Frequency at peak gain [Hz]
        bw_3db_hz:          -3dB cutoff frequency from peak [Hz], None if not found
        phase_margin_deg:   Phase Margin = 180 + phase at 0dB crossover [deg], None if no 0dB crossing
    """
    if len(freqs) == 0:
        return {"peak_gain_db": None, "peak_gain_freq_hz": None, "bw_3db_hz": None, "phase_margin_deg": None}

    peak_idx = int(np.argmax(mags_db))
    peak_gain_db = float(mags_db[peak_idx])
    peak_gain_freq_hz = float(freqs[peak_idx])

    # -3dB bandwidth: first frequency where gain drops below (peak - 3) dB
    threshold = peak_gain_db - 3.0
    bw_3db_hz: Optional[float] = None
    # Search after peak for the cutoff
    for i in range(peak_idx, len(mags_db)):
        if mags_db[i] <= threshold:
            # Linear interpolation between samples i-1 and i
            if i > 0 and mags_db[i - 1] != mags_db[i]:
                t = (threshold - mags_db[i - 1]) / (mags_db[i] - mags_db[i - 1])
                bw_3db_hz = float(freqs[i - 1] + t * (freqs[i] - freqs[i - 1]))
            else:
                bw_3db_hz = float(freqs[i])
            break

    # Phase margin: phase at the 0dB gain crossover (gain descends through 0)
    phase_margin_deg: Optional[float] = None
    for i in range(1, len(mags_db)):
        if mags_db[i - 1] >= 0.0 >= mags_db[i]:
            # Linear interpolation for the exact crossover
            if mags_db[i - 1] != mags_db[i]:
                t = (0.0 - mags_db[i - 1]) / (mags_db[i] - mags_db[i - 1])
                phase_at_crossover = phases_deg[i - 1] + t * (phases_deg[i] - phases_deg[i - 1])
            else:
                phase_at_crossover = float(phases_deg[i])
            phase_margin_deg = float(180.0 + phase_at_crossover)
            break

    return {
        "peak_gain_db": peak_gain_db,
        "peak_gain_freq_hz": peak_gain_freq_hz,
        "bw_3db_hz": bw_3db_hz,
        "phase_margin_deg": phase_margin_deg,
    }


def extract_transient_metrics(
    times: np.ndarray,
    voltages: np.ndarray,
) -> Dict[str, Optional[float]]:
    """Extract key transient metrics from a time-domain simulation.

    Returns:
        v_steady_v:         Steady-state voltage (mean of last 10% of samples) [V]
        v_max_v:            Maximum voltage in the waveform [V]
        peak_overshoot_pct: ((V_max - V_steady) / |V_steady|) * 100 [%], None if V_steady ≈ 0
    """
    if len(voltages) == 0:
        return {"v_steady_v": None, "v_max_v": None, "peak_overshoot_pct": None}

    tail_start = max(0, int(len(voltages) * 0.9))
    v_steady = float(np.mean(voltages[tail_start:]))
    v_max = float(np.max(voltages))

    peak_overshoot_pct: Optional[float] = None
    if abs(v_steady) > 1e-9:
        peak_overshoot_pct = float(((v_max - v_steady) / abs(v_steady)) * 100.0)

    return {
        "v_steady_v": v_steady,
        "v_max_v": v_max,
        "peak_overshoot_pct": peak_overshoot_pct,
    }
