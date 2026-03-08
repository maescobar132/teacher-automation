"""
Unified LLM client supporting multiple providers.

Supports:
- Anthropic Claude (with prompt caching)
- DeepSeek (OpenAI-compatible API)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Unified client for multiple LLM providers."""

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        temperature: float = 0.3,
    ):
        """
        Initialize LLM client.

        Args:
            provider: "anthropic" or "deepseek"
            model: Model name (provider-specific)
            temperature: Temperature for generation
        """
        self.provider = provider.lower()
        self.temperature = temperature

        if self.provider == "anthropic":
            from anthropic import Anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")

            self.client = Anthropic(api_key=api_key)
            self.model = model or "claude-sonnet-4-6"

        elif self.provider == "deepseek":
            from openai import OpenAI

            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY not set")

            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            # Use deepseek-chat as default (reasoner is slow and not ideal for JSON)
            self.model = model or "deepseek-chat"

        else:
            raise ValueError(f"Unknown provider: {provider}")

        logger.info(f"Initialized {self.provider} client with model {self.model}")

    def generate_feedback(
        self,
        system_prompt: str,
        user_message: str,
        rubric: dict[str, Any] | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """
        Generate feedback using the configured LLM.

        Args:
            system_prompt: System instructions
            user_message: User message with student data
            rubric: Optional rubric (for caching with Anthropic)
            max_tokens: Maximum tokens to generate

        Returns:
            Raw LLM response text
        """
        if self.provider == "anthropic":
            return self._generate_anthropic(
                system_prompt, user_message, rubric, max_tokens
            )
        elif self.provider == "deepseek":
            return self._generate_deepseek(
                system_prompt, user_message, max_tokens
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _generate_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        rubric: dict[str, Any] | None,
        max_tokens: int,
    ) -> str:
        """Generate with Anthropic Claude (with prompt caching)."""
        # Build system blocks with caching
        system_blocks = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

        if rubric:
            system_blocks.append({
                "type": "text",
                "text": json.dumps(rubric, ensure_ascii=False),
                "cache_control": {"type": "ephemeral"}
            })

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            system=system_blocks,
            messages=[
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        return response.content[0].text

    def _generate_deepseek(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Generate with DeepSeek (OpenAI-compatible API)."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            max_tokens=max_tokens,
            temperature=self.temperature,
            stream=False
        )

        message = response.choices[0].message

        # For reasoning models, the content might be in reasoning_content
        # Try reasoning_content first (for deepseek-reasoner)
        if hasattr(message, 'reasoning_content') and message.reasoning_content:
            logger.debug("Using reasoning_content from deepseek-reasoner")
            # Reasoning models put the final answer after thinking
            # Return the regular content which should have the JSON
            return message.content if message.content else message.reasoning_content

        return message.content


def extract_json_from_response(text: str) -> dict[str, Any]:
    """
    Extract JSON from LLM response.

    Handles responses with markdown code blocks or raw JSON.
    """
    if not text or not text.strip():
        logger.error("Empty response text")
        raise ValueError("Empty response from LLM")

    # Try to find JSON in code blocks first
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        json_str = code_block_match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from code block: {e}")

    # Try to find raw JSON (greedy match to get full object)
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse raw JSON: {e}")

    # Log first 500 chars of response for debugging
    logger.error(f"No valid JSON found. Response preview: {text[:500]}...")
    raise ValueError("No JSON found in response")
