"""
design_reviewer.py -> Automated Schematic Design Review Agent for SolverSCH.

Uses a local LLM (Qwen 2.5 Coder) via Ollama to perform high-level engineering 
code reviews based on deterministic simulation results from the solver.
Supports Tool Calling for mathematical recalculations.
"""

import logging
import json
import asyncio
import aiohttp
from typing import Any, Dict, Optional, List

logger = logging.getLogger("solver_sch.ai.design_reviewer")

def tool_recalculate_divider(v_in: float, v_target: float, max_current: float) -> Dict[str, Any]:
    """Calculates ideal resistor values for a voltage divider.
    """
    if max_current <= 0:
        return {"error": "max_current must be positive"}
    
    r_total = float(v_in / max_current)
    r2 = float((v_target / v_in) * r_total)
    r1 = r_total - r2
    
    return {
        "R1": float(f"{r1:.2f}"),
        "R2": float(f"{r2:.2f}"),
        "R_total": float(f"{r_total:.2f}")
    }

# Ollama Tool Schema
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "recalculate_divider",
            "description": "Recalculate R1 and R2 values for a voltage divider to reach a target voltage within current limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "v_in": {"type": "number", "description": "Input voltage (V)"},
                    "v_target": {"type": "number", "description": "Target output voltage (V)"},
                    "max_current": {"type": "number", "description": "Maximum allowed input current (A)"}
                },
                "required": ["v_in", "v_target", "max_current"]
            }
        }
    }
]

