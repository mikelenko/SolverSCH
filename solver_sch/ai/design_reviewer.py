"""
design_reviewer.py — Public facade for the DesignReviewAgent.

All heavy implementation lives in the sub-modules:
  tools.py        — tool functions, ToolRegistry, REGISTRY
  llm_backends.py — LLMClient (Ollama + Gemini)
  agent.py        — run_review() two-phase loop

Backward-compatible re-exports keep existing imports working unchanged.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from solver_sch.ai.system_prompts import SENIOR_REVIEWER_PROMPT

# ── Backward-compatible re-exports ───────────────────────────────────────────
from solver_sch.ai.tools import (  # noqa: F401
    DATASHEETS_DIR,
    HAS_PDF_DEPS,
    REGISTRY,
    ToolRegistry,
    _datasheet_cache,
    tool_analyze_diagram,
    tool_query_datasheet,
    tool_recalculate_divider,
    tool_recalculate_opamp_gain,
)
from solver_sch.ai.llm_backends import LLMClient  # noqa: F401
from solver_sch.ai.agent import run_review  # noqa: F401

# fitz re-export so existing patches on "solver_sch.ai.design_reviewer.fitz" still resolve
try:
    import fitz  # noqa: F401
except ImportError:
    fitz = None  # type: ignore[assignment]

logger = logging.getLogger("solver_sch.ai.design_reviewer")


class DesignReviewAgent:
    """Automated Agent for reviewing circuit designs based on simulation data.

    Supports two backends:
      - "ollama": Local model via Ollama /api/chat
      - "gemini": Google Gemini API (requires GEMINI_API_KEY)
    """

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite-preview",
        ollama_url: str = "http://localhost:11434/api/chat",
        temperature: float = 0.2,
        allowed_tools: Optional[List[str]] = None,
        backend: str = "gemini",
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.temperature = temperature
        self.allowed_tools = allowed_tools
        self.backend = backend.lower()
        self._gemini_client = None

        if self.backend == "gemini":
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set.")
            from google import genai
            self._gemini_client = genai.Client(api_key=api_key)
            # Share client + model with vision tool
            import solver_sch.ai.tools as _tools
            _tools._vision_gemini_client = self._gemini_client
            _tools._vision_model = self.model

        self._llm_client = LLMClient(
            model=self.model,
            ollama_url=self.ollama_url,
            temperature=self.temperature,
            backend=self.backend,
            gemini_client=self._gemini_client,
        )

    async def review_design_async(
        self,
        circuit_info: Any,
        sim_results: Any,
        task_intent: str,
    ) -> str:
        """Delegate to agent.run_review() after building the initial messages."""
        user_context = self._format_prompt(circuit_info, sim_results, task_intent)
        messages = [
            {"role": "system", "content": SENIOR_REVIEWER_PROMPT},
            {"role": "user", "content": user_context},
        ]
        return await run_review(
            llm_client=self._llm_client,
            messages=messages,
            registry=REGISTRY,
            allowed_tools=self.allowed_tools,
        )

    @staticmethod
    def _safe_json(obj: Any, **kwargs: Any) -> str:
        """JSON-serialize with numpy/complex type support."""
        import numpy as _np

        def _default(o: Any) -> Any:
            if isinstance(o, _np.integer):
                return int(o)
            if isinstance(o, _np.floating):
                return float(o)
            if isinstance(o, _np.complexfloating):
                return {"re": float(o.real), "im": float(o.imag)}
            if isinstance(o, _np.ndarray):
                return o.tolist()
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        return json.dumps(obj, default=_default, **kwargs)

    def _load_component_cards(self, circuit_info: Dict[str, Any]) -> Dict[str, Any]:
        """Load .card.json files for ICs found in the BOM."""
        if not os.path.isdir(DATASHEETS_DIR):
            return {}

        bom: List[Dict[str, Any]] = circuit_info.get("bom", [])
        candidates: set = set()
        for entry in bom:
            ref: str = entry.get("ref", "")
            comp_type: str = entry.get("type", "")
            if comp_type in ("Resistor", "Capacitor", "Inductor", "VoltageSource",
                             "CurrentSource", "ACVoltageSource"):
                continue
            if "_" in ref:
                candidates.add(ref.split("_", 1)[1].lower())
            candidates.add(ref.lower())

        cards: Dict[str, Any] = {}
        for fname in os.listdir(DATASHEETS_DIR):
            if not fname.lower().endswith(".card.json"):
                continue
            comp_name = fname.lower().removesuffix(".card.json")
            if comp_name in candidates:
                try:
                    with open(os.path.join(DATASHEETS_DIR, fname), "r", encoding="utf-8") as f:
                        cards[comp_name.upper()] = json.load(f)
                except Exception:
                    pass
        return cards

    def _format_prompt(
        self,
        circuit_info: Dict[str, Any],
        sim_results: Dict[str, Any],
        task_intent: str,
    ) -> str:
        cards = self._load_component_cards(circuit_info)
        cards_section = self._safe_json(cards, indent=2) if cards else "No datasheets indexed."

        return f"""
### TASK DESCRIPTION
{task_intent}

### CIRCUIT BOM
{self._safe_json(circuit_info, indent=2)}

### COMPONENT DATASHEETS (summaries — use query_datasheet tool for details)
{cards_section}

### SOLVER SIMULATION RESULTS
{self._safe_json(sim_results, indent=2)}

Please perform a Senior Design Review. Use the 'recalculate_divider' tool if the output voltage is wrong.
"""


if __name__ == "__main__":
    import asyncio

    async def test():
        reviewer = DesignReviewAgent()
        circuit = {
            "bom": [
                {"designator": "R1", "value": 10000},
                {"designator": "R2", "value": 1000},
                {"designator": "V1", "value": 12.0},
            ]
        }
        results = {
            "dc_op": {"out": 1.09, "in": 12.0},
            "currents": {"V1": 0.00109},
        }
        intent = "Voltage divider to step down 12V to 3.3V @ 5mA max."
        print("--- Testing Tool Calling Loop ---")
        report = await reviewer.review_design_async(circuit, results, intent)
        print(report)

    asyncio.run(test())
