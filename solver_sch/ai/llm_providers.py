"""
llm_providers.py -> Provider-agnostic LLM interface for SolverSCH.

Decouples the AutonomousDesigner from any single AI vendor.
Supports Google Gemini, OpenAI GPT, Anthropic Claude, and local Ollama.

Usage:
    from solver_sch.ai.llm_providers import get_provider

    llm = get_provider("gemini")           # Uses GEMINI_API_KEY env var
    llm = get_provider("openai")           # Uses OPENAI_API_KEY env var
    llm = get_provider("ollama", model="llama3")  # Local Ollama
    llm = get_provider("stub")             # Offline stub for testing

    # Single-turn
    response = llm.generate("Design an RC low-pass filter at 1kHz.")

    # Multi-turn chat
    history = []
    reply, history = llm.chat("What is a low-pass filter?", history)
    reply, history = llm.chat("Give me an RC example at 1kHz.", history)

Message history format:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
"""

from __future__ import annotations

import os
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

logger = logging.getLogger("solver_sch.ai.llm_providers")


Message = Dict[str, str]  # {"role": "user"|"assistant", "content": "..."}


class LLMProvider(ABC):
    """Abstract base class for LLM API providers.

    Implement `generate(prompt)` to add a new provider.
    `chat()` has a default implementation built on top of `generate()`,
    but providers can override it to use native multi-turn APIs.
    """

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Send a single prompt and return the text response.

        Args:
            prompt: User message / prompt to send.
            system_instruction: Optional system-level instruction (role definition).

        Returns:
            The LLM text response as a string.
        """

    def chat(
        self,
        message: str,
        history: Optional[List[Message]] = None,
        system_instruction: Optional[str] = None,
    ) -> tuple[str, List[Message]]:
        """Send a message in a multi-turn conversation.

        Args:
            message: The new user message.
            history: Previous messages as a list of {"role", "content"} dicts.
                     Pass [] or None to start a fresh conversation.
            system_instruction: Optional system prompt (applied on every turn).

        Returns:
            (reply, updated_history) — the assistant's reply and the full
            updated history including the new turn.
        """
        history = list(history) if history else []
        history.append({"role": "user", "content": message})
        # Build a single prompt from history for providers that don't natively
        # support message arrays (overridden in providers that do).
        full_prompt = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history
        )
        reply = self.generate(full_prompt, system_instruction=system_instruction)
        history.append({"role": "assistant", "content": reply})
        return reply, history


class GeminiProvider(LLMProvider):
    """Google Gemini API provider.

    Requires: pip install google-genai
    Config: GEMINI_API_KEY environment variable.
    """

    def __init__(self, model: str = "gemini-2.5-flash", temperature: float = 0.1) -> None:
        self.model = model
        self.temperature = temperature
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        from google.genai import types, errors
        max_retries = 5
        for attempt in range(max_retries):
            try:
                config = types.GenerateContentConfig(temperature=self.temperature)
                if system_instruction:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=self.temperature,
                    )
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except errors.ClientError as e:
                if e.code == 429:
                    if attempt >= max_retries - 1:
                        raise
                    logger.warning("Gemini rate limit hit (429). Retrying %d/%d in 45s...", attempt + 1, max_retries)
                    time.sleep(45)
                else:
                    raise

    def chat(
        self,
        message: str,
        history: Optional[List[Message]] = None,
        system_instruction: Optional[str] = None,
    ) -> tuple[str, List[Message]]:
        from google.genai import types, errors
        history = list(history) if history else []
        history.append({"role": "user", "content": message})
        # Gemini uses "user"/"model" roles and Content objects
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in history
        ]
        config = types.GenerateContentConfig(temperature=self.temperature)
        if system_instruction:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=self.temperature,
            )
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                reply = response.text
                history.append({"role": "assistant", "content": reply})
                return reply, history
            except errors.ClientError as e:
                if e.code == 429:
                    if attempt >= max_retries - 1:
                        raise
                    logger.warning("Gemini rate limit hit (429). Retrying %d/%d in 45s...", attempt + 1, max_retries)
                    time.sleep(45)
                else:
                    raise


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider.

    Requires: pip install openai
    Config: OPENAI_API_KEY environment variable.
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.1) -> None:
        self.model = model
        self.temperature = temperature
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        import openai
        self._client = openai.OpenAI(api_key=api_key)

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def chat(
        self,
        message: str,
        history: Optional[List[Message]] = None,
        system_instruction: Optional[str] = None,
    ) -> tuple[str, List[Message]]:
        history = list(history) if history else []
        history.append({"role": "user", "content": message})
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.extend(history)
        response = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=self.temperature
        )
        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        return reply, history


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider.

    Requires: pip install anthropic
    Config: ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self, model: str = "claude-3-5-haiku-20241022", temperature: float = 0.1) -> None:
        self.model = model
        self.temperature = temperature
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        kwargs = {"model": self.model, "max_tokens": 4096, "temperature": self.temperature,
                  "messages": [{"role": "user", "content": prompt}]}
        if system_instruction:
            kwargs["system"] = system_instruction
        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def chat(
        self,
        message: str,
        history: Optional[List[Message]] = None,
        system_instruction: Optional[str] = None,
    ) -> tuple[str, List[Message]]:
        history = list(history) if history else []
        history.append({"role": "user", "content": message})
        kwargs: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "messages": history,
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        response = self._client.messages.create(**kwargs)
        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        return reply, history


class OllamaProvider(LLMProvider):
    """Local Ollama provider (no API key needed).

    Requires: Ollama running locally on http://localhost:11434
    Docs: https://ollama.ai
    """

    def __init__(self, model: str = "qwen2.5-coder:14b", base_url: str = "http://localhost:11434", temperature: float = 0.1) -> None:
        self.model = model
        self.base_url = base_url
        self.temperature = temperature

    def _ollama_request(self, messages: List[Message]) -> str:
        import urllib.request
        import json
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat", data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())["message"]["content"]

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        messages: List[Message] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return self._ollama_request(messages)

    def chat(
        self,
        message: str,
        history: Optional[List[Message]] = None,
        system_instruction: Optional[str] = None,
    ) -> tuple[str, List[Message]]:
        history = list(history) if history else []
        history.append({"role": "user", "content": message})
        messages: List[Message] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.extend(history)
        reply = self._ollama_request(messages)
        history.append({"role": "assistant", "content": reply})
        return reply, history


class StubProvider(LLMProvider):
    """Offline stub provider for testing / development without API keys.

    Returns a static valid SPICE netlist so the pipeline can be tested end-to-end.
    Accepts (and ignores) common kwargs like temperature/model for API compatibility.
    """

    def __init__(self, model: str = "stub", temperature: float = 0.1, **_kwargs) -> None:
        self.model = model
        self.temperature = temperature

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        logger.info("[StubProvider] Returning canned RC filter netlist.")
        return """```spice
* RC Low-Pass Filter (Stub Response)
Vin in 0 AC 1.0
R1 in out 10000
C1 out 0 1e-8
.end
```"""


# ── Factory ────────────────────────────────────────────────────────

_PROVIDERS = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "ollama": OllamaProvider,
    "stub": StubProvider,
}


def get_provider(name: str = "ollama", **kwargs) -> LLMProvider:
    """Create an LLM provider by name.

    Args:
        name: Provider name. Options: "gemini", "openai", "anthropic", "ollama", "stub".
        **kwargs: Provider-specific options (e.g. model="gpt-4o", temperature=0.2).

    Returns:
        An LLMProvider instance ready for use.

    Examples:
        llm = get_provider("gemini")
        llm = get_provider("openai", model="gpt-4o")
        llm = get_provider("ollama", model="mistral")
        llm = get_provider("stub")  # No API key needed
    """
    name_lower = name.lower()
    if name_lower not in _PROVIDERS:
        available = list(_PROVIDERS)
        raise ValueError(f"Unknown LLM provider '{name}'. Available: {available}")
    return _PROVIDERS[name_lower](**kwargs)
