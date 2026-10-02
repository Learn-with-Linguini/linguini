"""OpenRouter access for the text and vision seams.

OpenRouter serves many vendors (Anthropic, Qwen, DeepSeek, Meta, Mistral, and
OpenAI's and Google's own models) behind an OpenAI-compatible Responses API,
including strict JSON-schema structured output and the same ``usage`` shape.
The OpenAI adapters therefore need nothing but a different base URL and key,
and models are named ``vendor/model`` (for example
``anthropic/claude-haiku-4.5``).

Calls are billed to the OpenRouter account and routed to whichever host
OpenRouter picks, so latency includes its routing hop.
"""

from __future__ import annotations

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
