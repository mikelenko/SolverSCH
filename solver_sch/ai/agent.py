"""
agent.py — Two-phase (Discovery & Reporting) agentic review loop.

Pure function `run_review` takes an LLMClient, messages, ToolRegistry,
and optional allowed_tools list, then returns a markdown report string.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from solver_sch.ai.llm_backends import LLMClient
from solver_sch.ai.tools import (
    ToolRegistry,
    tool_analyze_diagram,
    tool_query_datasheet,
)

logger = logging.getLogger("solver_sch.ai.agent")


async def run_review(
    llm_client: LLMClient,
    messages: List[Dict[str, Any]],
    registry: ToolRegistry,
    allowed_tools: Optional[List[str]] = None,
) -> str:
    """Run the two-phase discovery + reporting loop.

    Phase 1: Discovery — model calls tools until it says READY (max 3 iterations).
    Phase 2: Reporting — model generates final markdown report without tools.

    Returns the markdown report string.
    """
    # ==========================================
    # PHASE 1: DISCOVERY (Tool exploration)
    # ==========================================
    discovery_directive = (
        "CRITICAL DIRECTIVE FOR THIS TURN: You are in the DISCOVERY PHASE. "
        "Analyze the request. If you need more information, output ONLY the JSON for the required tool. "
        "DO NOT write any analysis yet. If you have all data, reply with exactly: READY."
    )
    messages.append({"role": "user", "content": discovery_directive})

    max_iterations = 3
    executed_calls: Set[Tuple[str, str]] = set()

    for i in range(max_iterations):
        try:
            logger.info(f"Discovery iteration {i + 1}...")
            response = await llm_client.call_async(
                messages, tools=registry.get_schemas(allowed_tools)
            )
            message = response.get("message", {})
            content = message.get("content", "").strip()
            tool_calls = message.get("tool_calls", [])

            if content == "READY":
                logger.info("Discovery complete. Model reported READY.")
                messages.append({"role": "assistant", "content": "READY"})
                break

            # Fallback JSON parsing
            if not tool_calls:
                json_str = ""
                if "```json" in content:
                    json_str = content.split("```json")[-1].split("```")[0].strip()
                elif content.startswith("{") and content.endswith("}"):
                    json_str = content

                if json_str:
                    try:
                        call_data = json.loads(json_str)
                        if isinstance(call_data, dict) and "name" in call_data:
                            tool_calls = [{"function": call_data}]
                        elif isinstance(call_data, list) and len(call_data) > 0:
                            tool_calls = [{"function": c} for c in call_data if "name" in c]
                    except json.JSONDecodeError:
                        pass

            if tool_calls:
                had_error = False
                last_error_msg = ""
                any_executed = False

                for call in tool_calls:
                    func_name = call.get("function", {}).get("name", "unknown")
                    args = call.get("function", {}).get("arguments", {})
                    call_key = (func_name, json.dumps(args, sort_keys=True))

                    if call_key in executed_calls:
                        logger.info(f"[PHASE 1] Skipping duplicate call: {func_name}")
                        continue

                    if not any_executed:
                        messages.append(message)
                    any_executed = True

                    logger.info(f"[PHASE 1] Executing tool: {func_name}")
                    executed_calls.add(call_key)

                    if func_name == "analyze_diagram":
                        result = await tool_analyze_diagram(**args)
                    elif func_name == "query_datasheet":
                        result = await tool_query_datasheet(**args)
                    elif func_name in registry._tools:
                        result = registry._tools[func_name]["func"](**args)
                    else:
                        result = {"error": f"Tool '{func_name}' not found"}

                    if isinstance(result, dict) and "error" in result:
                        had_error = True
                        last_error_msg = result["error"]

                    messages.append({"role": "tool", "content": json.dumps(result)})

                if not any_executed:
                    logger.info("[PHASE 1] All tool calls were duplicates. Forcing READY.")
                    messages.append({"role": "user", "content": (
                        "All requested tool calls have already been executed. "
                        "The results are in the conversation above. "
                        "You MUST now respond with exactly: READY"
                    )})
                elif had_error:
                    messages.append({"role": "user", "content": (
                        f"The tool returned an error: {last_error_msg}. "
                        f"Do NOT retry with the same parameters. "
                        f"Either try different parameters or say READY to proceed with available data."
                    )})
                else:
                    messages.append({"role": "user", "content": (
                        "Tool results provided above. Analyze the results. "
                        "If you need MORE data from a DIFFERENT tool or query, output the tool JSON. "
                        "Otherwise, output exactly: READY"
                    )})
            else:
                # No tool calls and no READY — move to phase 2
                break
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            break

    # ==========================================
    # PHASE 2: REPORTING (Tool-locked)
    # ==========================================
    logger.info("[PHASE 2] Generating final engineering report...")
    reporting_directive = (
        "DISCOVERY COMPLETE. All tool data has been gathered. "
        "NOW generate the final structured engineering report using ONLY markdown prose. "
        "You MUST include these sections: # Executive Summary, # Critical Warnings, "
        "# Design Flaws, # Best Practices Recommendations. "
        "ABSOLUTELY DO NOT output any JSON, tool calls, or code blocks. Only markdown text."
    )
    messages.append({"role": "user", "content": reporting_directive})

    try:
        response = await llm_client.call_async(messages, tools=None)
        return response.get("message", {}).get("content", "ERROR: Empty report content")
    except Exception as e:
        return f"ERROR during reporting phase: {str(e)}"
