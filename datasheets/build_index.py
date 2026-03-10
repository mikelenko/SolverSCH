"""
build_index.py — Offline Hierarchical RAG Indexer for SolverSCH Datasheets.

Usage:
    python datasheets/build_index.py datasheets/LM358.pdf
    python datasheets/build_index.py datasheets/LM358.pdf --no-card   # skip Gemini card gen
    python datasheets/build_index.py datasheets/LM358.pdf --model gemini-3.1-flash-lite-preview

Outputs (next to the PDF):
    LM358.card.json   — Component Card (~150 tokens), requires GEMINI_API_KEY
    LM358.index.json  — Pre-built chunks with section metadata (no API key needed)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ────────────────────────────────────────────────────────────────

SECTION_CHUNK_MAX = 2000
SECTION_CHUNK_SIZE = 1500
SECTION_CHUNK_OVERLAP = 200
MIN_HEADING_FONT_RATIO = 1.35   # heading font must be >= 135% of body font
MIN_HEADING_WORDS = 2           # heading must have at least 2 words
MIN_SECTION_CHARS = 50          # discard sections shorter than this

# Adaptive card schemas — key_electrical fields per component category
CARD_SCHEMAS: Dict[str, Dict[str, str]] = {
    "opamp": {
        "GBW": "...", "slew_rate": "...", "Vos_max": "...",
        "CMRR": "...", "Iq": "...", "Vcc_range": "...",
    },
    "voltage_regulator": {
        "Vin_range": "...", "Vout": "...", "Iout_max": "...",
        "dropout": "...", "line_regulation": "...", "quiescent_current": "...",
    },
    "mosfet": {
        "Vds_max": "...", "Id_max": "...", "Rds_on": "...",
        "Vgs_th": "...", "Qg_total": "...", "Pd_max": "...",
    },
    "bms_monitor": {
        "cells": "...", "measurement_accuracy": "...", "adc_resolution": "...",
        "conversion_time": "...", "interface": "...", "sleep_current": "...",
    },
    "adc": {
        "resolution_bits": "...", "channels": "...", "sample_rate": "...",
        "INL": "...", "interface": "...", "Vref": "...",
    },
    "mcu": {
        "core": "...", "flash_KB": "...", "ram_KB": "...",
        "max_clock": "...", "gpio_count": "...", "peripherals": "...",
    },
    "generic": {
        "param_1": "...", "param_2": "...", "param_3": "...",
        "param_4": "...", "param_5": "...", "param_6": "...",
    },
}

# Heuristic 2: Known datasheet section titles (normalised to UPPER STRIP)
KNOWN_SECTIONS: frozenset = frozenset({
    "ABSOLUTE MAXIMUM RATINGS",
    "RECOMMENDED OPERATING CONDITIONS",
    "ELECTRICAL CHARACTERISTICS",
    "TYPICAL PERFORMANCE CHARACTERISTICS",
    "PIN CONFIGURATION", "PIN CONFIGURATIONS",
    "PIN DESCRIPTION", "PIN DESCRIPTIONS", "PIN FUNCTIONS",
    "BLOCK DIAGRAM", "FUNCTIONAL BLOCK DIAGRAM",
    "APPLICATIONS INFORMATION", "APPLICATION INFORMATION",
    "APPLICATIONS", "APPLICATION CIRCUIT",
    "TYPICAL APPLICATION", "TYPICAL APPLICATIONS",
    "ORDERING INFORMATION", "ORDER INFORMATION",
    "PACKAGE INFORMATION", "PACKAGE DESCRIPTION",
    "FEATURES", "DESCRIPTION", "GENERAL DESCRIPTION",
    "REVISION HISTORY", "RELATED PARTS",
    "TABLE OF CONTENTS",
    "THEORY OF OPERATION", "FUNCTIONAL DESCRIPTION",
    "DETAILED DESCRIPTION",
    "THERMAL INFORMATION", "THERMAL CONSIDERATIONS",
    "LAYOUT", "PCB LAYOUT", "LAYOUT CONSIDERATIONS",
})


# ── Section Detection ────────────────────────────────────────────────────────

def _detect_body_font(doc) -> float:
    """Estimate the dominant body font size by mode across all pages."""
    from collections import Counter
    sizes: List[float] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    sz = round(span["size"], 1)
                    if sz > 4:
                        sizes.append(sz)
    if not sizes:
        return 10.0
    counter: Counter = Counter(sizes)
    return counter.most_common(1)[0][0]


def _is_valid_heading(line_text: str) -> bool:
    """Filter out false-positive headings (figure labels, bullets, numbers)."""
    text = line_text.strip()

    # Too short or too few words
    words = text.split()
    if len(words) < MIN_HEADING_WORDS:
        return False

    # Bullet point lines (common in datasheet features lists)
    if text.startswith(("n ", "n\t", "• ", "– ", "- ", "■ ")):
        return False

    # Figure/table labels like "68111 TA01a", "680412 F05"
    if any(w.isdigit() or (len(w) > 3 and sum(c.isdigit() for c in w) > len(w) // 2)
           for w in words[:2]):
        # First two words are mostly numeric → likely a figure label
        alpha_chars = sum(1 for c in text if c.isalpha())
        if alpha_chars < len(text) * 0.5:
            return False

    # Must contain at least one meaningful word (>= 3 alpha chars)
    has_real_word = any(len(w) >= 3 and w.isalpha() for w in words)
    if not has_real_word:
        return False

    return True


def _run_pass(
    doc,
    body_font: float,
    heading_threshold: float,
    use_bold: bool,
    use_caps: bool,
) -> List[Dict[str, Any]]:
    """Run heading detection over *doc* with configurable heuristic flags.

    This is a pure function (no closures) — extracted from _extract_sections
    so it can be tested independently.
    """
    sections: List[Dict[str, Any]] = []
    current_title = "Introduction"
    current_page_start = 1
    current_lines: List[str] = []

    def _flush(page_end: int) -> None:
        text = "\n".join(current_lines).strip()
        if text and len(text) >= MIN_SECTION_CHARS:
            sections.append({
                "title": current_title,
                "page_start": current_page_start,
                "page_end": page_end,
                "text": text,
                "is_table": False,
            })

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = " ".join(s["text"] for s in line["spans"]).strip()
                if not line_text:
                    continue

                spans = line["spans"]
                max_font = max((s["size"] for s in spans), default=0)

                # Always-on: Font-size ratio + Known dictionary
                is_large_font = max_font >= heading_threshold
                is_known = line_text.upper().strip() in KNOWN_SECTIONS

                # Conditional: Bold + ALL CAPS (only in pass 2)
                is_bold_heading = False
                is_caps_heading = False

                if use_bold:
                    is_bold = any(s["flags"] & 16 for s in spans)
                    is_bold_heading = (is_bold and len(line_text) < 80
                                       and max_font >= body_font * 0.95)

                if use_caps:
                    alpha_only = "".join(c for c in line_text if c.isalpha())
                    words = line_text.split()
                    is_caps_heading = (len(alpha_only) >= 8
                                       and alpha_only == alpha_only.upper()
                                       and len(words) >= 2)

                is_heading = (
                    (is_large_font or is_known or is_bold_heading or is_caps_heading)
                    and len(line_text) < 120
                    and not line_text.endswith(".")
                    and _is_valid_heading(line_text)
                )

                if is_heading:
                    _flush(page_num - 1 if current_lines else page_num)
                    current_title = line_text
                    current_page_start = page_num
                    current_lines = []
                else:
                    current_lines.append(line_text)

        # Extract tables as separate chunks (inside page loop)
        try:
            tables = page.find_tables()
            for tbl in tables.tables:
                md = _table_to_markdown(tbl)
                if md:
                    sections.append({
                        "title": f"{current_title} (Table)",
                        "page_start": page_num,
                        "page_end": page_num,
                        "text": md,
                        "is_table": True,
                    })
        except Exception:
            pass  # find_tables not available in older PyMuPDF

    _flush(len(doc))
    return sections


def _extract_sections(doc) -> List[Dict[str, Any]]:
    """
    Extract sections from a PDF using a two-pass heuristic strategy.

    Pass 1 (precise): Font-size ratio + Known section dictionary.
    Pass 2 (fallback): Adds bold detection + ALL CAPS if Pass 1 finds
        fewer than MIN_HEADINGS_FOR_PASS1 unique headings.
    Falls back to one-section-per-page if no headings found at all.
    """
    body_font = _detect_body_font(doc)
    heading_threshold = body_font * MIN_HEADING_FONT_RATIO
    MIN_HEADINGS_FOR_PASS1 = 5

    # Pass 1: font-size + known dictionary only
    sections = _run_pass(doc, body_font, heading_threshold,
                         use_bold=False, use_caps=False)
    heading_count = len(set(s["title"] for s in sections))

    if heading_count >= MIN_HEADINGS_FOR_PASS1:
        found_headings = True
    else:
        # Pass 2: add bold + ALL CAPS as rescue
        sections = _run_pass(doc, body_font, heading_threshold,
                             use_bold=True, use_caps=True)
        found_headings = len(sections) > 1

    # Fallback: if no headings found, one section per page
    if not found_headings or not sections:
        sections = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("text").strip()
            if text:
                sections.append({
                    "title": f"Page {page_idx + 1}",
                    "page_start": page_idx + 1,
                    "page_end": page_idx + 1,
                    "text": text,
                    "is_table": False,
                })

    return sections


def _table_to_markdown(tbl) -> str:
    """Convert PyMuPDF table object to markdown string."""
    rows: List[List[str]] = tbl.extract()
    if not rows:
        return ""
    lines = []
    for i, row in enumerate(rows):
        cells = [str(c or "").strip().replace("\n", " ") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_section(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Split a section into chunks. If text <= SECTION_CHUNK_MAX, returns one chunk.
    Otherwise splits with overlap.
    """
    text = section["text"]
    meta_base = {
        "section_title": section["title"],
        "page_start": section["page_start"],
        "page_end": section["page_end"],
        "is_table": section["is_table"],
    }

    if len(text) <= SECTION_CHUNK_MAX:
        return [{**meta_base, "text": text, "chunk_idx": 0}]

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + SECTION_CHUNK_SIZE
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({**meta_base, "text": chunk_text, "chunk_idx": idx})
            idx += 1
        start += SECTION_CHUNK_SIZE - SECTION_CHUNK_OVERLAP

    return chunks


