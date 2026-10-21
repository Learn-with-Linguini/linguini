"""Structured contracts for generated grammar learning tasks.

Owns the static result models plus the dynamic response-model factory that
restricts generated references to the supplied scene keys at schema level.
Array bounds are sent to the provider and checked again when parsing locally.
String length bounds remain enforced by local validation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, create_model, model_validator

from app.schemas.base import ApiModel, NonEmptyText

type LearningTaskFocus = Literal[
    "genderNumberAgreement",
    "pluralNounForm",
    "sceneDescription",
    "chainedDescription",
]

REQUIRED_TASK_FOCUS_ORDER: tuple[str, ...] = (
    "genderNumberAgreement",
    "pluralNounForm",
    "sceneDescription",
    "chainedDescription",
)

KEY_FIELDS = {
    "objects": "object_keys",
    "attributes": "attribute_keys",
    "relationships": "relationship_keys",
}

_OptionId = Annotated[NonEmptyText, Field(max_length=64)]
_Token = Annotated[NonEmptyText, Field(max_length=40)]


class GeneratedChoice(ApiModel):
    option_id: _OptionId
    label: NonEmptyText = Field(max_length=200)


class GeneratedQuestion(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    prompt: NonEmptyText = Field(max_length=300)
    interaction_type: Literal["multipleChoice", "sentenceBuilding"] = "multipleChoice"
    options: list[GeneratedChoice] = Field(default_factory=list)
    correct_option_id: _OptionId | None = None
    correct_text: Annotated[str, Field(max_length=300)] | None = None
    token_bank: Annotated[list[_Token], Field(max_length=40)] = Field(
        default_factory=list
    )
    translation: Annotated[str, Field(max_length=300)] | None = None
    object_keys: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    attribute_keys: Annotated[list[str], Field(max_length=20)] = Field(
        default_factory=list
    )
    relationship_keys: Annotated[list[str], Field(max_length=20)] = Field(
        default_factory=list
    )

    @model_validator(mode="before")
    @classmethod
    def discard_builder_fields_from_multiple_choice(cls, value: Any) -> Any:
        """Tolerate harmless answer text a model may echo beside a valid MCQ.

        Only chained descriptions are sentence builders. A correct option remains
        the server-side answer key for every other task, so retaining an echoed
        `correctText` or `tokenBank` adds no value and makes the response invalid.
        """
        if not isinstance(value, dict):
            return value
        interaction = value.get(
            "interactionType", value.get("interaction_type", "multipleChoice")
        )
        if interaction != "multipleChoice":
            return value
        normalized = {
            key: item
            for key, item in value.items()
            if key not in {"correctText", "correct_text", "tokenBank", "token_bank"}
        }
        # Explicit values keep these optional fields available during assignment
        # validation, even when the provider omitted them from its JSON.
        normalized["correct_text"] = None
        normalized["token_bank"] = []
        return normalized

    @model_validator(mode="after")
    def validate_interaction(self) -> GeneratedQuestion:
        if self.interaction_type == "multipleChoice":
            if len(self.options) != 4:
                raise ValueError("multiple-choice questions require exactly four options")
            option_ids = {option.option_id for option in self.options}
            if self.correct_option_id not in option_ids:
                raise ValueError("correctOptionId must identify an offered option")
            if getattr(self, "correct_text", None) is not None or getattr(self, "token_bank", []):
                raise ValueError("multiple-choice questions cannot include sentence-building data")
        elif not self.correct_text or not self.token_bank:
            raise ValueError("sentence-building questions require correctText and tokenBank")
        elif self.options or self.correct_option_id is not None:
            raise ValueError("sentence-building questions cannot include answer options")
        return self


class GeneratedMultipleChoiceQuestion(GeneratedQuestion):
    interaction_type: Literal["multipleChoice"] = "multipleChoice"
    options: list[GeneratedChoice] = Field(min_length=4, max_length=4)
    correct_option_id: _OptionId


class GeneratedDescriptionQuestion(GeneratedMultipleChoiceQuestion):
    translation: NonEmptyText = Field(
        max_length=300,
        description="English translation of the complete correct sentence. Never null or empty.",
    )


class GeneratedSentenceBuilderQuestion(GeneratedQuestion):
    interaction_type: Literal["sentenceBuilding"] = "sentenceBuilding"
    options: list[GeneratedChoice] = Field(default_factory=list, max_length=0)
    correct_option_id: None = None
    correct_text: NonEmptyText = Field(max_length=300)
    token_bank: Annotated[list[_Token], Field(min_length=1, max_length=40)]
    translation: NonEmptyText = Field(
        max_length=300,
        description="Complete English sentence the learner must translate using the word bank.",
    )


class GeneratedLearningTaskContent(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    explanation: NonEmptyText = Field(max_length=400)
    questions: Annotated[list[GeneratedQuestion], Field(min_length=2, max_length=4)]


class GeneratedLearningTask(GeneratedLearningTaskContent):
    focus: LearningTaskFocus


class LearningTaskResult(ApiModel):
    tasks: Annotated[
        list[GeneratedLearningTask],
        Field(min_length=1, max_length=len(REQUIRED_TASK_FOCUS_ORDER)),
    ]


def required_task_focuses(payload: dict[str, Any]) -> tuple[str, ...]:
    """Return the one valid task sequence for the scene's relation count."""
    relationship_count = len(payload.get("relationships", []))
    return (
        REQUIRED_TASK_FOCUS_ORDER
        if relationship_count >= 1
        else REQUIRED_TASK_FOCUS_ORDER[:2] + REQUIRED_TASK_FOCUS_ORDER[3:]
    )


