"""
chat.py -> Interactive CLI chat with any SolverSCH LLM provider.

Usage:
    python -m solver_sch.ai.chat                        # default: ollama
    python -m solver_sch.ai.chat --provider gemini
    python -m solver_sch.ai.chat --provider openai --model gpt-4o
    python -m solver_sch.ai.chat --provider anthropic --model claude-3-5-sonnet-20241022
    python -m solver_sch.ai.chat --provider stub        # no API key needed

Commands during chat:
    /exit  or  /quit   — end the session
    /clear             — reset conversation history
    /history           — print full conversation so far
    /system <text>     — set or replace the system prompt
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Dict, List, Optional

from solver_sch.ai.llm_providers import Message, get_provider
from solver_sch.registry import available_analyses, available_components


BANNER = """
╔══════════════════════════════════════════════════════════╗
║           SolverSCH  ·  Interactive AI Chat              ║
║  /exit  quit  |  /clear  reset  |  /history  |  /system ║
╚══════════════════════════════════════════════════════════╝
"""

# ── Tool definitions told to the LLM ──────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "name": "simulate_circuit",
        "description": (
            "Parse a SPICE netlist and run one or more circuit analyses. "
            "Call this whenever you need actual simulation numbers (node voltages, "
            "frequency response, transient waveforms)."
        ),
        "parameters": {
            "netlist": {
                "type": "string",
                "description": "Full SPICE netlist text (standard SPICE syntax)",
            },
            "analyses": {
                "type": "array",
                "description": "List of analyses to run. Valid values: 'dc', 'ac', 'transient'.",
            },
            "ac_f_start": {
                "type": "number",
                "description": "AC sweep start frequency in Hz (default: 100)",
            },
            "ac_f_stop": {
                "type": "number",
                "description": "AC sweep stop frequency in Hz (default: 100000)",
            },
            "t_stop": {
                "type": "number",
                "description": "Transient simulation stop time in seconds (default: 0.005)",
            },
            "dt": {
                "type": "number",
                "description": "Transient timestep in seconds (default: 1e-5)",
            },
        },
        "required": ["netlist", "analyses"],
    }
]

_MAX_TOOL_ROUNDS = 8  # prevent runaway loops


# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    tools_desc = "\n".join(
        f"- **{t['name']}**: {t['description']}\n"
        f"  Required parameters: {', '.join(t['required'])}"
        for t in TOOLS_SCHEMA
    )
    return (
        "You are SolverSCH, an expert analog circuit design assistant.\n\n"
        "## Autonomous Tool Use\n"
        "You have access to the following tools. Call them whenever you need simulation\n"
        "data — do NOT ask the user to run a simulation for you.\n\n"
        f"{tools_desc}\n\n"
        "To call a tool, output EXACTLY one ```json block containing 'name' and 'arguments'.\n"
        "Do NOT include any explanatory text in that same message — just the JSON block:\n"
        "```json\n"
        '{"name": "simulate_circuit", "arguments": {"netlist": "...spice...", "analyses": ["dc"]}}\n'
        "```\n"
        "After receiving the tool result you will be called again; write your full answer then.\n\n"
        "## Available Circuit Components\n"
        f"{available_components()}\n\n"
        "## Available Analyses\n"
        f"{available_analyses()}\n"
    )


# ── Tool implementations ───────────────────────────────────────────────────────

def _tool_simulate_circuit(
    netlist: str,
    analyses: List[str],
    ac_f_start: float = 100.0,
    ac_f_stop: float = 100_000.0,
    t_stop: float = 0.005,
    dt: float = 1e-5,
) -> str:
    """Parse *netlist* and run the requested *analyses*; return a JSON string."""
    from solver_sch.parser.netlist_parser import NetlistParser
    from solver_sch.simulator import Simulator

    try:
        circuit = NetlistParser.parse_netlist(netlist)
    except Exception as exc:
        return json.dumps({"error": f"Netlist parse error: {exc}"})

    try:
        sim = Simulator(circuit)
    except Exception as exc:
        return json.dumps({"error": f"Simulator init error: {exc}"})

    results: Dict[str, Any] = {}

    for analysis in analyses:
        analysis = analysis.strip().lower()
        try:
            if analysis == "dc":
                results["dc"] = sim.dc().to_dict()
            elif analysis == "ac":
                results["ac"] = sim.ac(
                    f_start=ac_f_start,
                    f_stop=ac_f_stop,
                ).to_dict()
            elif analysis == "transient":
                results["transient"] = sim.transient(
                    t_stop=t_stop,
                    dt=dt,
                ).to_dict()
            else:
                results[analysis] = {"error": f"Unknown analysis '{analysis}'"}
        except Exception as exc:
            results[analysis] = {"error": str(exc)}

    return json.dumps(results, indent=2)


def _execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Dispatch a tool call and return the result as a JSON string."""
    if name == "simulate_circuit":
        return _tool_simulate_circuit(**arguments)
    return json.dumps({"error": f"Unknown tool '{name}'"})


