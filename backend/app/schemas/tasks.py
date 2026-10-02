"""Learning-task content, attempts, and task action contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.base import ApiModel, EntityModel, JsonObject, NonEmptyText, UnitScore, utc_now
from app.schemas.enums import (
    AttemptInputMode,
    ISpyInteractionMode,
    PartOfSpeech,
    TaskKind,
    TaskPhase,
    TaskStatus,
)


class VocabularyLearningWord(ApiModel):
    learning_key: str | None = None
    term_type: Literal["object", "attribute", "relationship"] = "object"
    vocabulary_item_id: UUID | None = None
    scene_object_id: UUID | None = None
    target_text: NonEmptyText
    translation: NonEmptyText
    part_of_speech: PartOfSpeech
    gender: str | None = None
    plural_form: str | None = None
    phonetic_text: str | None = None
    pronunciation_audio_asset_id: UUID | None = None
    example_sentence: str | None = None


class VocabularyChoice(ApiModel):
    option_id: NonEmptyText
    label: NonEmptyText


class VocabularyQuestion(ApiModel):
    question_id: NonEmptyText
    prompt: NonEmptyText
    options: Annotated[list[VocabularyChoice], Field(min_length=2)]
    # Vocabulary recognition is a low-stakes learning interaction, so clients
    # may evaluate its choices immediately without a network round trip.
    correct_option_id: NonEmptyText | None = None


class VocabularyIntroductionContent(ApiModel):
    kind: Literal["vocabularyIntroduction"] = "vocabularyIntroduction"
    title: NonEmptyText
    words: list[VocabularyLearningWord] = Field(default_factory=list)
    questions: list[VocabularyQuestion] = Field(default_factory=list)
    allow_typing_practice: bool = True
    # Kept temporarily so active sessions created before the grouped lesson remain readable.
    vocabulary_item_id: UUID | None = None
    target_text: str | None = None
    translation: str | None = None
    part_of_speech: PartOfSpeech | None = None
    gender: str | None = None
    example_sentence: str | None = None

    @model_validator(mode="after")
    def validate_words(self) -> VocabularyIntroductionContent:
        if self.words and self.questions:
            return self
        legacy_fields = (
            self.vocabulary_item_id,
            self.target_text,
            self.translation,
            self.part_of_speech,
        )
        if all(legacy_fields):
            return self
        raise ValueError("vocabulary introduction requires grouped words or legacy word fields")


class GrammarLessonQuestion(ApiModel):
    question_id: NonEmptyText
    prompt: NonEmptyText
    interaction_type: Literal["multipleChoice", "sentenceBuilding"] = "multipleChoice"
    options: list[VocabularyChoice] = Field(default_factory=list)
    token_bank: list[NonEmptyText] = Field(default_factory=list)
    translation: str | None = None

    @model_validator(mode="after")
    def validate_interaction(self) -> GrammarLessonQuestion:
        if self.interaction_type == "multipleChoice" and len(self.options) < 2:
            raise ValueError("multiple-choice questions require answer options")
        if self.interaction_type == "sentenceBuilding" and not self.token_bank:
            raise ValueError("sentence-building questions require a token bank")
        if self.interaction_type == "sentenceBuilding" and self.options:
            raise ValueError("sentence-building questions cannot have answer options")
        return self


class GrammarLessonContent(ApiModel):
    kind: Literal["grammarLesson"] = "grammarLesson"
    focus: NonEmptyText
    title: NonEmptyText
    explanation: NonEmptyText
    questions: Annotated[list[GrammarLessonQuestion], Field(min_length=1)]


class GrammarExplanationContent(ApiModel):
    kind: Literal["grammarExplanation"] = "grammarExplanation"
    title: NonEmptyText
    explanation: NonEmptyText
    examples: Annotated[list[NonEmptyText], Field(min_length=1)]
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)


class GrammarPracticeContent(ApiModel):
    kind: Literal["grammarPractice"] = "grammarPractice"
    prompt: NonEmptyText
    options: list[NonEmptyText] = Field(default_factory=list)
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)
    allow_text_answer: bool = True


class SyntaxExplanationContent(ApiModel):
    kind: Literal["syntaxExplanation"] = "syntaxExplanation"
    title: NonEmptyText
    sentence_pattern: NonEmptyText
    explanation: NonEmptyText
    examples: Annotated[list[NonEmptyText], Field(min_length=1)]
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)


class SentenceBuildingContent(ApiModel):
    kind: Literal["sentenceBuilding"] = "sentenceBuilding"
    prompt: NonEmptyText
    source_text: str | None = None
    token_bank: list[NonEmptyText] = Field(default_factory=list)
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)
    allow_speech: bool = True
    allow_text: bool = True


class ISpyChoice(ApiModel):
    option_id: NonEmptyText
    label: NonEmptyText
    scene_object_id: UUID | None = None


class ISpyRoundContent(ApiModel):
    kind: Literal["ispyRound"] = "ispyRound"
    clue: NonEmptyText
    clue_translation: str | None = None
    interaction_mode: ISpyInteractionMode
    options: list[ISpyChoice] = Field(default_factory=list)
    encouragement: str | None = None
    hint_available: bool = True


class ReflectionContent(ApiModel):
    kind: Literal["reflection"] = "reflection"
    prompt: NonEmptyText
    suggested_vocabulary_ids: list[UUID] = Field(default_factory=list)
    allow_speech: bool = True
    allow_text: bool = True


type TaskPublicContent = Annotated[
    VocabularyIntroductionContent
    | GrammarLessonContent
    | GrammarExplanationContent
    | GrammarPracticeContent
    | SyntaxExplanationContent
    | SentenceBuildingContent
    | ISpyRoundContent
    | ReflectionContent,
    Field(discriminator="kind"),
]


class TaskAnswerKey(ApiModel):
    """Private evaluation data; never expose this schema in public responses."""

    accepted_text_answers: list[NonEmptyText] = Field(default_factory=list)
    correct_scene_object_id: UUID | None = None
    correct_option_id: str | None = None
    expected_token_order: list[NonEmptyText] = Field(default_factory=list)
    reference_text: str | None = None
    evaluation_notes: str | None = None
    correct_option_ids: dict[str, str] = Field(default_factory=dict)
    accepted_text_answers_by_vocabulary_id: dict[str, list[str]] = Field(default_factory=dict)
    scene_description_context: JsonObject | None = None


class SessionTask(EntityModel):
    """Internal task entity, including its private answer key."""

    session_id: UUID
    phase: TaskPhase
    kind: TaskKind
    order_index: Annotated[int, Field(ge=0)]
    status: TaskStatus = TaskStatus.PENDING
    is_skippable: Literal[True] = True
    public_content: TaskPublicContent
    answer_key: TaskAnswerKey | None = Field(default=None, repr=False)
    vocabulary_item_id: UUID | None = None
    scene_object_id: UUID | None = None
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    skipped_at: AwareDatetime | None = None
    skip_reason: Annotated[str, Field(max_length=500)] | None = None

    @model_validator(mode="after")
    def validate_task(self) -> SessionTask:
        if self.public_content.kind != self.kind.value:
            raise ValueError("publicContent.kind must match task kind")
        if self.kind is TaskKind.ISPY_ROUND and self.phase is not TaskPhase.ISPY:
            raise ValueError("ispyRound tasks must belong to the ispy phase")
        if (
            self.kind not in {TaskKind.ISPY_ROUND, TaskKind.REFLECTION}
            and self.phase is TaskPhase.ISPY
        ):
            raise ValueError("only ispyRound tasks may belong to the ispy phase")
        if self.status is TaskStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed tasks require completedAt")
        if self.status is TaskStatus.SKIPPED and self.skipped_at is None:
            raise ValueError("skipped tasks require skippedAt")
        if self.completed_at is not None and self.skipped_at is not None:
            raise ValueError("a task cannot be both completed and skipped")
        return self


class SessionTaskPublic(ApiModel):
    """Client-safe task response with no answer-key field."""

    id: UUID
    session_id: UUID
    phase: TaskPhase
    kind: TaskKind
    order_index: Annotated[int, Field(ge=0)]
    status: TaskStatus
    is_skippable: Literal[True] = True
    public_content: TaskPublicContent
    vocabulary_item_id: UUID | None = None
    scene_object_id: UUID | None = None
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    skipped_at: AwareDatetime | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def from_internal(cls, task: SessionTask) -> SessionTaskPublic:
        return cls.model_validate(task, from_attributes=True)


class TaskAttempt(EntityModel):
    session_task_id: UUID
    attempt_number: Annotated[int, Field(ge=1)]
    input_mode: AttemptInputMode
    response_payload: JsonObject
    audio_media_asset_id: UUID | None = None
    is_correct: bool | None = None
    score: UnitScore | None = None
    feedback: JsonObject | None = None
    evaluation_details: JsonObject | None = None

    @model_validator(mode="after")
    def validate_audio_input(self) -> TaskAttempt:
        if (self.input_mode is AttemptInputMode.SPEECH) != (self.audio_media_asset_id is not None):
            raise ValueError("speech attempts require audioMediaAssetId; other modes cannot use it")
        return self


class TaskHint(EntityModel):
    session_task_id: UUID
    hint_level: Annotated[int, Field(ge=1)]
    content: JsonObject
    requested_at: AwareDatetime = Field(default_factory=utc_now)


class SubmitTextAttemptRequest(ApiModel):
    input_mode: Literal["text"] = "text"
    text: Annotated[str, Field(min_length=1, max_length=2_000)]
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None


class SubmitSpeechAttemptRequest(ApiModel):
    input_mode: Literal["speech"] = "speech"
    audio_media_asset_id: UUID
    transcript: Annotated[str, Field(max_length=2_000)] | None = None
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None


class SubmitObjectSelectionAttemptRequest(ApiModel):
    input_mode: Literal["objectSelection"] = "objectSelection"
    scene_object_id: UUID
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None


class SubmitMultipleChoiceAttemptRequest(ApiModel):
    input_mode: Literal["multipleChoice"] = "multipleChoice"
    option_id: NonEmptyText
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None


class SubmitVocabularyReviewAttemptRequest(ApiModel):
    input_mode: Literal["vocabularyReview"] = "vocabularyReview"
    answers: dict[str, NonEmptyText]
    typed_answers: dict[str, str] = Field(default_factory=dict)
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None

    @model_validator(mode="after")
    def validate_answers(self) -> SubmitVocabularyReviewAttemptRequest:
        if not self.answers:
            raise ValueError("answers cannot be empty")
        return self


class CheckVocabularyAnswerRequest(ApiModel):
    question_id: NonEmptyText
    option_id: NonEmptyText


class CheckVocabularyAnswerResponse(ApiModel):
    question_id: NonEmptyText
    is_correct: bool
    correct_option_id: NonEmptyText


type SubmitTaskAttemptRequest = Annotated[
    SubmitTextAttemptRequest
    | SubmitSpeechAttemptRequest
    | SubmitObjectSelectionAttemptRequest
    | SubmitMultipleChoiceAttemptRequest
    | SubmitVocabularyReviewAttemptRequest,
    Field(discriminator="input_mode"),
]


class SkipTaskRequest(ApiModel):
    reason: Annotated[str, Field(max_length=500)] | None = None


class SessionProgress(ApiModel):
    terminal_task_count: Annotated[int, Field(ge=0)]
    completed_task_count: Annotated[int, Field(ge=0)]
    skipped_task_count: Annotated[int, Field(ge=0)]
    total_task_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_counts(self) -> SessionProgress:
        if self.terminal_task_count != (self.completed_task_count + self.skipped_task_count):
            raise ValueError("terminal count must equal completed plus skipped")
        if self.terminal_task_count > self.total_task_count:
            raise ValueError("terminal count cannot exceed total count")
        return self


class TaskActionResponse(ApiModel):
    task: SessionTaskPublic
    attempt: TaskAttempt | None = None
    next_task_id: UUID | None = None
    session_progress: SessionProgress
