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

    response = llm.generate("Design an RC low-pass filter at 1kHz.")
"""

from __future__ import annotations

import os
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

logger = logging.getLogger("solver_sch.llm_providers")


class LLMProvider(ABC):
    """Abstract base class for LLM API providers.
    
    Implement `generate(prompt)` to add a new provider.
    """

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Send a prompt and return the text response.

        Args:
            prompt: User message / prompt to send.
            system_instruction: Optional system-level instruction (role definition).

        Returns:
            The LLM text response as a string.
        """


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
        while True:
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
                    logger.warning("Gemini rate limit hit (429). Retrying in 45s...")
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


class OllamaProvider(LLMProvider):
    """Local Ollama provider (no API key needed).

    Requires: Ollama running locally on http://localhost:11434
    Docs: https://ollama.ai
    """

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        import urllib.request
        import json
        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        payload = json.dumps({"model": self.model, "prompt": full_prompt, "stream": False}).encode()
        req = urllib.request.Request(f"{self.base_url}/api/generate", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["response"]


class StubProvider(LLMProvider):
    """Offline stub provider for testing / development without API keys.
    
    Returns a static valid SPICE netlist so the pipeline can be tested end-to-end.
    """

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


def get_provider(name: str = "gemini", **kwargs) -> LLMProvider:
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
