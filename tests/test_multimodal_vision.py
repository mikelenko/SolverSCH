import asyncio
import logging
from solver_sch.ai.design_reviewer import DesignReviewAgent

# Włączamy logi na poziom INFO, żeby widzieć w konsoli moment wywołania narzędzia wizyjnego!
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def main():
    print("--- TEST MULTIMODALNY (QWEN 14B + LLaVA) ---")
    
    agent = DesignReviewAgent()
    
    # Symulujemy wycinek danych z netlisty i programu do layoutu PCB
    payload = {
        "netlist_components": ["U1_LM358", "SENSOR_TEMP"],
        "pcb_routing_warning": "Wykryto bezpośrednie połączenie ścieżki sygnałowej 'TEMP_OUT' do Pinu 8 układu U1_LM358."
    }
    
    # Narzucamy intencję, zmuszając agenta do zweryfikowania tego fizycznie za pomocą obrazu
    intent = (
        "I have a highly suspicious PCB routing connection. "
        "You MUST use the `analyze_diagram` tool on the image 'import/LM358_pinout.png' "
        "to determine exactly what Pin 8 of the LM358 is. "
        "Then, evaluate if connecting a delicate 3.3V sensor output to Pin 8 is a design flaw."
    )
    
    print("Wysyłanie zadania do Głównego Agenta (Qwen 14B)...")
    
    # Uruchamiamy przegląd asynchronicznie
    report = await agent.review_design_async(payload, {}, intent)
    
    print("\n" + "="*60)
    print("RAPORT KOŃCOWY (QWEN po konsultacji z modelem wizyjnym):")
    print("="*60)
    print(report)

if __name__ == "__main__":
    asyncio.run(main())
