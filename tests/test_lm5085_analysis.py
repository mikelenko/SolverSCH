import asyncio
import logging
import os
import sys
from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.ai.design_reviewer import DesignReviewAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("lm5085_analysis")

def load_env():
    """Manually load .env file if it exists."""
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

async def main():
    load_env()
    print("\n" + "="*60)
    print("LM5085 STEP-DOWN DCDC CONVERTER ANALYSIS")
    print("="*60)
    
    netlist_path = "StepDownDCDC_LM5085.cir"
    if not os.path.exists(netlist_path):
        print(f"ERROR: Netlist file not found: {netlist_path}")
        return

    print(f"[*] Reading netlist: {netlist_path}")
    with open(netlist_path, 'r', encoding='utf-8', errors='ignore') as f:
        netlist_text = f.read()
    
    print("[*] Parsing circuit topology...")
    circuit = NetlistParser.parse_netlist(netlist_text, "StepDown_LM5085")
    
    # Extrahiujemy BOM ręcznie dla agenta, aby wiedział o konkretnych numerach części
    # (NetlistParser może nie wyciągnąć numerów części z komentarzy lub stubów automatycznie w 100% przypadków)
    bom = []
    for comp in circuit.get_components():
        bom.append({
            "designator": comp.name,
            "type": type(comp).__name__,
            "value": str(comp)
        })
    
    # Dodajemy informacje o kluczowych układach scalonych (wyciągnięte z komentarzy w .cir)
    # U6 = LM5085SD
    # Q5 = SQS411
    circuit_info = {
        "project_name": "StepDownDCDC_LM5085",
        "bom": bom,
        "critical_parts": {
            "U6": "LM5085SD/NOPB",
            "Q5": "SQS411ENW",
            "D15": "ES2BHE3"
        }
    }

    # Symulacja DC - POMIJAMY zgodnie z prośbą użytkownika (brak modelu U6)
    sim_results = {}

    print("\n--- URUCHAMIANIE SZTUCZNEJ INTELIGENCJI (DIODE SPECIALIST) ---")
    print("[*] Cel: Dedykowana analiza diody D15 (ES2BHE3).")
    
    intent = (
        "Wykonaj szczegółową analizę techniczną diody D15 (ES2BHE3) w roli diody flyback (freewheeling) dla przetwornicy Buck 24V/12V (LM5085). "
        "SKUP SIĘ WYŁĄCZNIE NA DIODZIE: "
        "1. Sprawdź parametry: Vrrm, If(av), Vf (spadek napięcia) oraz Trr (czas odzyskiwania). "
        "2. Wyjaśnij różnicę między zastosowaną technologią 'Ultrafast' a zalecaną technologią Schottky dla tego zastosowania. "
        "3. Przedstaw konsekwencje dla sprawności i poziomu szumów (EMI). "
        "4. Podaj jasną rekomendację: CZY MOŻNA JĄ ZOSTAWIĆ, CZY NALEŻY WYMIENIĆ? "
        "ODPOWIEDZ PO POLSKU."
    )

    agent = DesignReviewAgent(model="gemini-3.1-flash-lite-preview")
    
    try:
        report = await agent.review_design_async(circuit_info, sim_results, intent)
        
        print("\n" + "="*60)
        print("RAPORT INŻYNIERSKI - DIODA ES2BHE3:")
        print("="*60)
        print(report)
        
        # Save report to file
        report_path = "reports/ES2BHE3_Diode_Report.md"
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(report)
        print(f"\n[*] Raport został zapisany w: {report_path}")
        
    except Exception as e:
        logger.error(f"Error during AI review: {e}")

if __name__ == "__main__":
    asyncio.run(main())
