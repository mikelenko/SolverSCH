"""
test_design_review.py -> Demonstracja użycia DesignReviewAgent.
"""

import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from solver_sch.ai.design_reviewer import DesignReviewAgent

async def main():
    agent = DesignReviewAgent(model="qwen2.5-coder:14b")
    
    system_prompt = (
            "You are a Senior Hardware Engineer performing a strict Schematic Design Review. "
            "You will be provided with a circuit Netlist/BOM and exact mathematical simulation results "
            "(DC, AC, Transient) computed by a highly accurate SPICE solver. "
            "CRITICAL INSTRUCTION: DO NOT calculate math yourself. DO NOT propose specific new component values or formulas. "
            "Trust the solver's results implicitly. If values are wrong, simply state that they need to be recalculated by the designer. "
            "Your task is to analyze these results and identify any engineering flaws, such as:\n"
            "- Floating nodes or unconnected pins.\n"
            "- Overcurrent, overvoltage, or thermal issues.\n"
            "- Output values deviating from the task intent.\n"
            "- Missing good practices (e.g., decoupling capacitors, pull-up resistors).\n"
            "Format your response as a professional Markdown report with sections: "
            "[Executive Summary, Critical Warnings, Design Flaws, Best Practices Recommendations]."
        )

    # 1. Definiujemy "Intencję" projektową
    task_intent = (
        "Zaprojektuj dzielnik napięcia (Voltage Divider), który z 12V DC na wejściu (V1) "
        "wygeneruje 3.3V na wyjściu (węzeł 'out'). Prąd wejściowy nie może przekroczyć 10mA."
    )
    
    # 2. Dane z Simulatora (Dla tego testu podajemy "twarde" dane ręcznie)
    # W rzeczywistym systemie te dane pochodzą z stamper.py i sparse_solver.py
    circuit_info = {
        "name": "Voltage_Divider_Iteration_1",
        "bom": [
            {"designator": "V1", "value": 12.0, "nodes": ["in", "0"]},
            {"designator": "R1", "value": 1000.0, "nodes": ["in", "out"]},
            {"designator": "R2", "value": 330.0, "nodes": ["out", "0"]}
        ]
    }
    
    sim_results = {
        "dc_operating_points": {
            "in": 12.0,
            "out": 2.977,   # 12 * (330 / 1330)
            "0": 0.0
        },
        "currents": {
            "V1": -0.00902  # ~9.02mA (V=12, R_total=1330)
        },
        "violations": [] 
    }
    
    print("--- URUCHAMIANIE AGENTA DESIGN REVIEW (QWEN 14B) ---")
    print(f"Baza: {agent.ollama_url}\n")
    
    report = await agent.review_design_async(circuit_info, sim_results, task_intent)
    
    print("-" * 30)
    print("RAPORT INŻYNIERSKI (MARKDOWN):")
    print("-" * 30)
    print(report)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