# ── Component Card Generation ────────────────────────────────────────────────

def _generate_card(sections: List[Dict[str, Any]], component_name: str,
                   model: str, api_key: str) -> Dict[str, Any]:
    """Call Gemini to produce a structured Component Card JSON.

    Uses a two-step prompt: first identify category, then fill the
    matching key_electrical schema from CARD_SCHEMAS.
    """
    import logging
    _log = logging.getLogger("build_index")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Build condensed section overview (first 200 chars per section, max 25)
    overview_lines: List[str] = []
    for s in sections:
        if not s["is_table"]:
            preview = s["text"][:200].replace("\n", " ")
            overview_lines.append(f"[{s['title']} (p{s['page_start']})] {preview}")
    overview = "\n".join(overview_lines[:25])

    # Deduplicate section list
    seen: set = set()
    deduped_sections: List[Dict[str, str]] = []
    for s in sections:
        if s["is_table"]:
            continue
        title: str = s["title"]
        if title not in seen:
            seen.add(title)
            deduped_sections.append({
                "title": title,
                "pages": f"{s['page_start']}-{s['page_end']}",
            })

    total_pages: int = sections[-1]["page_end"] if sections else 0
    sections_json: str = json.dumps(deduped_sections[:12])
    schemas_json: str = json.dumps(CARD_SCHEMAS, indent=2)
    valid_categories: str = ", ".join(CARD_SCHEMAS.keys())

    prompt = f"""You are a technical documentation parser. Extract a structured Component Card.

Component name: {component_name}
Total pages: {total_pages}

Datasheet section overview:
{overview}

Available category schemas:
{schemas_json}

Step 1: Identify the component category from: {valid_categories}
Step 2: Fill key_electrical using ONLY the fields from the matching schema.
  - Replace every "..." with the actual value from the datasheet.
  - Use "N/A" only if the datasheet truly does not contain that parameter.
  - If no specific category matches, use "generic" and fill param_1..param_6 with the 6 most important specs.

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "component": "{component_name}",
  "category": "<one of: {valid_categories}>",
  "manufacturer": "...",
  "package": "...",
  "absolute_maximum_ratings": {{"Vcc_max": "...", "Vin_max": "...", "Temp_operating": "..."}},
  "key_electrical": {{<fields from matching schema>}},
  "sections": {sections_json},
  "total_pages": {total_pages},
  "generated_by": "{model}"
}}"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    raw: str = (response.text or "").strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        card: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "component": component_name,
            "category": "generic",
            "sections": deduped_sections[:12],
            "total_pages": total_pages,
            "generated_by": model,
            "parse_error": "Card JSON could not be parsed from model output",
        }

    # Post-generation validation
    category: str = str(card.get("category", "generic")).lower()
    if category not in CARD_SCHEMAS:
        _log.warning("Unknown category '%s' — normalising to 'generic'", category)
        card["category"] = "generic"

    key_elec: Dict[str, Any] = card.get("key_electrical", {})
    non_na = [v for v in key_elec.values() if v not in ("...", "N/A", "", None)]
    if len(non_na) < 3:
        _log.warning(
            "Component Card for '%s' has only %d non-N/A key_electrical fields",
            component_name, len(non_na),
        )

    return card


# ── Main ──────────────────────────────────────────────────────────────────────

def build_index(pdf_path: str, model: str = "gemini-3.1-flash-lite-preview",
                generate_card: bool = True) -> Tuple[str, Optional[str]]:
    """
    Build .index.json and optionally .card.json for a datasheet PDF.

    Returns:
        (index_path, card_path or None)
    """
    try:
        import fitz
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(pdf_path):
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    base = os.path.splitext(pdf_path)[0]
    component_name = os.path.basename(base)
    index_path = base + ".index.json"
    card_path = base + ".card.json"

    print(f"Opening PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    print(f"  Pages: {len(doc)}")

    print("Detecting sections...")
    sections = _extract_sections(doc)
    print(f"  Found {len(sections)} sections")
    doc.close()

    print("Chunking sections...")
    all_chunks: List[Dict[str, Any]] = []
    for section in sections:
        all_chunks.extend(_chunk_section(section))
    print(f"  Total chunks: {len(all_chunks)}")

    # Save index
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"component": component_name, "chunks": all_chunks}, f,
                  ensure_ascii=False, indent=2)
    print(f"  Saved: {index_path}")

    # Generate card
    card_out: Optional[str] = None
    if generate_card:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY not set — skipping card generation.", file=sys.stderr)
        else:
            print(f"Generating Component Card via {model}...")
            card = _generate_card(sections, component_name, model, api_key)
            with open(card_path, "w", encoding="utf-8") as f:
                json.dump(card, f, ensure_ascii=False, indent=2)
            print(f"  Saved: {card_path}")
            card_out = card_path

    return index_path, card_out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build BM25 index and Component Card for a datasheet PDF."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--model", default="gemini-3.1-flash-lite-preview",
                        help="Gemini model for card generation")
    parser.add_argument("--no-card", action="store_true",
                        help="Skip Component Card generation (no API key needed)")
    args = parser.parse_args()

    build_index(args.pdf, model=args.model, generate_card=not args.no_card)
    print("Done.")


if __name__ == "__main__":
    main()
