"""
Tests for Hierarchical RAG:
- build_index.py (offline indexer)
- tool_query_datasheet with pre-built .index.json
- _load_component_cards + _format_prompt card injection
- section metadata in query results
- fallback to live PDF when .index.json absent
"""

import asyncio
import json
import os
import pytest

import solver_sch.ai.tools as dr_module
from solver_sch.ai.design_reviewer import (
    tool_query_datasheet,
    _datasheet_cache,
    DesignReviewAgent,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    _datasheet_cache.clear()
    yield
    _datasheet_cache.clear()


def _write_index(tmp_path, component: str, chunks: list) -> str:
    """Write a minimal .index.json file and return its path."""
    index = {"component": component, "chunks": chunks}
    path = tmp_path / f"{component}.index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return str(path)


def _write_card(tmp_path, component: str, card: dict) -> str:
    path = tmp_path / f"{component}.card.json"
    path.write_text(json.dumps(card), encoding="utf-8")
    return str(path)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBuildIndex:

    def test_build_index_creates_index_json(self, tmp_path):
        """build_index on a real multi-page PDF creates a valid .index.json."""
        import fitz
        from datasheets.build_index import build_index

        pages_text = [
            "Absolute Maximum Ratings\nSupply Voltage 32V\nInput Voltage -0.3V to 32V\n",
            "Electrical Characteristics\nInput Offset Voltage 2mV typ\nOpen Loop Gain 100dB\n",
            "Pin Descriptions\nPin 1 Output A\nPin 8 VCC\n",
        ]
        doc = fitz.open()
        for text in pages_text:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=11)
        pdf_path = tmp_path / "TestIC.pdf"
        doc.save(str(pdf_path))
        doc.close()

        index_path, card_path = build_index(str(pdf_path), generate_card=False)

        assert os.path.isfile(index_path)
        assert card_path is None  # --no-card

        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["component"] == "TestIC"
        assert len(data["chunks"]) > 0
        first_chunk = data["chunks"][0]
        assert "text" in first_chunk
        assert "page_start" in first_chunk
        assert "section_title" in first_chunk


class TestQueryWithPrebuiltIndex:

    def test_query_uses_prebuilt_index(self, monkeypatch, tmp_path):
        """tool_query_datasheet loads from .index.json without opening a PDF."""
        chunks = [
            {"text": "Absolute Maximum Ratings: Supply Voltage 32V", "page_start": 1,
             "page_end": 1, "section_title": "Absolute Maximum Ratings", "is_table": False},
            {"text": "Electrical Characteristics: Input Offset 2mV", "page_start": 2,
             "page_end": 2, "section_title": "Electrical Characteristics", "is_table": False},
        ]
        _write_index(tmp_path, "testchip", chunks)
        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))

        # Patch fitz.open to fail — proves PDF is never opened
        import unittest.mock as mock
        with mock.patch("solver_sch.ai.tools.fitz") as mock_fitz:
            mock_fitz.open.side_effect = AssertionError("Should not open PDF when index exists")
            result = asyncio.run(tool_query_datasheet("testchip", "supply voltage maximum"))

        assert "results" in result
        assert len(result["results"]) > 0

    def test_section_metadata_in_results(self, monkeypatch, tmp_path):
        """Results from pre-built index include 'section' key."""
        chunks = [
            {"text": "Maximum drain-source voltage 60V", "page_start": 3,
             "page_end": 3, "section_title": "Absolute Maximum Ratings", "is_table": False},
            {"text": "Gate threshold voltage 1.5V to 3.0V", "page_start": 5,
             "page_end": 5, "section_title": "Electrical Characteristics", "is_table": False},
        ]
        _write_index(tmp_path, "irf540n", chunks)
        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))

        result = asyncio.run(tool_query_datasheet("IRF540N", "drain source voltage"))
        assert "results" in result
        for entry in result["results"]:
            assert "section" in entry
            assert isinstance(entry["section"], str)

    def test_fallback_without_index(self, monkeypatch, tmp_path):
        """If .index.json absent but PDF present, falls back to live parsing."""
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Supply Voltage 15V maximum rating", fontsize=11)
        pdf_path = tmp_path / "lm741.pdf"
        doc.save(str(pdf_path))
        doc.close()

        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        result = asyncio.run(tool_query_datasheet("lm741", "supply voltage"))
        assert "results" in result
        assert len(result["results"]) > 0


class TestComponentCardInjection:

    def test_card_injected_into_prompt(self, monkeypatch, tmp_path):
        """_format_prompt includes ### COMPONENT DATASHEETS when card file exists."""
        card = {
            "component": "LM358",
            "category": "Dual Operational Amplifier",
            "absolute_maximum_ratings": {"Vcc_max": "32V"},
            "key_electrical": {"GBW": "1.1 MHz"},
            "sections": [{"title": "Pin Configuration", "pages": "3"}],
        }
        _write_card(tmp_path, "lm358", card)
        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        agent = DesignReviewAgent()
        circuit_info = {
            "bom": [{"ref": "U1_LM358", "type": "OpAmp", "nodes": ["in", "out"]}]
        }
        prompt = agent._format_prompt(circuit_info, {}, "Test review")

        assert "### COMPONENT DATASHEETS" in prompt
        assert "LM358" in prompt

    def test_no_card_section_when_no_cards(self, monkeypatch, tmp_path):
        """_format_prompt shows 'No datasheets indexed.' when no card files exist."""
        monkeypatch.setattr(dr_module, "DATASHEETS_DIR", str(tmp_path))
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        agent = DesignReviewAgent()
        circuit_info = {"bom": [{"ref": "R1", "type": "Resistor", "nodes": ["a", "b"]}]}
        prompt = agent._format_prompt(circuit_info, {}, "Test review")

        assert "No datasheets indexed." in prompt
