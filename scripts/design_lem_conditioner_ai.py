import os
import logging
import time
from solver_sch.ai.auto_designer import AutonomousDesigner
from solver_sch.ai.llm_providers import get_provider

# Ustawienie klucza API
os.environ["GEMINI_API_KEY"] = "AIzaSyD6YG0KFjzIoFPGsYeVDM54swjRo6ceRlo"

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_lem_ai_design():
    print("=== Autonomous LEM Conditioner Design (AI Driven v3) ===")
    
    # Prompt nakierowujący na prostą i stabilną topologię
    prompt = (
        "Design a high-precision LEM current transducer interface. [DC TARGET: 3.3V]\n\n"
        "GOAL: Output V(out) = 3.3V when input current I_LEM is +25mA.\n"
        "Baseline: When current is 0mA, V(out) should be 1.65V.\n\n"
        "SOLVERSCH DIALECT:\n"
        "- V1 vcc 0 3.3 (Power supply)\n"
        "- V2 v_ref 0 1.65 (Offset reference)\n"
        "- I_LEM v_ref out 0.025 (The sensor output current)\n"
        "- R<name> <n1> <n2> <value> (Resistors)\n"
        "- The output node MUST be named 'out'.\n\n"
        "HINT: Simply connect a burden resistor Rb between node 'out' and 'v_ref'. "
        "Calculate the value of Rb so that 25mA produces exactly 1.65V additional drop, resulting in V(out) = 3.3V.\n"
        "DO NOT use .subckt, .model or complex OpAmps for this simple task."
    )
    
    # Używamy gemini-1.5-flash (stabilniejszy/tańszy jeśli chodzi o limity) 
    # lub gemini-2.0-flash jeśli użytkownik preferuje
    llm = get_provider("gemini", model="gemini-2.0-flash")
    designer = AutonomousDesigner(target_goal=prompt, llm=llm)
    
    print(f"Starting the optimization loop...\n")
    
    try:
        designer.run_optimization_loop(max_iterations=5)
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Design loop failed: {e}")

if __name__ == "__main__":
    run_lem_ai_design()
