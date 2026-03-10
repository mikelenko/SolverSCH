"""
Integration tests for Simulator.review() pipeline.
Tests 1, 2, 4 mock DesignReviewAgent — no API key required.
Test 3 verifies the error path when GEMINI_API_KEY is missing.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch

from solver_sch import Simulator, Circuit
from solver_sch.model.circuit import Resistor, VoltageSource


CANNED_REPORT = (
    "# Executive Summary\nTest report.\n"
    "# Critical Warnings\nNone.\n"
    "# Design Flaws\nNone.\n"
    "# Best Practices Recommendations\nAll good.\n"
)


def _make_divider() -> Simulator:
    ckt = Circuit("Divider")
    ckt.add_component(VoltageSource("V1", "in", "0", 12.0))
    ckt.add_component(Resistor("R1", "in", "out", 10000))
    ckt.add_component(Resistor("R2", "out", "0", 1000))
    return Simulator(ckt)


class TestReviewPipeline:

    def test_review_builds_payload_correctly(self, monkeypatch):
        """circuit_info has bom + nodes; sim_results has 'dc' key with node_voltages."""
        sim = _make_divider()
        dc = sim.dc()

        captured = {}

        async def fake_review(_self, circuit_info, sim_results, intent):
            captured["circuit_info"] = circuit_info
            captured["sim_results"] = sim_results
            return CANNED_REPORT

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch("solver_sch.ai.design_reviewer.DesignReviewAgent.review_design_async",
                   new=fake_review):
            asyncio.run(sim.review(dc_result=dc, intent="Test intent"))

        ci = captured["circuit_info"]
        assert "bom" in ci
        assert "nodes" in ci
        assert len(ci["bom"]) == 3  # V1, R1, R2

        sr = captured["sim_results"]
        assert "dc" in sr
        assert "node_voltages_V" in sr["dc"]

    def test_review_returns_markdown_string(self, monkeypatch):
        """Return value is a str containing all four required markdown sections."""
        sim = _make_divider()
        dc = sim.dc()

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch("solver_sch.ai.design_reviewer.DesignReviewAgent.review_design_async",
                   new=AsyncMock(return_value=CANNED_REPORT)):
            result = asyncio.run(sim.review(dc_result=dc))

        assert isinstance(result, str)
        assert "# Executive Summary" in result
        assert "# Critical Warnings" in result
        assert "# Design Flaws" in result
        assert "# Best Practices Recommendations" in result

    def test_review_without_api_key_raises(self, monkeypatch):
        """Missing GEMINI_API_KEY propagates ValueError from DesignReviewAgent."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        sim = _make_divider()
        dc = sim.dc()

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            asyncio.run(sim.review(dc_result=dc))

    def test_review_accepts_partial_results(self, monkeypatch):
        """Passing only dc_result (no ac/transient) does not raise."""
        sim = _make_divider()
        dc = sim.dc()

        captured = {}

        async def fake_review(_self, circuit_info, sim_results, intent):
            captured["sim_results"] = sim_results
            return CANNED_REPORT

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch("solver_sch.ai.design_reviewer.DesignReviewAgent.review_design_async",
                   new=fake_review):
            result = asyncio.run(sim.review(dc_result=dc))

        assert "dc" in captured["sim_results"]
        assert "ac" not in captured["sim_results"]
        assert "transient" not in captured["sim_results"]
        assert isinstance(result, str)
