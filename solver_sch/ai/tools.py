"""
tools.py — Tool functions, ToolRegistry, and REGISTRY instance for DesignReviewAgent.

Contains all callable tools exposed to the LLM:
- tool_recalculate_divider
- tool_recalculate_opamp_gain
- tool_analyze_diagram
- tool_query_datasheet
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    import fitz  # PyMuPDF
    from rank_bm25 import BM25Plus
    HAS_PDF_DEPS = True
except ImportError:
    HAS_PDF_DEPS = False

logger = logging.getLogger("solver_sch.ai.tools")

DATASHEETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "datasheets"
)
_datasheet_cache: Dict[str, Dict[str, Any]] = {}

# Vision backend config — set by DesignReviewAgent on init
_vision_gemini_client: Any = None
_vision_model: str = "gemini-3.1-flash-lite-preview"


def tool_recalculate_divider(v_in: float, v_target: float, max_current: float, **kwargs: Any) -> Dict[str, Any]:
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


def tool_recalculate_opamp_gain(v_in: float, v_target: float, r_in: float, **kwargs: Any) -> Dict[str, Any]:
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


async def tool_analyze_diagram(image_path: str, question: str, **kwargs: Any) -> Dict[str, Any]:
    """Analyzes an engineering diagram or datasheet excerpt using Gemini Vision."""
    global _vision_gemini_client, _vision_model

    # Normalize path separators and try case-insensitive resolution
    image_path = image_path.replace("\\", "/")
    if not os.path.exists(image_path):
        head, tail = os.path.split(image_path)
        if head:
            parent, dirname = os.path.split(head)
            candidate = os.path.join(parent, dirname.capitalize(), tail)
            if os.path.exists(candidate):
                image_path = candidate

    try:
        with open(image_path, "rb") as img_file:
            img_bytes = img_file.read()
    except FileNotFoundError:
        return {"error": f"Image file '{image_path}' not found. Check the path and try again with a corrected path."}

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    if _vision_gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY not set and no vision client initialized."}
        from google import genai as _genai
        _vision_gemini_client = _genai.Client(api_key=api_key)

    try:
        from google.genai import types as _gtypes

        prompt_text = (
            "You are a Senior Hardware Engineer analyzing an electronics datasheet or IC diagram. "
            f"{question} "
            "List every visible pin number and its exact function. Be concise and precise."
        )

        part_image = _gtypes.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        part_text = _gtypes.Part.from_text(text=prompt_text)
        contents = _gtypes.Content(parts=[part_image, part_text], role="user")

        raw_response: Dict[str, Any] = {}

        def _sync_generate() -> None:
            resp = _vision_gemini_client.models.generate_content(  # type: ignore[union-attr]
                model=_vision_model,
                contents=[contents],
            )
            raw_response["text"] = str(resp.text) if resp.text else ""

        await asyncio.to_thread(_sync_generate)  # type: ignore[arg-type]
        raw: str = raw_response.get("text", "")
        return {"vision_analysis": raw.strip()}
    except Exception as e:
        return {"error": f"Gemini vision error: {e}"}


def _load_datasheet_index(comp_key: str, component_name: str) -> Dict[str, Any]:
    """Load and cache a datasheet index for comp_key.

    Tries .index.json first, falls back to live PDF parsing.
    Returns the cache entry dict, or raises ValueError with an error message.
    """
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100

    if comp_key in _datasheet_cache:
        return _datasheet_cache[comp_key]

    chunks: List[str] = []
    chunk_pages: List[int] = []
    chunk_sections: List[str] = []

    # Priority 1: Pre-built .index.json
    index_path: Optional[str] = None
    if os.path.isdir(DATASHEETS_DIR):
        for fname in os.listdir(DATASHEETS_DIR):
            if fname.lower() == f"{comp_key}.index.json":
                index_path = os.path.join(DATASHEETS_DIR, fname)

    if index_path and os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        for chunk in index_data.get("chunks", []):
            text = chunk.get("text", "").strip()
            if text:
                chunks.append(text)
                chunk_pages.append(chunk.get("page_start", 1))
                chunk_sections.append(chunk.get("section_title", ""))
    else:
        # Priority 2: Live PDF parsing
        pdf_path: Optional[str] = None
        if os.path.isdir(DATASHEETS_DIR):
            for fname in os.listdir(DATASHEETS_DIR):
                if fname.lower() == f"{comp_key}.pdf":
                    pdf_path = os.path.join(DATASHEETS_DIR, fname)
                    break

        if pdf_path is None or not os.path.isfile(pdf_path):
            raise ValueError(
                f"Datasheet for '{component_name}' not found. "
                f"Place '{component_name}.pdf' in the datasheets/ directory."
            )

        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text")
            if not text or not text.strip():
                continue
            start = 0
            while start < len(text):
                chunk_text = text[start:start + CHUNK_SIZE].strip()
                if chunk_text:
                    chunks.append(chunk_text)
                    chunk_pages.append(page_num + 1)
                    chunk_sections.append("")
                start += CHUNK_SIZE - CHUNK_OVERLAP
        doc.close()

    if not chunks:
        raise ValueError(
            f"No extractable text found for '{component_name}'. The PDF may be image-only."
        )

    tokenized = [c.lower().split() for c in chunks]
    entry: Dict[str, Any] = {
        "chunks": chunks,
        "pages": chunk_pages,
        "sections": chunk_sections,
        "bm25": BM25Plus(tokenized),
    }
    _datasheet_cache[comp_key] = entry
    return entry


def _search_bm25(cache: Dict[str, Any], query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Run BM25 query against a loaded cache entry, return top_k results."""
    scores = cache["bm25"].get_scores(query.lower().split())
    all_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    cache_sections: List[str] = cache.get("sections", [])
    results = []
    for idx in all_indices[:top_k]:
        score_val = float(scores[idx])
        if score_val > 0:
            entry: Dict[str, Any] = {
                "page": cache["pages"][idx],
                "text": cache["chunks"][idx],
                "score": float(f"{score_val:.3f}"),
            }
            if idx < len(cache_sections) and cache_sections[idx]:
                entry["section"] = cache_sections[idx]
            results.append(entry)
    return results


