import asyncio
import logging
from solver_sch.ai.design_reviewer import tool_analyze_diagram

async def main():
    print("--- DEBUG VISION (LLaVA) ---")
    img_path = "import/LM358_pinout.png"
    question = "What is Pin 8 of the LM358?"
    
    result = await tool_analyze_diagram(img_path, question)
    print("\nResult from LLaVA:")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
