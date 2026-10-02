"""LLM-as-judge, used only where deterministic scoring runs out.

Both evals score against fixed reference data first. That covers most of what
matters and costs nothing to run, but it leaves a residue: a scene-analysis
label that is not in the case's accepted pool, or a translation that is not in
the lexicon. Neither is necessarily wrong. The label may be a real object the
labeller did not think to list; the translation may be a perfectly good synonym.

Treating that residue as failure would punish good models for our incomplete
reference data. Sending everything to a judge instead would make the whole
score slow, expensive and non-deterministic. So the judge is asked only about
the residue, and its verdicts are reported separately from the deterministic
numbers rather than blended into them.

Guardrails, which matter as much as the prompt:

- The judge is never told which model produced the output, so it cannot prefer
  a provider by name -- including its own.
- Temperature is zero and the rubric is anchored with worked examples, because
  an unanchored 1-5 scale drifts between runs.
- The reason is required *before* the score, so the verdict follows the
  reasoning rather than being justified after the fact.
- A judge from the same family as the model under test shares its blind spots.
  Prefer judging with a different provider, and say in the report which judge
  was used.

What this judge cannot do: confirm an object is actually in the photograph.
That needs a vision judge holding the image, and is deliberately not faked
here -- a text-only judge asked "is there a chair in this photo?" will simply
agree with whatever it is shown.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JudgeVerdict(BaseModel):
    """A single judgement. ``reason`` is first so the model writes it first."""

    reason: str = Field(description="One sentence of justification, written first.")
    score: int = Field(ge=1, le=5, description="1 unusable, 3 borderline, 5 ideal.")
    verdict: Literal["accept", "reject"]


class JudgeError(Exception):
    """The judge could not return a usable verdict."""


class JudgeClient(Protocol):
    def judge(self, system_prompt: str, payload: str) -> JudgeVerdict: ...


VOCABULARY_RUBRIC = """You grade candidate vocabulary words for a beginner language-learning app.

The app shows a learner a photograph of a real scene and teaches them words for
the physical objects in it. You are given one candidate word that a vision
model returned for a photograph. You cannot see the photograph, so do not guess
whether the object is present. Judge only whether the word is a good thing to
teach if it is present.

A good word is a concrete physical object, in singular form, that a beginner
would plausibly want and be able to use. Score:

5 - a concrete everyday object, exactly the kind of word to teach: "spoon",
    "traffic light", "shopping cart".
4 - concrete and teachable but slightly unusual or narrow: "radiator",
    "pinboard".
3 - borderline: a real thing, but too generic, too abstract, or a part rather
    than an object: "wall", "surface", "handle".
2 - not really an object: a material, a texture, an activity, or a scene
    description: "wood", "lighting", "shopping".
1 - unusable: a person or body part, a brand name, a plural, a phrase
    containing an adjective, or something that is not a noun at all.

Reject anything naming a person, a brand, or a sensitive characteristic,
whatever else is true of it.

Return the reason first, then the score, then accept or reject."""


TRANSLATION_RUBRIC = """You grade candidate translations for a beginner language-learning app.

You are given an English word, a target language, and a candidate translation
with its definite article and grammatical gender. Judge whether this is a good
thing to teach a beginner.

Score:

5 - the ordinary, most common word a beginner should learn, with the correct
    article and gender.
4 - correct and natural, but a less common synonym than the obvious choice.
3 - understandable but awkward, overly formal, or regionally narrow.
2 - wrong register, wrong sense of an ambiguous English word, or the article or
    gender is wrong.
1 - not a valid translation, or the article has been glued onto the noun
    instead of being returned in its own field.

The article and gender must agree with the word actually given, not with some
other translation of the same English word. Judge them against the candidate in
front of you.

Return the reason first, then the score, then accept or reject."""


@dataclass(frozen=True)
class JudgedItem:
    """One residual item, with the judge's verdict attached."""

    case_id: str
    subject: str
    verdict: JudgeVerdict


class ScriptedJudge:
    """A judge with fixed answers, for tests and for dry runs.

    Keyed on the subject string; anything unmapped is accepted at 3 so a test
    that forgets an entry fails loudly on the number rather than crashing.
    """

    def __init__(self, answers: dict[str, JudgeVerdict] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, str]] = []

    def judge(self, system_prompt: str, payload: str) -> JudgeVerdict:
        self.calls.append((system_prompt, payload))
        subject = json.loads(payload).get("candidate", "")
        return self.answers.get(
            subject,
            JudgeVerdict(reason="no scripted answer", score=3, verdict="accept"),
        )


class OpenAIJudge:
    """Judge backed by the OpenAI Responses API, mirroring the translator."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("The judge requires an API key and model.")
        self.model = model.strip()
        if client is not None:
            self.client = client
        else:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=api_key.strip(), timeout=timeout_seconds, max_retries=2
            )

    def judge(self, system_prompt: str, payload: str) -> JudgeVerdict:
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=system_prompt,
                input=payload,
                text_format=JudgeVerdict,
                temperature=0,
            )
            verdict = response.output_parsed
            if verdict is None:
                raise JudgeError("The judge returned no verdict.")
            return verdict
        except JudgeError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider failures are all alike here
            logger.exception("Judging failed (%s)", type(exc).__name__)
            raise JudgeError("Judging failed.") from exc


def judge_vocabulary(
    client: JudgeClient, case_id: str, labels: Sequence[str], scene_title: str | None = None
) -> list[JudgedItem]:
    """Grade scene-analysis labels the deterministic scorer could not confirm."""
    judged: list[JudgedItem] = []
    for label in labels:
        payload = json.dumps(
            {"candidate": label, "sceneTitle": scene_title}, ensure_ascii=False
        )
        judged.append(
            JudgedItem(
                case_id=case_id,
                subject=label,
                verdict=client.judge(VOCABULARY_RUBRIC, payload),
            )
        )
    return judged


def judge_translations(
    client: JudgeClient,
    case_id: str,
    language: str,
    candidates: Sequence[tuple[str, str, str | None, str | None]],
) -> list[JudgedItem]:
    """Grade translations absent from the lexicon.

    ``candidates`` is ``(source, translation, article, gender)``.
    """
    judged: list[JudgedItem] = []
    for source, translation, article, gender in candidates:
        payload = json.dumps(
            {
                "candidate": translation,
                "sourceWord": source,
                "targetLanguage": language,
                "article": article,
                "gender": gender,
            },
            ensure_ascii=False,
        )
        judged.append(
            JudgedItem(
                case_id=case_id,
                subject=f"{source} -> {translation}",
                verdict=client.judge(TRANSLATION_RUBRIC, payload),
            )
        )
    return judged


def summarize(judged: Sequence[JudgedItem]) -> dict[str, Any]:
    """Aggregate verdicts, reported beside the deterministic numbers."""
    if not judged:
        return {"judged": 0, "accepted": 0, "acceptRate": None, "meanScore": None}
    accepted = sum(1 for item in judged if item.verdict.verdict == "accept")
    return {
        "judged": len(judged),
        "accepted": accepted,
        "acceptRate": accepted / len(judged),
        "meanScore": sum(item.verdict.score for item in judged) / len(judged),
        "rejected": [
            {"subject": item.subject, "reason": item.verdict.reason}
            for item in judged
            if item.verdict.verdict == "reject"
        ],
    }
