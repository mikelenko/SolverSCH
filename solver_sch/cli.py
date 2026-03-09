import sys
import argparse
import logging
import traceback

def setup_logging(verbose: bool):
    """Konfiguruje globalny rejestrator zdarzeń na podstawie trybu gadatliwości."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )

def cmd_ai():
    """Uruchamia środowisko projektanta AI (Osobisty Projektant AI)."""
    from solver_sch.ai.auto_designer import AutonomousDesigner
    from solver_sch.ai.system_prompts import SOLVER_ENVIRONMENT_RULES

    print("=== Osobisty Projektant AI (The SolverSCH Environment) ===")
    print("Zasilany przez solver_sch. Wpisz 'exit', 'quit' lub 'q' aby wyjść.\n")

    while True:
        try:
            goal_input = input("\n[CEL PROJEKTU] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nWyjście awaryjne. Zamykanie...")
            break

        if not goal_input:
            continue

        if goal_input.lower() in ('exit', 'quit', 'q'):
            print("Zamykanie środowiska projektowego. Do widzenia!")
            break

        # Zastrzyk zasady środowiska weryfikacyjnego do pętli agentowej
        full_prompt = goal_input + SOLVER_ENVIRONMENT_RULES
        designer_agent = AutonomousDesigner(target_goal=full_prompt)
        
        try:
            designer_agent.run_optimization_loop(max_iterations=5)
        except Exception as e:
            print(f"Error during AI loop: {e}")
            traceback.print_exc()
            
        print("-" * 50)

def main():
    parser = argparse.ArgumentParser(
        prog="solversch",
        description="SolverSCH: Autonomous EDA Designer and MNA Solver"
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="Włącz tryb gadatliwy (DEBUG logging)")
    
    subparsers = parser.add_subparsers(dest="command", help="Dostępne polecenia")
    
    # Komenda: ai (interaktywny tryb AI)
    parser_ai = subparsers.add_parser("ai", help="Uruchamia interaktywnego asystenta projektowania układów za pomocą AI")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    if args.command == "ai":
        cmd_ai()
    else:
        # Domyślne zachowanie: brak argumentów -> wyświetl pomoc
        parser.print_help()

if __name__ == "__main__":
    main()
