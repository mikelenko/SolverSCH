"""
test_design_review_tools.py -> Weryfikacja Tool Calling w DesignReviewAgent.
"""

import sys, os, asyncio, json, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO)
logging.getLogger("solver_sch.ai.design_reviewer").setLevel(logging.DEBUG)
from solver_sch.ai.design_reviewer import DesignReviewAgent

async def main():
    # Używamy modelu 14B, który dobrze radzi sobie z Tool Calling
    agent = DesignReviewAgent(model="qwen2.5-coder:14b")
    
    # 1. Cel: 12V -> 3.3V przy max 5mA
    task_intent = (
        "Zaprojektuj dzielnik napięcia 12V na 3.3V. "
        "Maksymalny prąd wejściowy (z V1) nie może przekroczyć 5mA."
    )
    
    # 2. Błędny projekt (R1=10k, R2=1k -> Vout ~ 1.1V zamiast 3.3V)
    # Prąd: 12V / 11k = 1.09mA (OK), ale napięcie złe.
    circuit_info = {
        "name": "Failing_Divider_Vout_Low",
        "bom": [
            {"designator": "V1", "value": 12.0, "nodes": ["in", "0"]},
            {"designator": "R1", "value": 10000.0, "nodes": ["in", "out"]},
            {"designator": "R2", "value": 1000.0, "nodes": ["out", "0"]}
        ]
    }
    
    sim_results = {
        "dc_operating_points": {
            "in": 12.0,
            "out": 1.091,   # 12 * (1k / 11k)
            "0": 0.0
        },
        "currents": {
            "V1": -0.00109  # 1.09mA
        }
    }
    
    print("--- URUCHAMIANIE AGENTA Z OBSŁUGĄ TOOLS (QWEN 14B) ---")
    print(f"Baza: {agent.ollama_url}\n")
    print("Oczekiwane zachowanie: Model powinien wykryć błąd napięcia i wywołać 'recalculate_divider'.\n")
    
    report = await agent.review_design_async(circuit_info, sim_results, task_intent)
    
    print("-" * 30)
    print("RAPORT KOŃCOWY (PO WYWOŁANIU TOOLS):")
    print("-" * 30)
    print(report)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
