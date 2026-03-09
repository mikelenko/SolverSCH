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
import base64
from typing import Any, Dict, Optional, List
from solver_sch.ai.system_prompts import SENIOR_REVIEWER_PROMPT

logger = logging.getLogger("solver_sch.ai.design_reviewer")

def tool_recalculate_divider(v_in: float, v_target: float, max_current: float) -> Dict[str, Any]:
    """Calculates ideal resistor values for a voltage divider."""
    if max_current <= 0:
        return {"error": "max_current must be positive"}
    if v_in <= 0:
        return {"error": "v_in must be positive to calculate a divider"}
    
    r_total = float(v_in / max_current)
    r2 = float((v_target / v_in) * r_total)
    r1 = r_total - r2
    
    return {
        "R1": float(f"{r1:.2f}"),
        "R2": float(f"{r2:.2f}"),
        "R_total": float(f"{r_total:.2f}")
    }

def tool_recalculate_opamp_gain(v_in: float, v_target: float, r_in: float) -> Dict[str, Any]:
    """Calculates Rf value for a non-inverting OpAmp gain stage.
    Formula: Gain = 1 + (Rf / Rin) -> Rf = Rin * (Gain - 1)
    """
    if v_in <= 0:
        return {"error": "v_in must be positive"}
    if v_target < v_in:
        return {"error": "Target voltage must be >= input voltage for a non-inverting amplifier"}
    if r_in <= 0:
        return {"error": "r_in must be positive"}

    gain = v_target / v_in
    r_fb = r_in * (gain - 1)

    return {
        "Gain": float(f"{gain:.2f}"),
        "R_fb": float(f"{r_fb:.2f}")
    }

async def tool_analyze_diagram(image_path: str, question: str) -> Dict[str, Any]:
    """Analyzes an engineering diagram or datasheet excerpt using a local Vision Model (LLaVA via Ollama)."""
    try:
        with open(image_path, "rb") as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode('utf-8')
    except FileNotFoundError:
        return {"error": f"Image file {image_path} not found."}
    
    payload = {
        "model": "moondream",
        "prompt": f"Analyze this engineering diagram/datasheet. Question: {question}",
        "images": [img_b64],
        "stream": False
    }
    
    try:
        # Note: We use a separate session or the one from the caller if available.
        # Here we create a local one for simplicity as per user request.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post("http://localhost:11434/api/chat", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return {"vision_analysis": data.get("message", {}).get("content", "No output")}
                else:
                    return {"error": f"Ollama Vision API error: {response.status}"}
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Unknown error in tool_analyze_diagram"}

class ToolRegistry:
    """Registry for managing LLM tools and their schemas."""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, func: Any, schema: Dict[str, Any]):
        self._tools[name] = {"func": func, "schema": schema}

    def get_schemas(self, allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if allowed_tools is None:
            return [t["schema"] for t in self._tools.values()]
        return [self._tools[name]["schema"] for name in allowed_tools if name in self._tools]

    def call(self, name: str, kwargs: Dict[str, Any]) -> Any:
        if name not in self._tools:
            return {"error": f"Tool '{name}' not found in registry."}
        return self._tools[name]["func"](**kwargs)

# Global Registry Instance
REGISTRY = ToolRegistry()

REGISTRY.register(
    "recalculate_divider",
    tool_recalculate_divider,
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
)

REGISTRY.register(
    "recalculate_opamp_gain",
    tool_recalculate_opamp_gain,
    {
        "type": "function",
        "function": {
            "name": "recalculate_opamp_gain",
            "description": "Calculates the feedback resistor (Rf) for a non-inverting OpAmp stage based on input/target voltage and input resistor (Rin).",
            "parameters": {
                "type": "object",
                "properties": {
                    "v_in": {"type": "number", "description": "Input voltage to the stage (V)"},
                    "v_target": {"type": "number", "description": "Desired output voltage (V)"},
                    "r_in": {"type": "number", "description": "Input resistor value (Ohms)"}
                },
                "required": ["v_in", "v_target", "r_in"]
            }
        }
    }
)

REGISTRY.register(
    "analyze_diagram",
    tool_analyze_diagram,
    {
        "type": "function",
        "function": {
            "name": "analyze_diagram",
            "description": "Extracts engineering data from a local image file (like a datasheet graph, pinout diagram, or internal schematic) by asking a Vision AI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Relative path to the image file, e.g., 'datasheets/LM358_pinout.png'"},
                    "question": {"type": "string", "description": "Specific question about the diagram, e.g., 'What is pin 4 connected to?'"}
                },
                "required": ["image_path", "question"]
            }
        }
    }
)

class DesignReviewAgent:
    """Automated Agent for reviewing circuit designs based on simulation data."""

    def __init__(
        self, 
        model: str = "qwen2.5-coder:14b", 
        ollama_url: str = "http://localhost:11434/api/chat",
        temperature: float = 0.2,
        allowed_tools: Optional[List[str]] = None
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.temperature = temperature
        self.allowed_tools = allowed_tools

    async def review_design_async(
        self, 
        circuit_info: Any, 
        sim_results: Any, 
        task_intent: str
    ) -> str:
        user_content = self._format_prompt(circuit_info, sim_results, task_intent)
        messages = [
            {"role": "system", "content": SENIOR_REVIEWER_PROMPT},
            {"role": "user", "content": user_content}
        ]
        
        options = {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_thread": 6
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "tools": REGISTRY.get_schemas(self.allowed_tools),
                    "stream": False,
                    "options": options
                }
                
                logger.info(f"Sending request to Ollama ({self.model})...")
                async with session.post(self.ollama_url, json=payload) as response:
                    if response.status != 200:
                        return f"ERROR: Ollama status {response.status}"
                    
                    data = await response.json()
                    message = data.get("message", {})
                    content = message.get("content", "")
                    tool_calls = message.get("tool_calls", [])
                    
                    # Fallback JSON parsing
                    if not tool_calls and "```json" in content:
                        try:
                            json_str = content.split("```json")[-1].split("```")[0].strip()
                            call_data = json.loads(json_str)
                            if "name" in call_data and "arguments" in call_data:
                                tool_calls = [{"function": call_data}]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

                    if tool_calls:
                        messages.append(message)
                        for call in tool_calls:
                            func_name = call.get("function", {}).get("name")
                            args = call.get("function", {}).get("arguments", {})
                            if func_name == "recalculate_divider":
                                logger.info(f"Executing tool: {func_name} with args {args}")
                                result = tool_recalculate_divider(**args)
                                messages.append({"role": "tool", "content": json.dumps(result)})
                            
                            elif func_name == "recalculate_opamp_gain":
                                logger.info(f"Executing tool: {func_name} with args {args}")
                                result = tool_recalculate_opamp_gain(**args)
                                messages.append({"role": "tool", "content": json.dumps(result)})
                            
                            elif func_name == "analyze_diagram":
                                logger.info(f"Executing tool: {func_name} with args {args}")
                                result = await tool_analyze_diagram(**args)
                                messages.append({"role": "tool", "content": json.dumps(result)})
                            
                            else:
                                logger.warning(f"Tool {func_name} not implemented in explicit loop.")
                                result = {"error": f"Tool {func_name} not available in loop."}
                                messages.append({"role": "tool", "content": json.dumps(result)})
                        
                        payload["messages"] = messages
                        async with session.post(self.ollama_url, json=payload) as final_resp:
                            data = await final_resp.json()
                            return data.get("message", {}).get("content", "ERROR")
                    
                    return content or "ERROR: No content"
        
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
