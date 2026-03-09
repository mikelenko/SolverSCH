import asyncio
import logging
import numpy as np
from solver_sch.model.circuit import Circuit, Resistor, Inductor, Capacitor, ACVoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.signal_analyzer import extract_ac_metrics
from solver_sch.ai.design_reviewer import DesignReviewAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def main():
    print("1. Budowa obwodu RLC (Unstable AC, R=0.1 Ohm, L=10uH, C=100nF)...")
    # High-Q series RLC: low damping -> narrow resonance peak, poor phase margin
    circuit = Circuit("Unstable AC RLC", ground_name="0")
    circuit.add_component(ACVoltageSource("V_IN", "in", "0", amplitude=1.0, frequency=1e3, ac_mag=1.0))
    circuit.add_component(Resistor("R_LOSS", "in", "net_l", 0.1))
    circuit.add_component(Inductor("L_RESON", "net_l", "out", 10e-6))
    circuit.add_component(Capacitor("C_RESON", "out", "0", 100e-9))

    print("2. Budowa macierzy MNA...")
    stamper = MNAStamper(circuit)
    stamper.stamp_linear()

    solver = SparseSolver(
        A_matrix=stamper.A_lil,
        z_vector=stamper.z_vec,
        node_to_idx=stamper.node_to_idx,
        vsrc_to_idx=stamper.vsrc_to_idx,
        n_independent_nodes=stamper.n
    )

    print("3. Symulacja AC Sweep (1 kHz - 10 MHz)...")
    freqs, mags_db, phases_deg = solver.simulate_ac_sweep(
        f_start=1e3,
        f_stop=10e6,
        points_per_decade=50,
        stamper_ref=stamper
    )

    print("4. Pre-procesor SignalAnalyzer...")
    mag_out = mags_db.get('out', np.zeros(len(freqs)))
    phase_out = phases_deg.get('out', np.zeros(len(freqs)))

    ac_metrics = extract_ac_metrics(freqs, mag_out, phase_out)
    print(f"   Peak Gain:     {ac_metrics['peak_gain_db']:.2f} dB @ {ac_metrics['peak_gain_freq_hz']:.0f} Hz")
    bw = ac_metrics['bw_3db_hz']
    pm = ac_metrics['phase_margin_deg']
    print(f"   -3dB BW:       {bw:.0f} Hz" if bw is not None else "   -3dB BW:       N/A")
    print(f"   Phase Margin:  {pm:.1f} deg" if pm is not None else "   Phase Margin:  N/A (no 0dB crossover)")

    print("\n5. Wywolanie Agenta AI (Design Review)...")
    agent = DesignReviewAgent()

    circuit_info = {
        "netlist_components": [
            {"ref": c.name, "type": type(c).__name__, "nodes": list(c.nodes())}
            for c in circuit.get_components()
        ]
    }
    sim_results = {"ac_metrics": ac_metrics}

    intent = "Evaluate the AC frequency response of this high-Q RLC circuit. Check for stability and phase margin."
    report = await agent.review_design_async(circuit_info, sim_results, intent)

    print("\n" + "=" * 50)
    print("RAPORT Z AUDYTU:")
    print("=" * 50)
    print(report)

if __name__ == "__main__":
    asyncio.run(main())