@lru_cache(maxsize=32)
def generation_response_model(
    focuses: tuple[str, ...],
    object_keys: tuple[str, ...],
    attribute_keys: tuple[str, ...],
    relationship_keys: tuple[str, ...],
) -> type[ApiModel]:
    """Express runtime requirements in the provider schema before generation."""
    fields = {}
    for focus in focuses:
        base = (
            GeneratedSentenceBuilderQuestion if focus == "chainedDescription"
            else GeneratedDescriptionQuestion if focus == "sceneDescription"
            else GeneratedMultipleChoiceQuestion
        )
        references = {}
        for name, keys in (
            ("object_keys", object_keys),
            ("attribute_keys", attribute_keys),
            ("relationship_keys", relationship_keys),
        ):
            minimum = int(name == "object_keys" or (
                name == "relationship_keys" and bool(keys)
                and focus in {"sceneDescription", "chainedDescription"}
            ))
            references[name] = (
                list[Literal.__getitem__(keys)] if keys else list[str],
                Field(
                    min_length=minimum,
                    description=(
                        "Include at least one supplied object key used in the correct answer; "
                        "never return an empty array. Copy object keys from the input, "
                        "including objects linked by selected attributes and relationships."
                        if name == "object_keys" else
                        "Keys of supplied vocabulary used in the correct answer."
                    ),
                ) if keys else Field(max_length=0),
            )
        question = create_model(f"{focus}Question", __base__=base, **references)
        task = create_model(
            f"{focus}Task", __base__=GeneratedLearningTaskContent,
            questions=(list[question], Field(min_length=2, max_length=4)),
        )
        fields[focus] = (task, ...)
    return create_model(
        f"RequiredLearningTasks{len(focuses)}",
        __base__=ApiModel,
        **fields,
    )


def scene_generation_response_model(payload: dict[str, Any]) -> type[ApiModel]:
    # Local import: schemas must not pull validation (which needs this module).
    from app.ai.features.learning_tasks.validation import (
        LearningTaskGenerationError,
    )

    if not payload.get("objects"):
        raise LearningTaskGenerationError("Learning tasks need at least one scene object.")
    return generation_response_model(
        required_task_focuses(payload),
        *(tuple(dict.fromkeys(row["key"] for row in payload.get(field, [])))
          for field in KEY_FIELDS),
    )


def unpack_generated_tasks(payload: dict[str, Any], response: ApiModel) -> LearningTaskResult:
    # The enclosing field owns the focus and order, not model-written metadata.
    return LearningTaskResult(tasks=[
        GeneratedLearningTask.model_validate({
            **getattr(response, focus).model_dump(), "focus": focus,
        })
        for focus in required_task_focuses(payload)
    ])
