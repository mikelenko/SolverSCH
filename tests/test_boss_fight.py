import asyncio
import logging
import numpy as np
from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.signal_analyzer import extract_ac_metrics, extract_transient_metrics
from solver_sch.ai.design_reviewer import DesignReviewAgent

logging.basicConfig(level=logging.WARNING)

async def main():
    print("--- ROZPOCZĘCIE AUDYTU (BOSS FIGHT) ---")
    
    # Naprawa: wczytujemy plik przed parsowaniem
    netlist_path = "import/boss_fight_channel.nsx"
    with open(netlist_path, 'r', encoding='utf-8', errors='ignore') as f:
        netlist_text = f.read()
    
    circuit = NetlistParser.parse_netlist(netlist_text, "Sensor_Channel")
    stamper = MNAStamper(circuit)
    stamper.stamp_linear()
    
    solver = SparseSolver(stamper.A_lil, stamper.z_vec, stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n)
    
    # 1. Symulacja DC
    print("[1/3] Obliczanie punktu pracy (DC)...")
    dc_res = solver.solve()
    
    # 2. Symulacja AC
    print("[2/3] Skanowanie częstotliwości (AC Bode Plot)...")
    # Zwraca słowniki node -> array
    freqs, mags_db, phases_deg = solver.simulate_ac_sweep(10, 1e6, 20, stamper)
    ac_metrics = extract_ac_metrics(
        freqs, 
        mags_db.get('out', np.zeros(len(freqs))), 
        phases_deg.get('out', np.zeros(len(freqs)))
    )
    
    # 3. Symulacja Transient
    print("[3/3] Badanie dynamiki skoku (Transient)...")
    tr_res = solver.simulate_transient(t_stop=1e-3, dt=100e-9)
    times = np.array([t for t, r in tr_res])
    voltages = np.array([r.node_voltages.get('out', 0.0) for t, r in tr_res])
    tr_metrics = extract_transient_metrics(times, voltages)
    
    print("\n--- URUCHAMIANIE SZTUCZNEJ INTELIGENCJI ---")
    
    # Pakujemy wszystko do jednego zgrabnego słownika (0 surowych tablic!)
    payload = {
        "netlist_components": [comp.name for comp in circuit.get_components()],
        "dc_node_voltages": {k: round(v, 3) for k, v in dc_res.node_voltages.items() if k != '0'},
        "ac_metrics": ac_metrics,
        "transient_metrics": tr_metrics
    }
    
    # ZDEJMUJEMY KÓŁKA BOCZNE - ZERO WSKAZÓWEK
    intent = "Perform a comprehensive, senior-level design review of this entire sensor channel."
    
    agent = DesignReviewAgent()
    report = await agent.review_design_async(payload, {}, intent)
    
    print("\n" + "="*60)
    print("RAPORT KOŃCOWY (QWEN 14B):")
    print("="*60)
    print(report)

if __name__ == "__main__":
    asyncio.run(main())
