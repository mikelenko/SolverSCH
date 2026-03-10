"""
Test Multimodal Vision Pipeline (Qwen 14B + Moondream).
Requires a running Ollama instance with qwen2.5-coder:14b and moondream models.
Run with: pytest tests/test_multimodal_vision.py -v -m ollama
"""

import asyncio
import logging
import pytest
import aiohttp
from solver_sch.ai.design_reviewer import DesignReviewAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _ollama_is_running() -> bool:
    """Check if Ollama is reachable."""
    async def _check() -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get("http://localhost:11434/api/tags") as r:
                    return r.status == 200
        except Exception:
            pass
        return False
    result: bool = asyncio.run(_check())
    return result


# Skip entire module if Ollama is not available
pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not _ollama_is_running(), reason="Ollama not running"),
]

PAYLOAD = {
    "netlist_components": ["U1_LM358", "SENSOR_TEMP"],
    "pcb_routing_warning": (
        "Wykryto bezpośrednie połączenie ścieżki sygnałowej "
        "'TEMP_OUT' do Pinu 8 układu U1_LM358."
    ),
}

INTENT = (
    "CRITICAL DIRECTIVE: We have a suspicious connection where a 3.3V sensor "
    "connects to Pin 8 of an LM358. "
    "STEP 1: You DO NOT know what Pin 8 is. You MUST immediately use the "
    "`analyze_diagram` tool on 'Import/LM358_pinout.png'. "
    "DO NOT generate the final report format yet. Output ONLY the tool call "
    "if you haven't received the vision data. "
    "STEP 2: ONLY AFTER you receive the tool's result confirming the function "
    "of Pin 8, generate your final structured report "
    "(Executive Summary, Critical Warnings, etc.) declaring if this is a design flaw."
)


def test_report_structure():
    """The final report must contain at least one of the expected headings."""
    agent = DesignReviewAgent()
    report: str = asyncio.run(
        agent.review_design_async(PAYLOAD, {}, INTENT)
    )

    assert report, "Report should not be empty"
    assert not report.startswith("ERROR"), f"Agent returned an error: {report}"

    # At least one structural heading must be present
    expected_headings = [
        "Executive Summary",
        "Critical Warnings",
        "Design Flaws",
        "Best Practices",
    ]
    has_heading = any(h.lower() in report.lower() for h in expected_headings)
    assert has_heading, (
        f"Report must contain at least one of {expected_headings}."
    )

    print("\n" + "=" * 60)
    print("RAPORT KOŃCOWY (QWEN + Moondream):")
    print("=" * 60)
    print(report)


# Allow running directly: python tests/test_multimodal_vision.py
if __name__ == "__main__":
    if not _ollama_is_running():
        print("SKIP: Ollama is not running on localhost:11434")
        raise SystemExit(1)

    print("--- TEST MULTIMODALNY (QWEN 14B + Moondream) ---")
    print("Wysyłanie zadania do Głównego Agenta (Qwen 14B)...")
    agent = DesignReviewAgent()
    report = asyncio.run(agent.review_design_async(PAYLOAD, {}, INTENT))
    print("\n" + "=" * 60)
    print("RAPORT KOŃCOWY:")
    print("=" * 60)
    print(report)
