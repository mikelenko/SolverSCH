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
    
    żelazne_zasady = (
        " KRYTYCZNE ZASADY ŚRODOWISKA WERYFIKACYJNEGO (SUROWY DIALEKT MNA):\n"
        "1. Puste Płótno: Masz absolutną swobodę topologiczną. Kaskaduj komponenty i dodawaj węzły, jeśli trzeba.\n"
        "2. Sztywne Punkty Pomiarowe: Sygnał wejściowy ZAWSZE wchodzi na węzeł 'in'. Sygnał wyjściowy ZAWSZE mierzymy na węźle 'out'. Masa to '0'.\n"
        "3. BEZWZGLĘDNE ZASILANIE WEJŚCIA: ZAWSZE dodawaj wejściowe źródło testowe! Aby przetestować okno 9-36V, MUSISZ napisać 'V1 in 0 15' (gdzie 15 to przykładowe napięcie wewnątrz okna). Zasilanie logiki to np. 'V2 vcc 0 5'. Używaj CZYSTYCH liczb, bez słów 'DC' czy 'V'!\n"
        "4. Modele i Hierarchia: ZABRONIONE jest używanie dyrektyw .SUBCKT oraz .model.\n"
        "5. Składnia BJT: Bipolarne definiuj ściśle jako 'Q<nazwa> <kolektor> <baza> <emiter>'.\n"
        "6. Komparator z Limitami: Używaj 'U<nazwa> <wy> <we+> <we-> <high> <low>'. Przykład: 'U1 out in ref 5.0 0.0'.\n"
        "Myśl architektonicznie!"
    )
    
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
        full_prompt = goal_input + żelazne_zasady
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
