"""Deterministic M06 A2 request-lesson result and validation."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel, NonEmptyText
from app.schemas.tasks import VocabularyChoice
from app.services.mission_m06_lexicon import ITEMS


class M06Question(ApiModel):
    question_id: NonEmptyText
    purpose: Literal[
        "listenOrderCard",
        "politeChunkGap",
        "buildRequest",
        "identifyMissingDetail",
        "replyWithDetail",
        "confirmOrRepair",
    ]
    prompt: NonEmptyText
    interaction_type: Literal["multipleChoice", "sentenceBuilding", "textCloze"]
    options: list[VocabularyChoice] = Field(default_factory=list)
    correct_option_id: str | None = None
    correct_text: str | None = None
    accepted_answers: list[str] = Field(default_factory=list)
    token_bank: list[NonEmptyText] = Field(default_factory=list)
    translation: str | None = None
    audio_text: str | None = None
    listen_first: bool | None = None
    slot_template: str | None = None
    complete_chunk: str | None = None
    gap_kind: NonEmptyText
    assistance_steps: list[
        Literal["replayAudio", "visualDetail", "phraseOnset", "chunkBank", "fullModel"]
    ]
    dialogue: list[dict[str, str]] | None = None
    allow_retry: bool = True
    target_id: NonEmptyText
    evidence_type: Literal["recognition", "construction"]
    distractor_fields: dict[str, str] = Field(default_factory=dict)
    option_fields: dict[str, dict[str, str]] = Field(default_factory=dict)
    correct_chunks: list[str] = Field(default_factory=list)
    repair_chunks: list[str] = Field(default_factory=list)
    wrong_value_chunk: str | None = None

    @model_validator(mode="after")
    def validate_interaction(self):
        if self.interaction_type == "multipleChoice":
            if len(self.options) != 3 or self.correct_option_id not in {
                option.option_id for option in self.options
            }:
                raise ValueError("M06 multiple-choice questions need three choices and one answer.")
        elif self.interaction_type == "sentenceBuilding":
            if not self.token_bank or not self.correct_text or self.options:
                raise ValueError("M06 sentence builders need an answer and chunk bank.")
        elif self.options or self.token_bank or not self.correct_text:
            raise ValueError("M06 text cloze needs a text answer without choices or chunks.")
        return self


class MissionM06Result(ApiModel):
    questions: Annotated[list[M06Question], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def validate_purposes(self):
        expected = [
            "listenOrderCard",
            "politeChunkGap",
            "buildRequest",
            "identifyMissingDetail",
            "replyWithDetail",
            "confirmOrRepair",
        ]
        if [question.purpose for question in self.questions] != expected:
            raise ValueError("M06 questions must follow the six approved purposes.")
        return self


def validate_m06_lesson(payload, result):
    """Reject a lesson that leaves the approved transaction or language tables."""
    try:
        result = MissionM06Result.model_validate(result)
    except Exception as exc:
        raise LearningTaskGenerationError("M06 lesson does not match its result schema.") from exc
    transaction = payload["transaction"]
    fields = set(transaction["requestDetails"]) | {"quantity", "item"}
    if transaction["followUp"]["type"] in fields:
        raise LearningTaskGenerationError("The M06 follow-up must ask for a missing detail.")
    mismatch = transaction["mismatch"]
    allowed_mismatches = {"quantity", transaction["followUp"]["type"]}
    if transaction["scenario"] == "cafe" and transaction["requestDetails"].get("size"):
        allowed_mismatches.add("size")
    mismatch_field = mismatch.get("field")
    if mismatch.get("fields") or (
        mismatch["flag"]
        and (
            not isinstance(mismatch_field, str)
            or mismatch_field not in allowed_mismatches
            or mismatch.get("servedValue") == mismatch.get("correctedValue")
        )
    ):
        raise LearningTaskGenerationError("M06 may contain only one mismatch.")
    if mismatch["flag"]:
        corrected = (
            transaction["quantity"]
            if mismatch_field == "quantity"
            else transaction["requestDetails"].get(mismatch_field)
            or transaction["followUp"]["value"]
        )
        if mismatch.get("correctedValue") != corrected:
            raise LearningTaskGenerationError("M06 mismatch must be repaired to the real order.")
    gap_kinds = {question.gap_kind for question in result.questions}
    if len(gap_kinds) < 3:
        raise LearningTaskGenerationError("M06 needs at least three distinct gap kinds.")
    first = result.questions[0]
    if len(first.options) != 3 or any(
        len(first.option_fields.get(option.option_id, {})) != 1
        for option in first.options
        if option.option_id != first.correct_option_id
    ):
        raise LearningTaskGenerationError("M06 order-card distractors must change one field.")
    if any(
        value == {
            "item": transaction["itemKey"],
            "quantity": str(transaction["quantity"]),
            **transaction["requestDetails"],
        }.get(field)
        for option in first.options
        if option.option_id != first.correct_option_id
        for field, value in first.option_fields[option.option_id].items()
    ):
        raise LearningTaskGenerationError("M06 order-card distractors must change one field.")
    q6 = result.questions[-1]
    if q6.slot_template is not None or q6.complete_chunk is not None:
        raise LearningTaskGenerationError("M06 Q6 must not reveal the response in a slot template.")
    if result.questions[-1].correct_text != payload.get("expectedQ6Answer"):
        raise LearningTaskGenerationError("M06 confirmation must match its transaction.")
    if payload["q5Mode"] != "openCloze" and result.questions[4].interaction_type == "textCloze":
        raise LearningTaskGenerationError("M06 open cloze requires independent Q5 history.")
    if payload["q5Mode"] == "openCloze" and result.questions[4].interaction_type != "textCloze":
        raise LearningTaskGenerationError("M06 Q5 must follow the permitted history mode.")
    # Pack lessons (packLesson) derive tiles from generated sentences; the Korean rules
    # below describe this module's own reviewed chunks.
    reviewed_chunks = not payload.get("packLesson")
    for question in result.questions:
        if question.interaction_type == "sentenceBuilding":
            for chunk in question.correct_chunks:
                if not chunk:
                    raise LearningTaskGenerationError("M06 sentence chunks cannot be empty.")
            if payload["targetLanguage"] == "ko" and reviewed_chunks:
                # Korean request units stay intact; the number and counter are a single chunk.
                if (
                    question.purpose in {"buildRequest", "confirmOrRepair"}
                    and not any(
                        counter in chunk
                        for chunk in question.correct_chunks
                        for counter in ("잔", "개", "권", "자루")
                    )
                    and question.purpose == "buildRequest"
                ):
                    raise LearningTaskGenerationError("Korean request chunks need a counter.")
    if payload["targetLanguage"] == "ko" and reviewed_chunks:
        request = result.questions[2]
        item = ITEMS[payload["itemKey"]]
        noun, counter = item.nouns["ko"]
        size = transaction["requestDetails"].get("size")
        request_noun = f"{'작은 ' if size == 'small' else '큰 ' if size == 'large' else ''}{noun}"
        number = {1: "한", 2: "두", 3: "세"}[transaction["quantity"]]
        quantity_chunk = f"{number} {counter}"
        if (
            request_noun not in request.correct_chunks
            or quantity_chunk not in request.correct_chunks
        ):
            raise LearningTaskGenerationError(
                "Korean request chunks must separate the item from its number and counter."
            )
        if any(
            request_noun in chunk and quantity_chunk in chunk
            for chunk in request.correct_chunks
        ):
            raise LearningTaskGenerationError(
                "Korean request chunks must separate the item from its number and counter."
            )
    return result