async def tool_query_datasheet(component_name: Optional[str] = None, query: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Searches a local datasheet for relevant passages using BM25 keyword ranking.

    Supports 'part_number' alias for 'component_name'.
    Prefers pre-built .index.json (from build_index.py) over live PDF parsing.
    Returns section_title metadata when available.
    """
    if component_name is None:
        component_name = kwargs.get("part_number") or kwargs.get("component")
    if not component_name:
        return {"error": "Missing parameter: 'component_name' (or 'part_number') is required."}
    if not query:
        return {"error": "Missing parameter: 'query' is required."}
    if not HAS_PDF_DEPS:
        return {"error": "PyMuPDF and rank_bm25 are not installed. Run: pip install PyMuPDF rank_bm25"}

    comp_key = component_name.strip().lower()
    try:
        cache = _load_datasheet_index(comp_key, component_name)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Failed to load datasheet index: {e}"}

    results = _search_bm25(cache, query)
    if not results:
        return {"results": [], "note": f"No relevant passages found for query: '{query}'"}

    # Attach component card if available
    comp_card: Optional[Dict[str, Any]] = None
    if os.path.isdir(DATASHEETS_DIR):
        for fname in os.listdir(DATASHEETS_DIR):
            if fname.lower() == f"{comp_key}.card.json":
                try:
                    with open(os.path.join(DATASHEETS_DIR, fname), "r", encoding="utf-8") as f:
                        comp_card = json.load(f)
                except Exception:
                    pass
                break

    response: Dict[str, Any] = {"results": results}
    if comp_card:
        response["component_card"] = comp_card
    return response


def tool_simulate_dc_sweep(
    v_supply: float,
    v_in_values: List[float],
    r_series: float,
    r_to_gnd: float,
    r_ref_high: float,
    r_ref_low: float,
    r_pullup: float,
    v_pullup: float,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run a DC sweep simulation of a comparator input channel.

    Builds the circuit programmatically and solves using MNA + Newton-Raphson
    (MNAStamper + SparseSolver) for each V_in value. Returns node voltages and
    current through the series resistor for each operating point.

    Circuit topology:
        V_IN -- R_SERIES -- vm -- R_FILT -- GND
                             |
                         CMP(-)   (inverting input)
                         CMP(+) = REF = V_SUPPLY * r_ref_low / (r_ref_high + r_ref_low)
                         CMP(out) -- R_PULLUP -- V_PULLUP
    """
    try:
        from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, Comparator
        from solver_sch.builder.stamper import MNAStamper
        from solver_sch.solver.sparse_solver import SparseSolver
    except ImportError as e:
        return {"error": f"SolverSCH import failed: {e}"}

    v_ref_theoretical = float(v_supply * r_ref_low / (r_ref_high + r_ref_low))
    threshold_vin = v_ref_theoretical * (r_series + r_to_gnd) / r_to_gnd if r_to_gnd > 0 else 0.0
    sweep_results = []

    for v_in in v_in_values:
        try:
            ckt = Circuit(f"CMP_sweep_vin{v_in:.3f}")

            # Input signal
            ckt.add_component(VoltageSource("V_IN", "vin", "0", float(v_in)))
            # Series resistor RR58_1: vin -> vm
            ckt.add_component(Resistor("R_SERIES", "vin", "vm", float(r_series)))
            # Filter resistor to GND RR84_1: vm -> 0
            ckt.add_component(Resistor("R_FILT", "vm", "0", float(r_to_gnd)))

            # Reference divider: supply -> vref -> GND
            ckt.add_component(VoltageSource("V_SUP", "vsup", "0", float(v_supply)))
            ckt.add_component(Resistor("R_REF_H", "vsup", "vref", float(r_ref_high)))
            ckt.add_component(Resistor("R_REF_L", "vref", "0", float(r_ref_low)))

            # Comparator: CMP(+)=vref, CMP(-)=vm, out=vout
            ckt.add_component(Comparator("CMP", "vref", "vm", "vout"))

            # Pull-up to v_pullup rail
            ckt.add_component(VoltageSource("V_PU", "vpu", "0", float(v_pullup)))
            ckt.add_component(Resistor("R_PU", "vpu", "vout", float(r_pullup)))

            # Use MNAStamper + SparseSolver with Newton-Raphson (same as test_boss_fight.py)
            stamper = MNAStamper(ckt)
            stamper.stamp_linear()
            solver = SparseSolver(
                stamper.A_lil, stamper.z_vec,
                stamper.node_to_idx, stamper.vsrc_to_idx, stamper.n
            )
            solver.set_nonlinear_stamper(stamper.stamp_nonlinear)
            res = solver.solve()
            voltages = res.node_voltages

            v_vm = float(voltages.get("vm", 0.0))
            v_vref = float(voltages.get("vref", v_ref_theoretical))
            v_vout = float(voltages.get("vout", 0.0))

            # Current through R_SERIES: I = (V_IN - V_vm) / R_SERIES
            i_r_series_uA = (float(v_in) - v_vm) / r_series * 1e6 if r_series > 0 else 0.0

            sweep_results.append({
                "v_in": round(float(v_in), 4),
                "v_input_minus": round(v_vm, 4),
                "v_ref": round(v_vref, 4),
                "comp_output_V": round(v_vout, 4),
                "i_r_series_uA": round(i_r_series_uA, 2),
                "state": "HIGH" if v_vout > v_pullup * 0.5 else "LOW",
            })
        except Exception as e:
            sweep_results.append({"v_in": float(v_in), "error": str(e)})

    return {
        "sweep": sweep_results,
        "v_ref_theoretical_V": round(v_ref_theoretical, 4),
        "threshold_vin_V": round(threshold_vin, 3),
        "topology": (
            f"V_IN -> R_SERIES({r_series:.0f}) -> vm -> R_FILT({r_to_gnd:.0f}) -> GND; "
            f"CMP(+)=vref={v_ref_theoretical:.3f}V, CMP(-)=vm, "
            f"out -> R_PU({r_pullup:.0f}) -> {v_pullup}V"
        ),
    }


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

    async def call(self, name: str, kwargs: Dict[str, Any]) -> Any:
        if name not in self._tools:
            return {"error": f"Tool '{name}' not found in registry."}
        func = self._tools[name]["func"]
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)


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

