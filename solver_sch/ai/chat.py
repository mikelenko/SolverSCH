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
import sys
from typing import List, Optional

from solver_sch.ai.llm_providers import Message, get_provider


BANNER = """
╔══════════════════════════════════════════════════════════╗
║           SolverSCH  ·  Interactive AI Chat              ║
║  /exit  quit  |  /clear  reset  |  /history  |  /system ║
╚══════════════════════════════════════════════════════════╝
"""


def _print_assistant(text: str) -> None:
    print(f"\n\033[1;34mAssistant:\033[0m {text}\n")


def _print_info(text: str) -> None:
    print(f"\033[90m{text}\033[0m")


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

    print(BANNER)
    _print_info(f"Provider : {provider_name}  |  model : {getattr(llm, 'model', 'default')}")
    if system_prompt:
        _print_info(f"System   : {system_prompt}")
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
                    system_prompt = arg
                    _print_info(f"System prompt set: {system_prompt}")
                else:
                    _print_info(f"Current system prompt: {system_prompt or '(none)'}")
                continue

            _print_info(f"Unknown command: /{cmd}")
            continue

        # ── normal message ─────────────────────────────────────────
        try:
            reply, history = llm.chat(user_input, history, system_instruction=system_prompt)
            _print_assistant(reply)
        except Exception as exc:
            print(f"\033[31mError: {exc}\033[0m", file=sys.stderr)


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
        help="System prompt to use throughout the conversation",
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
