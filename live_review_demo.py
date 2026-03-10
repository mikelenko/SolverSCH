"""
live_review_demo.py — End-to-End AI Design Review na boss_fight_channel.nsx

Przepływ:
  1. Buduje układ ręcznie (mapując boss_fight_channel.nsx)
  2. Uruchamia symulację DC + AC
  3. Wywołuje Simulator.review() z intencją projektową
  4. Drukuje raport AI i zapisuje do reports/

Uruchomienie:
    python live_review_demo.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    import solver_sch as sch
    from solver_sch.parser.netlist_parser import NetlistParser

    # ── Budowa układu (boss_fight_channel.nsx) ────────────────────────────────
    nsx_path = "Import/boss_fight_channel.nsx"
    print(f"Building circuit from: {nsx_path}")
    
    with open(nsx_path, "r", encoding="utf-8") as f:
        netlist_text = f.read()
        
    c = NetlistParser.parse_netlist(netlist_text, circuit_name="BossFight_SensorChannel")

    nodes = sorted(c.get_unique_nodes())
    comps = len(c.get_components())
    print(f"  Nodes: {nodes}")
    print(f"  Components: {comps}")

    # Walidacja
    result = c.validate()
    if not result.valid:
        print(f"  Validation warnings: {result.errors}")

    sim = sch.Simulator(c)

    # ── DC Analysis ───────────────────────────────────────────────────────────
    print("\nRunning DC analysis...")
    dc = sim.dc()
    print("  Node voltages:", {k: f"{v:.3f}V" for k, v in dc.node_voltages.items()})

    # ── AC Sweep 10 Hz – 10 MHz ───────────────────────────────────────────────
    print("\nRunning AC sweep (10 Hz – 10 MHz, 20 pts/decade)...")
    ac = sim.ac(f_start=10, f_stop=10e6, points_per_decade=20)
    print(f"  AC: {len(ac.frequencies)} frequency points computed")

    # ── AI Design Review ──────────────────────────────────────────────────────
    intent = (
        "Sensor signal conditioning channel for STM32 ADC (3.3V logic, "
        "Vref=3.3V, Vin_max=3.3V). "
        "Sensor output: 0–0.5V DC. "
        "Required ADC full-scale range: 0–3.3V. "
        "Power rails available: ±5V for OpAmp, 3.3V digital. "
        "Output must be protected against overvoltage spikes. "
        "Please identify ALL design errors, quantify their severity "
        "against the MCU absolute maximum ratings, and propose corrected values."
    )

    print("\nCalling AI Design Review (Gemini)...")
    print("=" * 64)
    report = await sim.review(dc_result=dc, ac_result=ac, intent=intent)
    print(report)
    print("=" * 64)

    # Zapis raportu
    os.makedirs("reports", exist_ok=True)
    out_path = "reports/boss_fight_review.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# AI Design Review — boss_fight_channel\n\n")
        f.write(f"**Intent:** {intent}\n\n---\n\n")
        f.write(report)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
