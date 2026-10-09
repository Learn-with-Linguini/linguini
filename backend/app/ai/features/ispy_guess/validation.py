"""Provider-neutral, deterministic guards for I-Spy description evaluation.

No SDK imports: the same rules run regardless of which adapter produced the
response. ``ISpyGuessError`` stays a ``SceneAnalysisError`` so the workflow's
ungraded fallback is unchanged.

``build_guess_payload`` is the target-blindness boundary: only an allowlist of
scene facts plus the learner text reaches the model, so a selected target or
any other answer data in the stored context can never be sent.
"""

from __future__ import annotations

from typing import Any

from app.ai.features.ispy_guess.schemas import ISpyGuessResult
from app.services.scene_analysis import SceneAnalysisError

MAX_LEARNER_TEXT_LENGTH = 2_000

_SCENE_FIELDS = ("objects", "attributes", "relations")


class ISpyGuessError(SceneAnalysisError):
    """The learner description could not be evaluated safely."""


def build_guess_payload(context: dict[str, Any], learner_text: str) -> dict[str, Any]:
    if not learner_text.strip():
        raise ISpyGuessError("I-Spy guessing needs a learner description.")
    if len(learner_text) > MAX_LEARNER_TEXT_LENGTH:
        raise ISpyGuessError("I-Spy description is too long to evaluate.")
    scene = context.get("sceneObjects") or {}
    return {
        "targetLanguage": context.get("targetLanguage"),
        "sceneObjects": {field: list(scene.get(field) or []) for field in _SCENE_FIELDS},
        "learnerText": learner_text,
    }


def validate_ispy_guess(payload: dict[str, Any], result: ISpyGuessResult) -> None:
    scene = payload["sceneObjects"]
    object_keys = {row["key"] for row in scene["objects"]}
    evidence_keys = {
        row["key"] for field in ("attributes", "relations") for row in scene[field]
    }
    alternatives = set(result.alternative_object_keys)
    if result.guessed_object_key is None:
        if alternatives:
            raise ISpyGuessError("An unknown object cannot have alternatives.")
    elif result.guessed_object_key not in object_keys:
        raise ISpyGuessError("I-Spy guess is not in the supplied scene.")
    if not alternatives <= object_keys or result.guessed_object_key in alternatives:
        raise ISpyGuessError("I-Spy alternatives must be other supplied objects.")
    if len(alternatives) != len(result.alternative_object_keys):
        raise ISpyGuessError("I-Spy alternatives must be unique.")
    matched = set(result.matched_evidence_keys)
    contradicted = set(result.contradicted_evidence_keys)
    if not (matched | contradicted) <= evidence_keys:
        raise ISpyGuessError("I-Spy feedback referenced evidence outside the scene.")
    if matched & contradicted:
        raise ISpyGuessError("Scene evidence cannot be both matched and contradicted.")
