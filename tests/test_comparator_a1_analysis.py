"""
Analiza obwodu Comparator_A_1.cir — kanał A (BU19_1_B)
Agent SAM decyduje jakie narzędzia wywołać i z jakimi parametrami.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from solver_sch.ai.design_reviewer import DesignReviewAgent

logging.basicConfig(level=logging.INFO)

# Załaduj .env z katalogu projektu (jeśli GEMINI_API_KEY nie jest ustawiony)
if not os.environ.get("GEMINI_API_KEY"):
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

NETLIST_PATH = Path(__file__).parent.parent / "Comparator_A_1.cir"


async def main():
    print("--- AGENT-DRIVEN ANALYSIS: Comparator_A_1.cir ---\n")

    # Wczytaj surową netlistę — agent dostaje ją jako kontekst
    netlist_text = NETLIST_PATH.read_text(encoding="utf-8")

    # ── Payload: surowe dane obwodu, BEZ gotowych wyników ──────────────────────
    circuit_info = {
        "circuit_name": "Comparator_A_1 — Quad Comparator Input Conditioning",
        "netlist_raw": netlist_text,
        "bom": [
            # Channel A (BU19_1_B) — to jest kanał do analizy
            {"ref": "RR58_1",  "type": "Resistor",    "value": 10000, "nodes": "Input_A_1 → INPUT_A-_1",    "role": "series input resistor"},
            {"ref": "RR84_1",  "type": "Resistor",    "value": 2400,  "nodes": "INPUT_A-_1 → GND",          "role": "input filter to GND"},
            {"ref": "RR85_1",  "type": "Resistor",    "value": 20000, "nodes": "5V_REF → REF_1",            "role": "ref divider high-side"},
            {"ref": "RR88_1",  "type": "Resistor",    "value": 10000, "nodes": "REF_1 → GND",               "role": "ref divider low-side"},
            {"ref": "RR81_1",  "type": "Resistor",    "value": 4700,  "nodes": "Comp_out_A_1 → +3V3",       "role": "output pull-up"},
            {"ref": "BU19_1_B","type": "Comparator",  "value": None,  "nodes": "CMP(+)=REF_1, CMP(-)=INPUT_A-_1, out=Comp_out_A_1"},
            {"ref": "CC128_1", "type": "Capacitor",   "value": 100e-9,"nodes": "INPUT_A-_1 → GND",          "role": "input filter cap"},
            {"ref": "DD14",    "type": "Diode",       "value": None,  "nodes": "Input_A_1 → GND",           "role": "input protection"},
            # Supply rails
            {"ref": "5V_REF",  "type": "Supply",      "value": 5.0},
            {"ref": "+3V3",    "type": "Supply",      "value": 3.3},
        ],
        "target_channel": "Channel A (BU19_1_B)",
        "sensor_voltage_range": "0–36V (typical automotive/industrial sensor)",
    }

    # ── Intent: co agent ma zbadać (ale NIE jak) ───────────────────────────────
    intent = (
        "You are analyzing a comparator-based sensor input conditioning circuit. "
        "Your task:\n"
        "1. Use the simulate_dc_sweep tool to determine the switching threshold "
        "   and voltage levels across the input network for various V_in values.\n"
        "   Extract resistor values from the BOM above to fill tool parameters.\n"
        "2. After getting simulation data, determine if the switching threshold "
        "   is reachable within the sensor's 0-36V range.\n"
        "3. If the design has issues, use recalculate_divider to suggest fixes.\n"
        "4. Write a complete engineering report with findings."
    )

    # ── Agent z narzędziami ────────────────────────────────────────────────────
    if not os.environ.get("GEMINI_API_KEY"):
        print("BŁĄD: brak GEMINI_API_KEY")
        return

    agent = DesignReviewAgent(
        backend="gemini",
        allowed_tools=["simulate_dc_sweep", "recalculate_divider"],
    )

    print("Agent uruchomiony. Discovery phase (tool calling)...\n")
    report = await agent.review_design_async(circuit_info, {}, intent)

    print("\n" + "=" * 60)
    print("RAPORT KOŃCOWY (agent-generated):")
    print("=" * 60)
    sys.stdout.flush()
    sys.stdout.buffer.write((report + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    asyncio.run(main())
