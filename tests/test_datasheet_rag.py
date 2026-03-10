"""
Unit tests for tool_query_datasheet (BM25 PDF RAG tool).
Tests run without Ollama — they exercise the tool function directly.
"""

import asyncio
import os
import pytest

import solver_sch.ai.tools as dr_module
from solver_sch.ai.design_reviewer import tool_query_datasheet, _datasheet_cache


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_bm25_cache(chunks: list, pages: list) -> None:
    """Pre-populate the BM25 cache so tests skip file I/O."""
    from rank_bm25 import BM25Plus
    tokenized = [c.lower().split() for c in chunks]
    key = "test_ic"
    _datasheet_cache[key] = {
        "chunks": chunks,
        "pages": pages,
        "bm25": BM25Plus(tokenized),
    }


@pytest.fixture(autouse=True)
def clear_cache():
    """Isolate tests by flushing the module-level BM25 cache."""
    _datasheet_cache.clear()
    yield
    _datasheet_cache.clear()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestQueryDatasheetErrors:

    def test_pdf_not_found_returns_error(self, monkeypatch, tmp_path):
        """Returns an error dict when the PDF doesn't exist."""
        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        result = asyncio.run(tool_query_datasheet("NONEXISTENT", "voltage rating"))
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_missing_deps_returns_error(self, monkeypatch):
        """Returns an error if PyMuPDF/rank_bm25 are unavailable."""
        monkeypatch.setattr(dr_module, "HAS_PDF_DEPS", False)
        result = asyncio.run(tool_query_datasheet("LM358", "input voltage"))
        assert "error" in result
        assert "not installed" in result["error"].lower()

    def test_image_only_pdf_returns_error(self, monkeypatch, tmp_path):
        """Returns an error when no text can be extracted from the PDF."""
        import fitz
        # Create a blank (no-text) PDF
        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "blank.pdf"
        doc.save(str(pdf_path))
        doc.close()

        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        result = asyncio.run(tool_query_datasheet("blank", "anything"))
        assert "error" in result
        assert "text" in result["error"].lower() or "image" in result["error"].lower()


class TestQueryDatasheetRetrieval:

    def test_basic_retrieval(self):
        """Returns relevant chunks for a keyword query (using pre-populated cache)."""
        _make_bm25_cache(
            chunks=[
                "Absolute Maximum Ratings: Supply Voltage 32V, Input Voltage Range -0.3 to 32V",
                "Electrical Characteristics: Input Offset Voltage 2mV typical, Input Bias Current 45nA",
                "Pin Configuration: Pin 1 Output A, Pin 2 Inverting Input A, Pin 8 Non-Inverting Input B",
            ],
            pages=[1, 2, 3],
        )
        result = asyncio.run(tool_query_datasheet("TEST_IC", "supply voltage maximum rating"))
        assert "results" in result
        assert len(result["results"]) >= 1
        # Top result should be from the Absolute Maximum Ratings chunk (page 1)
        assert result["results"][0]["page"] == 1

    def test_result_structure(self):
        """Every result entry has page (int), text (str), and score (float)."""
        _make_bm25_cache(
            chunks=["Maximum drain-source voltage 60V", "Gate threshold voltage 1.5V"],
            pages=[3, 5],
        )
        result = asyncio.run(tool_query_datasheet("TEST_IC", "drain source voltage"))
        assert "results" in result
        for entry in result["results"]:
            assert isinstance(entry["page"], int)
            assert isinstance(entry["text"], str)
            assert isinstance(entry["score"], float)
            assert entry["score"] > 0

    def test_cache_reuse(self):
        """Two queries on the same component share the BM25 index and return different top results."""
        _make_bm25_cache(
            chunks=["Maximum supply voltage 15V", "Output short circuit current 40mA"],
            pages=[1, 2],
        )
        r1 = asyncio.run(tool_query_datasheet("TEST_IC", "supply voltage"))
        r2 = asyncio.run(tool_query_datasheet("TEST_IC", "output current"))
        assert "results" in r1
        assert "results" in r2
        # Top hits should differ for distinct queries
        assert r1["results"][0]["text"] != r2["results"][0]["text"]

    def test_case_insensitive_component_name(self):
        """Component name lookup is normalised to lowercase for cache hits."""
        from rank_bm25 import BM25Plus
        chunks = ["Pin 1 is VCC, Pin 2 is GND"]
        tokenized = [c.lower().split() for c in chunks]
        _datasheet_cache["irf540n"] = {
            "chunks": chunks,
            "pages": [1],
            "bm25": BM25Plus(tokenized),
        }
        result = asyncio.run(tool_query_datasheet("IRF540N", "VCC pin"))
        assert "results" in result
        assert len(result["results"]) > 0

    def test_no_relevant_results_returns_empty_list(self):
        """Returns an empty results list (not an error) when query has no BM25 matches."""
        _make_bm25_cache(
            chunks=["Capacitance 100pF per pin"],
            pages=[7],
        )
        result = asyncio.run(tool_query_datasheet("TEST_IC", "zzzyyyxxx"))
        # Either no results or empty list — must not be an error
        assert "error" not in result
        assert result.get("results") == [] or result.get("note") is not None


class TestQueryDatasheetWithRealPDF:

    def test_real_pdf_extraction_and_query(self, monkeypatch, tmp_path):
        """Creates a real multi-page PDF and verifies BM25 retrieval end-to-end."""
        import fitz
        pages_text = [
            "LM358 Dual Operational Amplifier\nAbsolute Maximum Ratings\nSupply Voltage: 32V\nInput Voltage: -0.3V to 32V\n",
            "Electrical Characteristics\nInput Offset Voltage: 2mV typical, 7mV max\nOpen Loop Gain: 100dB\n",
            "Pin Descriptions\nPin 1: Output A\nPin 2: Inverting Input A\nPin 3: Non-Inverting Input A\nPin 8: VCC\n",
        ]
        doc = fitz.open()
        for text in pages_text:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=11)
        pdf_path = tmp_path / "lm358.pdf"
        doc.save(str(pdf_path))
        doc.close()

        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        result = asyncio.run(tool_query_datasheet("LM358", "supply voltage maximum rating"))

        assert "results" in result
        assert len(result["results"]) > 0
        # The top result should mention voltage
        top_text = result["results"][0]["text"].lower()
        assert "voltage" in top_text or "supply" in top_text
        # Page numbers should be valid integers >= 1
        for entry in result["results"]:
            assert entry["page"] >= 1