# ── Tool-call detection ────────────────────────────────────────────────────────

def _extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Return the first valid tool-call dict found in *text*, or None."""
    parts = text.split("```json")
    for part in parts[1:]:
        block = part.split("```")[0].strip()
        try:
            data = json.loads(block)
            if "name" in data and "arguments" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# ── Display helpers ────────────────────────────────────────────────────────────

def _print_assistant(text: str) -> None:
    print(f"\n\033[1;34mAssistant:\033[0m {text}\n")


def _print_info(text: str) -> None:
    print(f"\033[90m{text}\033[0m")


def _print_tool(name: str, result_preview: str) -> None:
    print(f"\033[33m[Tool: {name}]\033[0m {result_preview[:120]}{'…' if len(result_preview) > 120 else ''}")


# ── Main chat loop ─────────────────────────────────────────────────────────────

def run_chat(
    provider_name: str = "ollama",
    model: Optional[str] = None,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
) -> None:
    kwargs: dict = {"temperature": temperature}
    if model:
        kwargs["model"] = model

    try:
        llm = get_provider(provider_name, **kwargs)
    except Exception as exc:
        print(f"Error initialising provider '{provider_name}': {exc}", file=sys.stderr)
        sys.exit(1)

    # Use the built-in tool-aware system prompt unless the user supplied one.
    effective_system = system_prompt if system_prompt is not None else _build_system_prompt()

    print(BANNER)
    _print_info(f"Provider : {provider_name}  |  model : {getattr(llm, 'model', 'default')}")
    _print_info("Tools    : simulate_circuit  (LLM calls automatically when needed)")
    print()

    history: List[Message] = []

    while True:
        try:
            user_input = input("\033[1;32mYou:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # ── built-in commands ──────────────────────────────────────
        if user_input.startswith("/"):
            cmd, _, arg = user_input[1:].partition(" ")
            cmd = cmd.lower()

            if cmd in ("exit", "quit"):
                print("Bye!")
                break

            if cmd == "clear":
                history = []
                _print_info("Conversation history cleared.")
                continue

            if cmd == "history":
                if not history:
                    _print_info("(empty)")
                else:
                    for msg in history:
                        role = "You" if msg["role"] == "user" else "Assistant"
                        print(f"\033[90m[{role}]\033[0m {msg['content']}\n")
                continue

            if cmd == "system":
                if arg:
                    effective_system = arg
                    _print_info(f"System prompt set: {effective_system[:120]}")
                else:
                    _print_info(f"Current system prompt:\n{effective_system}")
                continue

            _print_info(f"Unknown command: /{cmd}")
            continue

        # ── agentic message loop ────────────────────────────────────
        current_msg = user_input
        try:
            for _round in range(_MAX_TOOL_ROUNDS):
                reply, history = llm.chat(
                    current_msg, history, system_instruction=effective_system
                )

                tool_call = _extract_tool_call(reply)
                if tool_call is None:
                    # No tool call — final answer.
                    _print_assistant(reply)
                    break

                # Execute the tool.
                tool_name = tool_call["name"]
                tool_args = tool_call.get("arguments", {})
                _print_info(f"→ calling tool: {tool_name}({list(tool_args.keys())})")
                result_json = _execute_tool(tool_name, tool_args)
                _print_tool(tool_name, result_json)

                # Inject result as next user message so all providers see it.
                current_msg = f"[Tool result: {tool_name}]\n{result_json}"
            else:
                _print_info("(reached max tool rounds — stopping)")

        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m", file=sys.stderr)
            traceback.print_exc()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive CLI chat with a SolverSCH LLM provider."
    )
    parser.add_argument(
        "--provider", "-p",
        default="ollama",
        choices=["gemini", "openai", "anthropic", "claude", "ollama", "stub"],
        help="LLM provider to use (default: ollama)",
    )
    parser.add_argument("--model", "-m", default=None, help="Model name override")
    parser.add_argument(
        "--temperature", "-t", type=float, default=0.7, help="Sampling temperature (default: 0.7)"
    )
    parser.add_argument(
        "--system", "-s", default=None,
        help="System prompt to use throughout the conversation (overrides built-in tool prompt)",
    )
    args = parser.parse_args()

    run_chat(
        provider_name=args.provider,
        model=args.model,
        temperature=args.temperature,
        system_prompt=args.system,
    )


if __name__ == "__main__":
    main()
