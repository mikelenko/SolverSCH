import os
import sys
import argparse
import logging
import traceback
from pathlib import Path


def _ensure_env_key(key: str, *search_paths: Path) -> None:
    """Load an env key from .env files if not already set in environment."""
    if os.environ.get(key):
        return
    for env_path in search_paths:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line.startswith(f"{key}="):
                    os.environ[key] = line.split("=", 1)[1].strip()
                    return


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

def cmd_review(args):
    """Parses a netlist, runs DC, and calls DesignReviewAgent for an AI review."""
    import asyncio
    from solver_sch.parser.netlist_parser import NetlistParser
    from solver_sch.model.circuit import Circuit
    from solver_sch.simulator import Simulator

    _ensure_env_key("GEMINI_API_KEY", Path(args.netlist).parent / ".env", Path(".env"))

    with open(args.netlist, encoding="utf-8", errors="replace") as f:
        text = f.read()
    circuit: Circuit = NetlistParser.parse_netlist(text, circuit_name=args.netlist)
    sim = Simulator(circuit, backend="mna")
    dc = sim.dc()
    report = asyncio.run(sim.review(dc_result=dc, intent=args.intent, model=args.model, netlist_text=text))
    print(report)


def cmd_analyze(args):
    """Agent-driven circuit analysis — agent sam wybiera narzędzia i parametry."""
    import asyncio
    from solver_sch.ai.design_reviewer import DesignReviewAgent

    _ensure_env_key("GEMINI_API_KEY", Path(args.netlist).parent / ".env", Path(".env"))

    if not os.environ.get("GEMINI_API_KEY"):
        print("[BŁĄD] Brak GEMINI_API_KEY (ustaw w .env lub zmiennej środowiskowej)")
        sys.exit(1)

    netlist_text = Path(args.netlist).read_text(encoding="utf-8")

    circuit_info = {
        "circuit_name": Path(args.netlist).stem,
        "netlist_raw": netlist_text,
    }

    intent = args.intent

    agent = DesignReviewAgent(
        backend="gemini",
        model=args.model,
        allowed_tools=["simulate_dc_sweep", "recalculate_divider"],
    )

    print(f"[ANALYZE] Agent analizuje: {args.netlist}")
    print(f"[ANALYZE] Intent: {intent}")
    print(f"[ANALYZE] Model: {args.model}")
    print(f"[ANALYZE] Narzędzia: simulate_dc_sweep, recalculate_divider\n")

    report = asyncio.run(agent.review_design_async(circuit_info, {}, intent))

    sys.stdout.flush()
    sys.stdout.buffer.write((report + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()



def cmd_altium_to_spice(args):
    """Parses Altium .NET netlist and BOM to generate SPICE .cir file."""
    from solver_sch.parser.altium_parser import AltiumParser
    from solver_sch.utils.exporter import LTspiceExporter
    import os

    try:
        project = AltiumParser.parse_netlist_file(args.netlist)
        if args.bom:
            bom_data = AltiumParser.parse_bom(args.bom)
            for designator, bom_entry in bom_data.items():
                if designator in project.components:
                    project.components[designator].comment = bom_entry.description

        if getattr(args, "schematic_json", None) and getattr(args, "sheet_name", None):
            import json as _json
            with open(args.schematic_json, 'r', encoding='utf-8') as _f:
                _sdata = _json.load(_f)
            _sheet = _sdata.get('Sheets', {}).get(args.sheet_name, {})
            if not _sheet:
                print(f"[OSTRZEŻENIE] Brak sheetu '{args.sheet_name}' w {args.schematic_json}")
            else:
                # Designatory (pomiń czysto numeryczne test pointy)
                _json_map = {d: info.get('Comment', '') for d, info in _sheet.items() if not d.isdigit()}
                print(f"[FILTR] Sheet '{args.sheet_name}': {len(_json_map)} komponentów z JSON.")
                project = AltiumParser.filter_by_designators(project, set(_json_map.keys()))
                # Wzbogać wartości: BOM desc > JSON comment
                _bom_descs = {}
                if getattr(args, "bom_xlsx", None):
                    _bom_descs = AltiumParser.parse_bom_xlsx(args.bom_xlsx)
                for des in list(project.components.keys()):
                    comp = project.components[des]
                    bom_d = _bom_descs.get(des, '')
                    if bom_d and AltiumParser.extract_value(bom_d) is not None:
                        comp.comment = bom_d
                    else:
                        comp.comment = _json_map.get(des, comp.comment)

        elif getattr(args, "bom_xlsx", None) and getattr(args, "sheet", None):
            xlsx_map = AltiumParser.parse_bom_xlsx(args.bom_xlsx, sheet_number=args.sheet)
            if not xlsx_map:
                print(f"[OSTRZEŻENIE] Brak komponentów dla sheetu {args.sheet} w {args.bom_xlsx}")
            else:
                print(f"[FILTR] Sheet {args.sheet}: znaleziono {len(xlsx_map)} designatorów z BOM xlsx.")
                project = AltiumParser.filter_by_designators(project, set(xlsx_map.keys()))
                for des, comment in xlsx_map.items():
                    if des in project.components:
                        project.components[des].comment = comment

        if args.isolate_net:
            # Domyślne zasilania jako ściany izolacji. Użytkownik może nadpisać.
            default_stops = ["GND", "0", "+5V", "+3V3", "VBAT", "AGND", "PGND", "DGND", "VCC", "VDD"]
            stop_nets = args.stop_nets.split(",") if args.stop_nets else default_stops
            print(f"[IZOLACJA] Rozpoczynam wyodrębnianie od podsieci: '{args.isolate_net}'...")
            project = AltiumParser.isolate_subcircuit(project, args.isolate_net, stop_nets)

        circuit = AltiumParser.convert_to_circuit(project)
        
        out_path = args.output
        if not out_path:
            out_path = os.path.splitext(args.netlist)[0] + "_export.cir"
            
        LTspiceExporter.export(circuit, out_path, analysis="op")
        print(f"\n[SUKCES] Wygenerowano plik SPICE: {out_path}")
        print(f"Skonwertowano analogowych komponentów: {len(circuit.get_components())}")
        
    except Exception as e:
        print(f"[BŁĄD] Wystąpił problem podczas konwersji: {e}")
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(
        prog="solversch",
        description="SolverSCH: Autonomous EDA Designer and MNA Solver"
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Włącz tryb gadatliwy (DEBUG logging)")

    subparsers = parser.add_subparsers(dest="command", help="Dostępne polecenia")

    # Komenda: ai (interaktywny tryb AI)
    parser_ai = subparsers.add_parser("ai", help="Uruchamia interaktywnego asystenta projektowania układów za pomocą AI")

    # Komenda: review (AI design review z pliku netlisty)
    parser_review = subparsers.add_parser("review", help="Uruchamia audyt AI na pliku netlisty (.nsx/.cir)")
    parser_review.add_argument("netlist", help="Ścieżka do pliku netlisty")
    parser_review.add_argument("--intent", default="Perform a full design review.", help="Opis celu audytu")
    parser_review.add_argument("--model", default="gemini-3.1-flash-lite-preview", help="Model Gemini do użycia")

    # Komenda: analyze (agent-driven analysis z narzędziami)
    parser_analyze = subparsers.add_parser("analyze", help="Agent-driven analiza obwodu — agent sam wybiera narzędzia")
    parser_analyze.add_argument("netlist", help="Ścieżka do pliku netlisty (.cir)")
    parser_analyze.add_argument("--intent", default="Analyze this circuit. Use simulate_dc_sweep to determine switching thresholds and voltage levels. Report any design flaws.", help="Opis celu analizy")
    parser_analyze.add_argument("--model", default="gemini-3.1-flash-lite-preview", help="Model Gemini do użycia")

    # Komenda: chat (interactive multi-turn AI chat)
    parser_chat = subparsers.add_parser("chat", help="Interactive multi-turn AI chat with autonomous simulate_circuit tool")
    parser_chat.add_argument("--provider", "-p", default="ollama",
                             choices=["gemini", "openai", "anthropic", "claude", "ollama", "stub"],
                             help="LLM provider to use (default: ollama)")
    parser_chat.add_argument("--model", "-m", default=None, help="Model name override")
    parser_chat.add_argument("--temperature", "-t", type=float, default=0.7, help="Sampling temperature (default: 0.7)")
    parser_chat.add_argument("--system", "-s", default=None, help="Custom system prompt (overrides built-in tool prompt)")

    # Komenda: chat-gui (desktop agent chat window)
    subparsers.add_parser("chat-gui", help="Open desktop agent chat window (PySide6 + Anthropic)")

    # Komenda: altium-to-spice
    parser_a2s = subparsers.add_parser("altium-to-spice", help="Konwertuje pliki Altium (.NET, .xls BOM) na format SPICE (.cir)")
    parser_a2s.add_argument("--netlist", required=True, help="Ścieżka do pliku .NET (Altium Netlist)")
    parser_a2s.add_argument("--bom", help="Opcjonalna ścieżka do pliku .xls (Altium BOM)")
    parser_a2s.add_argument("--bom-xlsx", help="Ścieżka do pliku .xlsx BOM z kolumną SheetNumber (nowy format)")
    parser_a2s.add_argument("--sheet", help="Numer arkusza do filtrowania z BOM xlsx (np. 16)")
    parser_a2s.add_argument("--output", help="Ścieżka dla pliku wyjściowego .cir (domyślnie tworzony obok pliku .NET)")

    parser_a2s.add_argument("--isolate-net", help="Nazwa sieci (net), od której algorytm wyodrębni podobwód (np. Comp_out_A_1)")
    parser_a2s.add_argument("--stop-nets", help="Lista sieci izolujących rozdzielona przecinkami (domyślnie: GND,0,+5V,+3V3,VBAT,AGND,PGND,DGND,VCC,VDD)")

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "ai":
        cmd_ai()
    elif args.command == "chat":
        from solver_sch.ai.chat import run_chat
        run_chat(
            provider_name=args.provider,
            model=args.model,
            temperature=args.temperature,
            system_prompt=args.system,
        )
    elif args.command == "chat-gui":
        from solver_sch.ai.chat_window import main as _chat_gui_main
        _chat_gui_main()
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "altium-to-spice":
        cmd_altium_to_spice(args)
    else:
        # Domyślne zachowanie: brak argumentów -> wyświetl pomoc
        parser.print_help()

if __name__ == "__main__":
    main()