class DesignReviewAgent:
    """Automated Agent for reviewing circuit designs based on simulation data.

    This agent follows a hybrid architecture:
    1. Deterministic Solver: High-precision math/physics (numerical results).
    2. LLM Reviewer: Heuristic/Engineering reasoning (analytical report).
    3. Tool Calling: Automated mathematical fixes.
    """

    def __init__(
        self, 
        model: str = "qwen2.5-coder:14b", 
        ollama_url: str = "http://localhost:11434/api/chat",
        temperature: float = 0.2
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.temperature = temperature
        
        self.system_prompt = (
            "You are a Senior Hardware Engineer performing a strict Schematic Design Review. "
            "You will be provided with a circuit Netlist/BOM and exact mathematical simulation results "
            "(DC, AC, Transient) computed by a highly accurate SPICE solver. "
            "\n\nCRITICAL TOOL INSTRUCTION:\n"
            "If a voltage divider behaves incorrectly (e.g. Vout is not as intended), "
            "YOU MUST CALL the 'recalculate_divider' tool to get exact values. "
            "To call the tool, output ONLY a JSON block with 'name' and 'arguments'. "
            "Example:\n"
            "```json\n"
            "{\"name\": \"recalculate_divider\", \"arguments\": {\"v_in\": 12.0, \"v_target\": 3.3, \"max_current\": 0.005}}\n"
            "```\n"
            "DO NOT write JSON manually if your system supports native tool calls, but if not, this format is preferred. "
            "\n\nREPORT INSTRUCTIONS:\n"
            "1. Trust the solver's results implicitly.\n"
            "2. Analyze results and identify flaws: floating nodes, overcurrent, overvoltage.\n"
            "3. Format the FINAL response as a Markdown report with sections: "
            "[Executive Summary, Critical Warnings, Design Flaws, Best Practices Recommendations]."
            "CRITICAL: If you call a mathematical tool and receive its output, you MUST explicitly state the exact numerical results (e.g., the new resistor values) in the 'Best Practices Recommendations' section of your final report. Do not just tell the user to use the tool; give them the exact numbers the tool returned."
        )

    async def review_design_async(
        self, 
        circuit_info: Dict[str, Any], 
        sim_results: Dict[str, Any], 
        task_intent: str
    ) -> str:
        """Asynchronously performs a design review using Chat API and Tool Calling.
        """
        
        user_content = self._format_prompt(circuit_info, sim_results, task_intent)
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        options = {
            "temperature": self.temperature,
            "top_p": 0.9,
            "num_ctx": 4096,
            "num_thread": 6,
            "seed": 42
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                # First Call
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOLS_SCHEMA,
                    "stream": False,
                    "options": options
                }
                
                logger.info(f"Sending first request to Ollama ({self.model})...")
                async with session.post(self.ollama_url, json=payload) as response:
                    if response.status != 200:
                        return f"ERROR: Ollama Chat API status {response.status}: {await response.text()}"
                    
                    data = await response.json()
                    logger.debug(f"Raw Ollama Response: {json.dumps(data, indent=2)}")
                    message = data.get("message", {})
                    content = message.get("content", "")
                    
                    # 1. Check for formal tool_calls
                    tool_calls = message.get("tool_calls", [])
                    
                    # 2. Fallback: Parse Markdown JSON if tool_calls is empty
                    if not tool_calls and "```json" in content:
                        for json_block in content.split("```json")[1:]:
                            raw = json_block.split("```")[0].strip()
                            try:
                                call_data = json.loads(raw)
                                if "name" in call_data and "arguments" in call_data:
                                    logger.info("Detected fallback JSON tool call in content.")
                                    tool_calls = [{"function": call_data}]
                                    break
                            except Exception as e:
                                logger.warning(f"Failed to parse fallback JSON block: {e}")

                    if tool_calls:
                        logger.info(f"Processing {len(tool_calls)} tool calls.")
                        messages.append(message) # Add assistant's tool call request
                        
                        for call in tool_calls:
                            func_name = call.get("function", {}).get("name")
                            args = call.get("function", {}).get("arguments", {})
                            
                            if func_name == "recalculate_divider":
                                logger.info(f"Executing tool: {func_name} with args {args}")
                                result = tool_recalculate_divider(**args)
                                messages.append({
                                    "role": "tool",
                                    "content": json.dumps(result)
                                })
                        
                        # Second Call for final summary — no tools to prevent re-triggering tool loop
                        final_payload = {
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "options": options
                        }
                        logger.info("Sending second request with tool results...")
                        async with session.post(self.ollama_url, json=final_payload) as second_response:
                            if second_response.status != 200:
                                return f"ERROR: Ollama Final API status {second_response.status}"

                            final_data = await second_response.json()
                            return final_data.get("message", {}).get("content", "ERROR: Empty final response.")
                    
                    if not content:
                        return f"ERROR: Model returned no content and no tool calls. Raw: {json.dumps(data)}"
                        
                    return content
        
        except aiohttp.ClientConnectorError:
            return "ERROR: Could not connect to Ollama server."
        except asyncio.TimeoutError:
            return "ERROR: AI review timed out (300s)."
        except Exception as e:
            return f"ERROR: Unexpected error: {str(e)}"

    def _format_prompt(self, circuit_info: Dict[str, Any], sim_results: Dict[str, Any], task_intent: str) -> str:
        return f"""
### TASK DESCRIPTION
{task_intent}

### CIRCUIT BOM
{json.dumps(circuit_info, indent=2)}

### SOLVER SIMULATION RESULTS
{json.dumps(sim_results, indent=2)}

Please perform a Senior Design Review. Use the 'recalculate_divider' tool if the output voltage is wrong.
"""

if __name__ == "__main__":
    async def test():
        reviewer = DesignReviewAgent()
        # Mocking a failing divider: 12V in, target 3.3V, but we have R1=10k, R2=1k (Output ~1.09V)
        circuit = {
            "bom": [{"designator": "R1", "value": 10000}, {"designator": "R2", "value": 1000}, {"designator": "V1", "value": 12.0}]
        }
        results = {
            "dc_op": {"out": 1.09, "in": 12.0},
            "currents": {"V1": 0.00109} # 12/11000
        }
        intent = "Voltage divider to step down 12V to 3.3V @ 5mA max."
        
        print("--- Testing Tool Calling Loop ---")
        report = await reviewer.review_design_async(circuit, results, intent)
        print(report)

    asyncio.run(test())