REGISTRY.register(
    "query_datasheet",
    tool_query_datasheet,
    {
        "type": "function",
        "function": {
            "name": "query_datasheet",
            "description": "Searches a component's PDF datasheet for relevant technical information using keyword matching. Returns the top 3 most relevant text passages with page numbers. Use this to verify component specifications, absolute maximum ratings, pin functions, or electrical characteristics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component_name": {"type": "string", "description": "Part number or component name matching the PDF filename (e.g., 'LM358', 'ES2BHE3', 'LM5085')"},
                    "query": {"type": "string", "description": "Search query describing what information to find (e.g., 'maximum input voltage rating', 'output current limit')"}
                },
                "required": ["component_name", "query"]
            }
        }
    }
)

REGISTRY.register(
    "simulate_dc_sweep",
    tool_simulate_dc_sweep,
    {
        "type": "function",
        "function": {
            "name": "simulate_dc_sweep",
            "description": (
                "Runs a DC operating-point simulation sweep for a comparator input channel. "
                "Builds the circuit from component values extracted from the netlist and calls "
                "the MNA solver for each V_in value. Returns node voltages (vm = inverting input, "
                "vref = reference, vout = comparator output) and current through the series resistor. "
                "Use this to find the switching threshold and verify voltage levels across the input network."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "v_supply": {"type": "number", "description": "Supply voltage for the reference divider (e.g. 5.0 for 5V_REF)"},
                    "v_in_values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "List of input voltage values to sweep (V), e.g. [0.0, 0.5, 1.0, 1.5, 1.667, 1.8, 2.0, 2.5, 3.0, 3.3, 5.0]"
                    },
                    "r_series": {"type": "number", "description": "Series resistor between V_IN and inverting input node (Ohms), e.g. RR58_1 = 10000"},
                    "r_to_gnd": {"type": "number", "description": "Resistor from inverting input node to GND (Ohms), e.g. RR84_1 = 2400"},
                    "r_ref_high": {"type": "number", "description": "Upper resistor of reference voltage divider (Ohms), e.g. RR85_1 = 20000"},
                    "r_ref_low": {"type": "number", "description": "Lower resistor of reference voltage divider (Ohms), e.g. RR88_1 = 10000"},
                    "r_pullup": {"type": "number", "description": "Pull-up resistor on comparator output (Ohms), e.g. RR81_1 = 4700"},
                    "v_pullup": {"type": "number", "description": "Pull-up rail voltage (V), e.g. 3.3 for +3V3"}
                },
                "required": ["v_supply", "v_in_values", "r_series", "r_to_gnd", "r_ref_high", "r_ref_low", "r_pullup", "v_pullup"]
            }
        }
    }
)
