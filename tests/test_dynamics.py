"""
test_dynamics.py -> Integration test for SignalAnalyzer + DesignReviewAgent.

Builds an underdamped RLC circuit programmatically (no PULSE/MODEL directives),
runs a transient simulation, extracts metrics via SignalAnalyzer,
and sends only the scalar metrics to the AI reviewer.
"""

import asyncio
import logging

import numpy as np

from solver_sch.model.circuit import Circuit, Resistor, Inductor, Capacitor, VoltageSource
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.signal_analyzer import extract_transient_metrics
from solver_sch.ai.design_reviewer import DesignReviewAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def main():
    print("1. Budowa obwodu RLC (Underdamped, R=1 Ohm, L=10uH, C=100nF)...")
    # Series RLC: V_STEP -> R -> L -> out -> C -> GND
    # Step input: DC 3.3V (approximates a voltage step for DC operating point)
    circuit = Circuit("Underdamped RLC", ground_name="0")
    circuit.add_component(VoltageSource("V1", "in", "0", 3.3))
    circuit.add_component(Resistor("R_DAMP", "in", "net_l", 1.0))
    circuit.add_component(Inductor("L_FILT", "net_l", "out", 10e-6))
    circuit.add_component(Capacitor("C_FILT", "out", "0", 100e-9))

    print("2. Budowa macierzy MNA...")
    stamper = MNAStamper(circuit)
    stamper.stamp_linear()

    solver = SparseSolver(
        A_matrix=stamper.A_lil,
        z_vector=stamper.z_vec,
        node_to_idx=stamper.node_to_idx,
        vsrc_to_idx=stamper.vsrc_to_idx,
        n_independent_nodes=stamper.n,
    )

    print("3. Symulacja Transient (1ms, krok 100ns)...")
    results = solver.simulate_transient(t_stop=1e-3, dt=100e-9)

    times = np.array([t for t, _ in results])
    voltages = np.array([res.node_voltages.get("out", 0.0) for _, res in results])

    print("4. Pre-procesor SignalAnalyzer...")
    tr_metrics = extract_transient_metrics(times, voltages)
    print(f"   Napięcie ustalone : {tr_metrics['v_steady_v']:.3f} V")
    print(f"   Napięcie max      : {tr_metrics['v_max_v']:.3f} V")
    overshoot = tr_metrics['peak_overshoot_pct']
    print(f"   Przeregulowanie   : {overshoot:.1f} %" if overshoot is not None else "   Przeregulowanie   : N/A")

    print("\n5. Wywołanie Agenta AI (Design Review)...")
    agent = DesignReviewAgent()

    circuit_info = {
        "netlist_components": [
            {"ref": c.name, "type": type(c).__name__, "nodes": list(c.nodes())}
            for c in circuit.get_components()
        ]
    }
    sim_results = {"transient_metrics": tr_metrics}

    intent = (
        "Perform a strict review of the underdamped RLC filter's transient dynamics. "
        "Focus on stability, ringing, and peak overshoot relative to 3.3V steady state."
    )
    report = await agent.review_design_async(circuit_info, sim_results, intent)

    print("\n" + "=" * 50)
    print("RAPORT Z AUDYTU:")
    print("=" * 50)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
