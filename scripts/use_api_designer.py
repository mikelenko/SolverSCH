import logging
import os
from solver_sch.ai.auto_designer import AutonomousDesigner

# Minimal logging to see the AI's thoughts
logging.basicConfig(level=logging.INFO)

from solver_sch.ai.llm_providers import LLMProvider

class Custom600VProvider(LLMProvider):
    """Simulates an LLM response with the 600V-5V detector design."""
    def generate(self, prompt, system_instruction=None):
        return """
```spice
* 600V to 5V Detector (LLM Generated through API)
V1 in 0 600.0
Rh1 in n1 400k
Rh2 n1 n2 400k
Rh3 n2 div 390k
Rl div 0 10k
* OpAmp Buffer: E <out> <in_p> <in_n> <gain>
E1 out div out 1000000
.end
```
"""

def run_api_design():
    # Ensure results directory exists
    os.makedirs("results", exist_ok=True)
    
    prompt = (
        "Design a 600V to 5V DC measurement circuit. [DC TARGET: 5.0V] "
        "Use a divider and a buffer."
    )
    
    # Inject our custom provider instead of calling an external API
    llm = Custom600VProvider()
    designer = AutonomousDesigner(target_goal=prompt, llm=llm)
    
    print(f"--- Launching AutonomousDesigner API (with CustomProvider) ---\n")
    designer.run_optimization_loop()

if __name__ == "__main__":
    run_api_design()
