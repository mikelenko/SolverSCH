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


async def tool_query_datasheet(component_name: str, query: str) -> Dict[str, Any]:
    """Searches a local datasheet for relevant passages using BM25 keyword ranking.

    Prefers pre-built .index.json (from build_index.py) over live PDF parsing.
    Returns section_title metadata when available.
    """
    if not HAS_PDF_DEPS:
        return {"error": "PyMuPDF and rank_bm25 are not installed. Run: pip install PyMuPDF rank_bm25"}

    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100
    TOP_K = 3

    comp_key = component_name.strip().lower()

    # Fast path: return from cache immediately if already indexed
    if comp_key not in _datasheet_cache:
        chunks: List[str] = []
        chunk_pages: List[int] = []
        chunk_sections: List[str] = []

        # ── Priority 1: Pre-built .index.json ──────────────────────────────
        index_path: Optional[str] = None
        if os.path.isdir(DATASHEETS_DIR):
            for fname in os.listdir(DATASHEETS_DIR):
                fname_lower = fname.lower()
                if fname_lower == f"{comp_key}.index.json":
                    index_path = os.path.join(DATASHEETS_DIR, fname)

        if index_path and os.path.isfile(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                for chunk in index_data.get("chunks", []):
                    text = chunk.get("text", "").strip()
                    if text:
                        chunks.append(text)
                        chunk_pages.append(chunk.get("page_start", 1))
                        chunk_sections.append(chunk.get("section_title", ""))
            except Exception as e:
                return {"error": f"Failed to load index file: {e}"}
        else:
            # ── Priority 2: Live PDF parsing ────────────────────────────────
            pdf_path: Optional[str] = None
            if os.path.isdir(DATASHEETS_DIR):
                for fname in os.listdir(DATASHEETS_DIR):
                    if fname.lower() == f"{comp_key}.pdf":
                        pdf_path = os.path.join(DATASHEETS_DIR, fname)
                        break

            if pdf_path is None or not os.path.isfile(pdf_path):
                return {"error": f"Datasheet for '{component_name}' not found. Place '{component_name}.pdf' in the datasheets/ directory."}

            try:
                doc = fitz.open(pdf_path)
            except Exception as e:
                return {"error": f"Failed to open PDF: {e}"}

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if not text or not text.strip():
                    continue
                start = 0
                while start < len(text):
                    end = start + CHUNK_SIZE
                    chunk_text = text[start:end].strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                        chunk_pages.append(page_num + 1)
                        chunk_sections.append("")
                    start += CHUNK_SIZE - CHUNK_OVERLAP
            doc.close()

        if not chunks:
            return {"error": f"No extractable text found for '{component_name}'. The PDF may be image-only."}

        tokenized = [c.lower().split() for c in chunks]
        bm25 = BM25Plus(tokenized)
        _datasheet_cache[comp_key] = {
            "chunks": chunks,
            "pages": chunk_pages,
            "sections": chunk_sections,
            "bm25": bm25,
        }

    # Query BM25 index
    cache = _datasheet_cache[comp_key]
    query_tokens = query.lower().split()
    scores = cache["bm25"].get_scores(query_tokens)

    all_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranked_indices = [all_indices[i] for i in range(min(TOP_K, len(all_indices)))]

    results = []
    cache_sections: List[str] = cache.get("sections", [])
    for idx in ranked_indices:
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

    if not results:
        return {"results": [], "note": f"No relevant passages found for query: '{query}'"}

    # Attach component card summary if available
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
                    "component_name": {"type": "string", "description": "Component name matching the PDF filename (e.g., 'LM358', '2N2222', 'IRF540N')"},
                    "query": {"type": "string", "description": "Search query describing what information to find (e.g., 'maximum input voltage rating', 'output current limit')"}
                },
                "required": ["component_name", "query"]
            }
        }
    }
)
