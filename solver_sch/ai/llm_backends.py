"""
llm_backends.py — LLMClient: unified async interface for Ollama and Gemini backends.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("solver_sch.ai.llm_backends")


class LLMClient:
    """Unified async LLM client supporting Ollama and Gemini backends.

    Returns Ollama-compatible response dicts for both backends so the
    agent loop doesn't need to care which backend is active.
    """

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite-preview",
        ollama_url: str = "http://localhost:11434/api/chat",
        temperature: float = 0.2,
        backend: str = "gemini",
        gemini_client: Any = None,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.temperature = temperature
        self.backend = backend.lower()
        self._gemini_client = gemini_client

    async def call_async(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Dispatch to the configured backend. Returns Ollama-compatible dict."""
        if self.backend == "gemini":
            return await self._call_gemini_async(messages, tools)
        return await self._call_ollama_async(messages, tools)

    async def _call_ollama_async(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call Ollama Chat API."""
        options = {
            "temperature": self.temperature,
            "num_ctx": 4096,
            "num_thread": 6,
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if tools:
            payload["tools"] = tools

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(self.ollama_url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Ollama status {response.status}")
                data: Dict[str, Any] = await response.json()
                return data

    async def _call_gemini_async(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call Google Gemini API with tool support. Returns Ollama-compatible dict."""
        from google.genai import types

        # Convert messages to Gemini contents format
        gemini_contents: List[types.Content] = []
        system_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_text = content
            elif role == "user":
                gemini_contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=content)])
                )
            elif role == "assistant":
                gemini_contents.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=content)])
                )
            elif role == "tool":
                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=f"[Tool Result]: {content}")],
                    )
                )

        # Convert OpenAI-style tool schemas to Gemini FunctionDeclarations
        gemini_tools = None
        if tools:
            func_decls = []
            for t in tools:
                func_def = t.get("function", {})
                func_decls.append({
                    "name": func_def.get("name", ""),
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {}),
                })
            gemini_tools = [types.Tool(function_declarations=func_decls)]

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if system_text:
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=system_text,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
        if gemini_tools:
            config.tools = gemini_tools

        def _sync_call():
            return self._gemini_client.models.generate_content(
                model=self.model,
                contents=gemini_contents,
                config=config,
            )

        response = await asyncio.to_thread(_sync_call)

        # Normalize to Ollama-compatible format
        text_parts: List[str] = []
        tool_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                part_text: str = str(part.text) if part.text else ""
                if part_text:
                    text_parts.append(part_text)
                if part.function_call:
                    tool_calls.append({
                        "function": {
                            "name": part.function_call.name,
                            "arguments": dict(part.function_call.args) if part.function_call.args else {},
                        }
                    })

        content_text: str = "".join(text_parts).strip()
        result: Dict[str, Any] = {"message": {"role": "assistant", "content": content_text}}
        if tool_calls:
            result["message"]["tool_calls"] = tool_calls
        return result
