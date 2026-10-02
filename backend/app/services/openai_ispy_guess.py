"""OpenAI-backed evaluation of a learner's text-only I-Spy description."""

import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.schemas.ispy_guess import ISpyGuessResult
from app.services.ispy_guess import (
    DEFAULT_PROMPT_PATH,
    ISpyGuessError,
    scene_guess_response_model,
    validate_ispy_guess,
)

logger = logging.getLogger(__name__)


class OpenAIISpyGuessGenerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
        prompt_path: Path = DEFAULT_PROMPT_PATH,
        timeout_seconds: int = 60,
        base_url: str | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("OpenAI I-Spy guessing requires an API key and model.")
        self.model = model.strip()
        self.prompt = prompt_path.read_text(encoding="utf-8").strip()
        # A different base URL points the same Responses call at an
        # OpenAI-compatible host such as OpenRouter.
        self.client = client or OpenAI(
            api_key=api_key.strip(),
            timeout=timeout_seconds,
            max_retries=2,
            **({"base_url": base_url} if base_url else {}),
        )

    def guess(self, context: dict[str, Any], learner_text: str) -> ISpyGuessResult:
        payload = {**context, "learnerText": learner_text}
        response_model = scene_guess_response_model(payload)
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=self.prompt,
                input=json.dumps(payload, ensure_ascii=False),
                text_format=response_model,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ISpyGuessError("OpenAI returned no I-Spy guess.")
            result = ISpyGuessResult.model_validate(parsed.model_dump())
            validate_ispy_guess(payload, result)
            return result
        except ISpyGuessError:
            logger.exception("OpenAI returned an unusable I-Spy guess")
            raise
        except Exception as exc:
            logger.exception("OpenAI I-Spy guessing failed (%s)", type(exc).__name__)
            raise ISpyGuessError("I-Spy guessing failed.") from exc
