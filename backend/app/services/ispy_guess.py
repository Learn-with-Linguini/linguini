"""Provider-neutral scene-description guessing contract."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, create_model

from app.schemas.base import ApiModel
from app.schemas.ispy_guess import ISpyGuessResult
from app.services.scene_analysis import SceneAnalysisError

DEFAULT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "i_spy_guess.txt"


class ISpyGuessError(SceneAnalysisError):
    """The learner description could not be evaluated safely."""


class ISpyGuessGenerator(Protocol):
    def guess(self, context: dict[str, Any], learner_text: str) -> ISpyGuessResult: ...


@lru_cache(maxsize=32)
def _response_model(object_keys: tuple[str, ...], evidence_keys: tuple[str, ...]) -> type[ApiModel]:
    key_type = Literal.__getitem__(object_keys)
    evidence_type = Literal.__getitem__(evidence_keys) if evidence_keys else str
    return create_model(
        "GroundedISpyGuessResult",
        __base__=ISpyGuessResult,
        guessed_object_key=(key_type | None, ...),
        alternative_object_keys=(list[key_type], Field()),
        matched_evidence_keys=(
            list[evidence_type], Field() if evidence_keys else Field(max_length=0)
        ),
        contradicted_evidence_keys=(
            list[evidence_type], Field() if evidence_keys else Field(max_length=0)
        ),
    )


def scene_guess_response_model(payload: dict[str, Any]) -> type[ApiModel]:
    scene = payload.get("sceneObjects", {})
    object_keys = tuple(dict.fromkeys(row["key"] for row in scene.get("objects", [])))
    if not object_keys:
        raise ISpyGuessError("I-Spy guessing needs at least one scene object.")
    evidence_keys = tuple(
        dict.fromkeys(
            row["key"]
            for field in ("attributes", "relations")
            for row in scene.get(field, [])
        )
    )
    return _response_model(object_keys, evidence_keys)


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
