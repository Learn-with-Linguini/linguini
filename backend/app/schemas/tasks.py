"""Learning-task content, attempts, and task action contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, ValidationError, model_validator

from app.repositories.postgres.xp import task_xp
from app.schemas.base import ApiModel, EntityModel, JsonObject, NonEmptyText, UnitScore, utc_now
from app.schemas.enums import (
    AttemptInputMode,
    ISpyInteractionMode,
    PartOfSpeech,
    ProficiencyLevel,
    SessionMode,
    TaskKind,
    TaskPhase,
    TaskStatus,
)
from app.schemas.language_context import LanguageDisplayContext
from app.schemas.mission_content import A0MissionSnapshot, TaughtChunk
from app.schemas.roleplay import RoleplayFact

type MissionId = Annotated[str, StringConstraints(pattern=r"^M\d{2}$")]
type ContentVersion = Annotated[int, Field(ge=1)]
type ContractId = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=60)
]
type EvidenceType = Literal[
    "recognition", "objectSelection", "construction", "production", "participation"
]
type SupportKind = Literal[
    "translation", "audio", "example", "wordBank", "clueFrame", "helpPhrase", "hint",
    "answerReveal",
]
type MistakeType = Literal[
    "wrongObject", "wrongWord", "wrongArticle", "wrongGender", "wrongColour", "wrongAttribute",
    "wrongPosition",
    "wordOrder", "missingWord", "spelling", "targetNamed", "wrongQuantity", "pluralForm",
]
type QuestionOutcomeStatus = Literal["correct", "incorrect", "unassessed"]

# Question ID used by evaluation metadata and results of tasks without grouped questions.
TASK_QUESTION_ID = "task"


def _is_none(value) -> bool:
    return value is None


def _is_empty(value) -> bool:
    return not value


def _unique(values, message):
    if len(values) != len(set(values)):
        raise ValueError(message)


class MissionTaskFields(ApiModel):
    """Optional link from task content to a versioned mission definition.

    Omitted from JSON when unset, so content without a mission keeps its saved shape.
    """

    mission_id: MissionId | None = Field(default=None, exclude_if=_is_none)
    practice_level: ProficiencyLevel | None = Field(default=None, exclude_if=_is_none)
    content_version: ContentVersion | None = Field(default=None, exclude_if=_is_none)
    language_context: LanguageDisplayContext | None = Field(default=None, exclude_if=_is_none)

    @model_validator(mode="after")
    def validate_mission(self) -> MissionTaskFields:
        values = (self.mission_id, self.practice_level, self.content_version)
        if None in values and any(value is not None for value in values):
            raise ValueError("missionId, practiceLevel and contentVersion must be set together")
        return self

    @property
    def mission_key(self) -> tuple[str, ProficiencyLevel, int] | None:
        if self.mission_id is None:
            return None
        return self.mission_id, self.practice_level, self.content_version


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
    romanization: str | None = Field(default=None, exclude_if=_is_none)
    pronunciation_audio_asset_id: UUID | None = None
    example_sentence: str | None = None


class VocabularyChoice(ApiModel):
    option_id: NonEmptyText
    label: NonEmptyText


class LessonDialogueTurn(ApiModel):
    speaker: Literal["server", "linguini", "learner"]
    text: NonEmptyText
    translation: str | None = Field(default=None, exclude_if=_is_none)


MissionDialogueTurn = LessonDialogueTurn


class MissionQuestionOutcome(ApiModel):
    text: NonEmptyText
    kind: Literal["returned", "basket", "leftBehind"]
    scene_object_id: UUID


class VocabularyQuestion(ApiModel):
    romanizations: dict[str, str] | None = Field(default=None, exclude_if=_is_none)
    question_id: NonEmptyText
    prompt: NonEmptyText
    options: Annotated[list[VocabularyChoice], Field(min_length=2)]
    # Vocabulary recognition is a low-stakes learning interaction, so clients
    # may evaluate its choices immediately without a network round trip.
    correct_option_id: NonEmptyText | None = None


class VocabularyIntroductionContent(MissionTaskFields):
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
    interaction_type: Literal["multipleChoice", "sentenceBuilding", "textCloze"] = "multipleChoice"
    options: list[VocabularyChoice] = Field(default_factory=list)
    token_bank: list[NonEmptyText] = Field(default_factory=list)
    translation: str | None = None
    # Display only. Native prompts, tiles and answer keys remain canonical.
    romanizations: dict[str, str] | None = Field(default=None, exclude_if=_is_none)
    sentence_join_modes: list[Literal["space", "none"]] | None = Field(
        default=None, exclude_if=_is_none,
    )
    # The photo object a question is about, shown with its English label.
    scene_object_id: UUID | None = Field(default=None, exclude_if=_is_none)
    object_label: str | None = Field(default=None, exclude_if=_is_none)
    prompt_translation: str | None = Field(default=None, exclude_if=_is_none)
    # A second photo object the question relates the first to.
    reference_object_id: UUID | None = Field(default=None, exclude_if=_is_none)
    reference_label: str | None = Field(default=None, exclude_if=_is_none)
    # An optional section heading grouping this question with its neighbours.
    section: str | None = Field(default=None, exclude_if=_is_none)
    # Every scene object of a counted group, highlighted together in the photo.
    group_object_ids: list[UUID] | None = Field(default=None, exclude_if=_is_none)
    # A practice board: option id -> how many objects that board shows.
    board_counts: dict[str, int] | None = Field(default=None, exclude_if=_is_none)
    board_object_id: UUID | None = Field(default=None, exclude_if=_is_none)
    # The number word already visible in the prompt, revealed with its digit after grading.
    quantity_word: str | None = Field(default=None, exclude_if=_is_none)
    roleplay_premise: str | None = Field(default=None, exclude_if=_is_none)
    # Options are shown in their saved, already shuffled order.
    keep_option_order: bool | None = Field(default=None, exclude_if=_is_none)
    planning_facts: list[NonEmptyText] | None = Field(default=None, exclude_if=_is_none)
    # A marker choice: option id -> the scene object whose photo marker answers it.
    marker_object_ids: dict[str, UUID] | None = Field(default=None, exclude_if=_is_none)
    # A short English instruction shown above the prompt.
    instruction: str | None = Field(default=None, exclude_if=_is_none)
    # Target-language text the learner can play aloud.
    audio_text: str | None = Field(default=None, exclude_if=_is_none)
    # Listening questions hide the written prompt until the learner reveals it.
    listen_first: bool | None = Field(default=None, exclude_if=_is_none)
    # A practice board showing this many of ``board_object_id`` without a choice.
    display_count: Annotated[int, Field(ge=1, le=20)] | None = Field(
        default=None, exclude_if=_is_none
    )
    # A chunk with its missing word as ``___``, completed and played after grading.
    slot_template: str | None = Field(default=None, exclude_if=_is_none)
    complete_chunk: str | None = Field(default=None, exclude_if=_is_none)
    gap_type: Literal[
        "chunkChoice", "pictureToBlank", "audioGap", "dialogueGap", "typedGap",
    ] | None = Field(default=None, exclude_if=_is_none)
    gap_kind: str | None = Field(default=None, exclude_if=_is_none)
    assistance_steps: list[
        Literal["replayAudio", "visualDetail", "phraseOnset", "chunkBank", "fullModel"]
    ] | None = Field(default=None, exclude_if=_is_none)
    dialogue: list[LessonDialogueTurn] | None = Field(default=None, exclude_if=_is_none)
    allow_retry: bool | None = Field(default=None, exclude_if=_is_none)
    wrong_field_tokens: dict[str, str] | None = Field(default=None, exclude_if=_is_none)
    option_object_ids: dict[str, UUID] | None = Field(default=None, exclude_if=_is_none)
    option_icons: dict[str, Literal["belongs", "likes", "like", "dislike"]] | None = Field(
        default=None, exclude_if=_is_none
    )
    complete_translation: str | None = Field(default=None, exclude_if=_is_none)
    outcome: MissionQuestionOutcome | None = Field(default=None, exclude_if=_is_none)
    correct_note: str | None = Field(default=None, exclude_if=_is_none)
    typed_allowed: bool | None = Field(default=None, exclude_if=_is_none)

    @model_validator(mode="after")
    def validate_interaction(self) -> GrammarLessonQuestion:
        if self.interaction_type == "multipleChoice" and len(self.options) < 2:
            raise ValueError("multiple-choice questions require answer options")
        if self.interaction_type == "sentenceBuilding" and not self.token_bank:
            raise ValueError("sentence-building questions require a token bank")
        if self.interaction_type == "sentenceBuilding" and self.options:
            raise ValueError("sentence-building questions cannot have answer options")
        if self.interaction_type == "textCloze" and (self.options or self.token_bank):
            raise ValueError("text cloze questions cannot have answer options or a word bank")
        if self.marker_object_ids is not None and set(self.marker_object_ids) != {
            option.option_id for option in self.options
        }:
            raise ValueError("marker choices must cover exactly the answer options")
        if self.option_object_ids is not None and set(self.option_object_ids) != {
            option.option_id for option in self.options
        }:
            raise ValueError("object choices must cover exactly the answer options")
        if self.option_icons is not None and set(self.option_icons) != {
            option.option_id for option in self.options
        }:
            raise ValueError("icon choices must cover exactly the answer options")
        if self.board_counts is not None:
            if set(self.board_counts) != {option.option_id for option in self.options}:
                raise ValueError("board counts must cover exactly the answer options")
            if not all(1 <= count <= 20 for count in self.board_counts.values()):
                raise ValueError("board counts must be between 1 and 20")
            _unique(list(self.board_counts.values()), "board counts must be distinct")
        return self


class MissionScenarioAlternative(ApiModel):
    scene_object_id: UUID
    label: NonEmptyText


class MissionScenario(ApiModel):
    scenario_id: NonEmptyText
    prompt: NonEmptyText
    scene_object_id: UUID
    item_label: NonEmptyText
    accepted: bool
    alternatives: list[MissionScenarioAlternative] = Field(default_factory=list)


class LessonPrepCard(ApiModel):
    """A taught chunk shown, with audio, before a lesson's questions."""

    text: NonEmptyText
    romanization: str | None = Field(default=None, exclude_if=_is_none)
    translation: str | None = None
    scene_object_id: UUID | None = Field(default=None, exclude_if=_is_none)


class GrammarLessonContent(MissionTaskFields):
    kind: Literal["grammarLesson"] = "grammarLesson"
    focus: NonEmptyText
    title: NonEmptyText
    explanation: NonEmptyText | None = Field(default=None, exclude_if=_is_none)
    prep: list[LessonPrepCard] | None = Field(default=None, exclude_if=_is_none)
    questions: Annotated[list[GrammarLessonQuestion], Field(min_length=1)]
    check_each_question: bool | None = Field(default=None, exclude_if=_is_none)
    roleplay_facts: list[RoleplayFact] | None = Field(default=None, exclude_if=_is_none)
    situation: Literal["lostAndFound", "everydayChoice"] | None = Field(
        default=None, exclude_if=_is_none
    )
    taught_chunks: list[TaughtChunk] | None = Field(default=None, exclude_if=_is_none)
    mission_snapshot: A0MissionSnapshot | None = Field(default=None, exclude_if=_is_none)
    scenario: MissionScenario | None = Field(default=None, exclude_if=_is_none)


class GrammarExplanationContent(MissionTaskFields):
    kind: Literal["grammarExplanation"] = "grammarExplanation"
    title: NonEmptyText
    explanation: NonEmptyText
    examples: Annotated[list[NonEmptyText], Field(min_length=1)]
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)


class GrammarPracticeContent(MissionTaskFields):
    kind: Literal["grammarPractice"] = "grammarPractice"
    prompt: NonEmptyText
    options: list[NonEmptyText] = Field(default_factory=list)
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)
    allow_text_answer: bool = True


class SyntaxExplanationContent(MissionTaskFields):
    kind: Literal["syntaxExplanation"] = "syntaxExplanation"
    title: NonEmptyText
    sentence_pattern: NonEmptyText
    explanation: NonEmptyText
    examples: Annotated[list[NonEmptyText], Field(min_length=1)]
    related_vocabulary_ids: list[UUID] = Field(default_factory=list)


class SentenceBuildingContent(MissionTaskFields):
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


class ISpyRoundContent(MissionTaskFields):
    kind: Literal["ispyRound"] = "ispyRound"
    clue: NonEmptyText
    clue_translation: str | None = None
    interaction_mode: ISpyInteractionMode
    options: list[ISpyChoice] = Field(default_factory=list)
    encouragement: str | None = None
    hint_available: bool = True


type ClueFrameId = Literal["name", "colour", "location"]
type ClueSlotId = Literal["position", "reference", "colour"]
type ClueChip = Annotated[str, Field(min_length=1, max_length=200)]


class ClueSlotChip(ApiModel):
    """A vocabulary choice for one slot; a language option, not a claim about the scene."""

    text: ClueChip
    meaning: str | None = Field(default=None, max_length=200)
    example: str | None = Field(default=None, max_length=200)


class ClueSlot(ApiModel):
    slot_id: ClueSlotId
    label: NonEmptyText = Field(max_length=40)
    chips: list[ClueSlotChip] = Field(default_factory=list, max_length=12)


class ClueFrame(ApiModel):
    """An optional sentence starter; ``prefix`` is shown once and slots fill the rest.

    ``chips`` holds complete phrases on tasks saved before slots existed. ``phrases``
    maps ``"position|reference"`` to the composed text, so contractions stay server-side.
    ``help`` holds complete phrases from confirmed facts, shown only on request.
    """

    frame_id: ClueFrameId
    prefix: NonEmptyText = Field(max_length=40)
    meaning: NonEmptyText = Field(max_length=200)
    example: NonEmptyText = Field(max_length=200)
    template: str | None = Field(default=None, max_length=80)
    chips: list[ClueChip] = Field(default_factory=list, max_length=20)
    slots: list[ClueSlot] = Field(default_factory=list, max_length=2)
    phrases: dict[str, ClueChip] = Field(default_factory=dict, max_length=144)
    help: list[ClueChip] = Field(default_factory=list, max_length=12)


class ReflectionContent(MissionTaskFields):
    kind: Literal["reflection"] = "reflection"
    prompt: NonEmptyText
    suggested_vocabulary_ids: list[UUID] = Field(default_factory=list)
    allow_speech: bool = True
    allow_text: bool = True
    clue_frames: list[ClueFrame] = Field(default_factory=list, max_length=3)
    avoid_words: list[ClueChip] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_frames(self) -> ReflectionContent:
        ids = [frame.frame_id for frame in self.clue_frames]
        if len(ids) != len(set(ids)):
            raise ValueError("clueFrames cannot repeat a frameId")
        return self


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


class CorrectionRule(ApiModel):
    """Feedback for a recognisable mistake; empty ``answers`` matches any incorrect answer.

    ``note`` is a short reason this option is wrong, shown after a correct answer.
    """

    mistake: MistakeType
    answers: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    correction: NonEmptyText
    explanation: str | None = None
    note: str | None = None


class QuestionEvaluation(ApiModel):
    """Private link from one question to the mission objective and targets it assesses.

    The accepted answer is the question's existing answer-key entry when it has one;
    ``acceptedAnswers`` serves questions without one, and ``rubricCriterionIds`` names
    the mission criteria for answers judged against a rubric. ``vocabularyItemIds`` and
    ``sceneObjectId`` are hidden targets.
    """

    question_id: NonEmptyText
    objective_id: ContractId
    target_ids: Annotated[list[ContractId], Field(min_length=1)]
    evidence_type: EvidenceType
    accepted_answers: list[NonEmptyText] = Field(default_factory=list)
    rubric_criterion_ids: list[ContractId] = Field(default_factory=list)
    vocabulary_item_ids: list[UUID] = Field(default_factory=list)
    scene_object_id: UUID | None = None
    corrections: list[CorrectionRule] = Field(default_factory=list, max_length=20)
    correct_note: str | None = None

    @model_validator(mode="after")
    def validate_ids(self) -> QuestionEvaluation:
        _unique(self.target_ids, "targetIds cannot repeat")
        _unique(self.rubric_criterion_ids, "rubricCriterionIds cannot repeat")
        return self


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
    accepted_text_answers_by_question: dict[str, list[str]] = Field(
        default_factory=dict, exclude_if=_is_empty
    )
    scene_description_context: JsonObject | None = None
    question_evaluations: list[QuestionEvaluation] = Field(
        default_factory=list, exclude_if=_is_empty
    )
    mission_state: JsonObject | None = Field(default=None, exclude_if=_is_none)
    # Yes/no statement questions: question id -> whether the statement is true.
    statement_correct: dict[str, bool] = Field(default_factory=dict, exclude_if=_is_empty)

    @model_validator(mode="after")
    def validate_question_evaluations(self) -> TaskAnswerKey:
        _unique(
            [item.question_id for item in self.question_evaluations],
            "questionEvaluations cannot repeat a questionId",
        )
        for item in self.question_evaluations:
            keyed = self.has_answer_for(item.question_id)
            if keyed and item.accepted_answers:
                raise ValueError("acceptedAnswers cannot repeat an existing answer key")
            if not (keyed or item.accepted_answers or item.rubric_criterion_ids):
                raise ValueError("each question evaluation needs an accepted answer or rubric")
        return self

    def has_answer_for(self, question_id: str) -> bool:
        if question_id in self.correct_option_ids:
            return True
        return question_id == TASK_QUESTION_ID and bool(
            self.correct_option_id
            or self.correct_scene_object_id
            or self.accepted_text_answers
            or self.expected_token_order
        )


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
        self._validate_mission()
        return self

    def _validate_mission(self) -> None:
        evaluations = self.answer_key.question_evaluations if self.answer_key else []
        key = self.public_content.mission_key
        if key is None:
            if evaluations:
                raise ValueError("questionEvaluations require mission metadata")
            return
        # Imported here because the mission registry depends on these schemas.
        from app.missions import get_mission

        mission = get_mission(*key)
        if mission is None:
            raise ValueError("publicContent names an unknown mission definition")
        questions = getattr(self.public_content, "questions", None)
        known = {item.question_id for item in questions} if questions else {TASK_QUESTION_ID}
        for evaluation in evaluations:
            if evaluation.question_id not in known:
                raise ValueError("questionEvaluations name a question this task does not have")
            mission.check_evaluation(evaluation)


class SessionTaskPublic(ApiModel):
    """Client-safe task response with no answer-key field."""

    id: UUID
    session_id: UUID
    phase: TaskPhase
    kind: TaskKind
    order_index: Annotated[int, Field(ge=0)]
    status: TaskStatus
    xp_reward: Annotated[int, Field(ge=0)] = 0
    xp_bonus: Annotated[int, Field(ge=0)] = 0
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
    def from_internal(
        cls, task: SessionTask, *, mode: SessionMode
    ) -> SessionTaskPublic:
        reward, bonus = task_xp(task.phase, mode)
        return cls.model_validate(
            task.model_dump(
                by_alias=False, exclude={"answer_key", "skip_reason"}
            )
            | {"xp_reward": reward, "xp_bonus": bonus}
        )


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


ISPY_DESCRIPTION_EVALUATION_VERSION = "ispy-description-evaluation.v1"

type ISpyDescriptionOutcome = Literal[
    "clearMatch", "needsClarification", "needsRevision", "noMatch", "evaluationFailed"
]


class ISpyDescriptionEvaluation(ApiModel):
    """``evaluationDetails`` of a model-guessed I-Spy description attempt."""

    version: Literal["ispy-description-evaluation.v1"] = ISPY_DESCRIPTION_EVALUATION_VERSION
    outcome: ISpyDescriptionOutcome
    guessed_object_key: str | None = None
    ambiguous: bool = False
    alternative_object_keys: list[str] = Field(default_factory=list)
    matched_evidence_keys: list[str] = Field(default_factory=list)
    contradicted_evidence_keys: list[str] = Field(default_factory=list)
    target_among_alternatives: bool = False


class MistakeDetail(ApiModel):
    mistake: MistakeType
    answer: str | None = None
    correction: NonEmptyText
    explanation: str | None = None


class QuestionOutcome(ApiModel):
    """Structured result of one question.

    ``assistance`` lists every support the learner opened; ``assistanceUsed`` is true
    only when one of them counts as assistance under the mission's support rules.
    ``optionNotes`` explains why the unselected options do not fit a correct answer.
    ``correctNote`` briefly confirms why the correct answer fits.
    """

    question_id: NonEmptyText
    outcome: QuestionOutcomeStatus
    objective_id: ContractId | None = None
    target_ids: list[ContractId] = Field(default_factory=list)
    evidence_type: EvidenceType
    assistance: list[SupportKind] = Field(default_factory=list)
    assistance_used: bool = False
    mistakes: list[MistakeDetail] = Field(default_factory=list)
    correct_note: str | None = Field(default=None, exclude_if=_is_none)
    option_notes: list[NonEmptyText] = Field(default_factory=list, exclude_if=_is_empty)

    @model_validator(mode="after")
    def validate_outcome(self) -> QuestionOutcome:
        _unique(self.assistance, "assistance cannot repeat a support")
        if self.assistance_used and not self.assistance:
            raise ValueError("assistanceUsed requires the supports that were used")
        if self.mistakes and self.outcome != "incorrect":
            raise ValueError("only incorrect outcomes carry mistakes")
        if self.outcome != "unassessed" and not (self.objective_id and self.target_ids):
            raise ValueError("assessed outcomes require objectiveId and targetIds")
        return self


class QuestionReviewDetails(ApiModel):
    """``evaluationDetails`` of a grouped-question attempt.

    ``questionResults`` and ``correctAnswers`` keep their original meaning;
    ``questionOutcomes`` is added only for tasks with question evaluation metadata.
    """

    question_results: dict[str, bool]
    correct_answers: dict[str, str] = Field(default_factory=dict)
    question_outcomes: list[QuestionOutcome] = Field(default_factory=list, exclude_if=_is_empty)

    @model_validator(mode="after")
    def validate_outcomes(self) -> QuestionReviewDetails:
        _unique(
            [item.question_id for item in self.question_outcomes],
            "questionOutcomes cannot repeat a questionId",
        )
        for item in self.question_outcomes:
            graded = self.question_results.get(item.question_id)
            if item.outcome != "unassessed" and graded is not (item.outcome == "correct"):
                raise ValueError("questionOutcomes must agree with questionResults")
        return self


class TaskHint(EntityModel):
    session_task_id: UUID
    hint_level: Annotated[int, Field(ge=1)]
    content: JsonObject
    requested_at: AwareDatetime = Field(default_factory=utc_now)


CLUE_ASSISTANCE_VERSION = "ispy-clue-assistance.v1"


class ClueSlotChoice(ApiModel):
    frame_id: ClueFrameId
    slot_id: ClueSlotId
    chip: ClueChip


class ClueAssistance(ApiModel):
    """Support visible while a clue was written: guided practice, never independent recall."""

    version: Literal["ispy-clue-assistance.v1"] = CLUE_ASSISTANCE_VERSION
    practice_mode: Literal["guided"] = "guided"
    target_word_shown: Literal[True] = True
    offered_frame_ids: list[ClueFrameId] = Field(default_factory=list, max_length=3)
    selected_frame_ids: list[ClueFrameId] = Field(default_factory=list, max_length=3)
    inserted_chips: list[ClueChip] = Field(default_factory=list, max_length=20)
    selected_slots: list[ClueSlotChoice] = Field(default_factory=list, max_length=6)
    revealed_help_frame_ids: list[ClueFrameId] = Field(default_factory=list, max_length=3)


class LatestClueAttempt(ApiModel):
    """The owner's latest I-Spy attempt: only what the client needs to restore it."""

    id: UUID
    attempt_number: Annotated[int, Field(ge=1)]
    text: str
    option_id: str | None = None
    is_correct: bool | None = None
    feedback: str | None = None
    evaluation_details: ISpyDescriptionEvaluation | None = None
    assistance: ClueAssistance | None = None
    # Grouped-question answers and results, for mission lessons restored after a reload.
    answers: dict[str, str] | None = Field(default=None, exclude_if=_is_none)
    review_details: QuestionReviewDetails | None = Field(default=None, exclude_if=_is_none)

    @classmethod
    def from_attempt(cls, attempt: TaskAttempt, grouped: bool = False) -> LatestClueAttempt:
        payload = attempt.response_payload
        text = payload.get("text")
        option_id = payload.get("optionId")
        message = (attempt.feedback or {}).get("message")
        return cls(
            id=attempt.id,
            attempt_number=attempt.attempt_number,
            text=text if isinstance(text, str) else "",
            option_id=option_id if isinstance(option_id, str) else None,
            is_correct=attempt.is_correct,
            feedback=message if isinstance(message, str) else None,
            evaluation_details=_optional(ISpyDescriptionEvaluation, attempt.evaluation_details),
            assistance=_optional(ClueAssistance, payload.get("assistance")),
            **(dict(
                answers={
                    key: value for key, value in (payload.get("answers") or {}).items()
                    if isinstance(value, str)
                },
                review_details=_optional(QuestionReviewDetails, attempt.evaluation_details),
            ) if grouped else {}),
        )


def _optional(model, value):
    try:
        return model.model_validate(value) if isinstance(value, dict) else None
    except ValidationError:
        return None


class LatestAttemptResponse(ApiModel):
    attempt: LatestClueAttempt | None = None


class SubmitTextAttemptRequest(ApiModel):
    input_mode: Literal["text"] = "text"
    text: Annotated[str, Field(min_length=1, max_length=2_000)]
    assistance: ClueAssistance | None = None
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


class QuestionAssistance(ApiModel):
    """Supports the learner opened for one question, saved in ``responsePayload``."""

    question_id: NonEmptyText
    supports: Annotated[list[SupportKind], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def validate_supports(self) -> QuestionAssistance:
        _unique(self.supports, "supports cannot repeat")
        return self


class SubmitVocabularyReviewAttemptRequest(ApiModel):
    input_mode: Literal["vocabularyReview"] = "vocabularyReview"
    answers: dict[str, NonEmptyText]
    typed_answers: dict[str, str] = Field(default_factory=dict)
    question_assistance: Annotated[list[QuestionAssistance], Field(max_length=50)] | None = None
    idempotency_key: Annotated[str, Field(min_length=8, max_length=200)] | None = None

    @model_validator(mode="after")
    def validate_answers(self) -> SubmitVocabularyReviewAttemptRequest:
        if not self.answers:
            raise ValueError("answers cannot be empty")
        _unique(
            [item.question_id for item in self.question_assistance or []],
            "questionAssistance cannot repeat a questionId",
        )
        return self


class CheckVocabularyAnswerRequest(ApiModel):
    question_id: NonEmptyText
    option_id: NonEmptyText
    review: bool = False


class CheckVocabularyAnswerResponse(ApiModel):
    accepted_option_id: NonEmptyText
    basil_earned: int = 0
    question_id: NonEmptyText
    is_correct: bool
    correct_option_id: NonEmptyText


class CheckVocabularyTypingRequest(ApiModel):
    learning_key: NonEmptyText
    answer: Annotated[str, Field(max_length=2_000)] = ""
    reveal: bool = False

    @model_validator(mode="after")
    def validate_answer(self) -> CheckVocabularyTypingRequest:
        if not self.reveal and not self.answer.strip():
            raise ValueError("answer cannot be empty")
        return self


class CheckVocabularyTypingResponse(ApiModel):
    learning_key: NonEmptyText
    is_correct: bool
    correct_answer: NonEmptyText
    revealed: bool


class VocabularyChecksResponse(ApiModel):
    checks: list[CheckVocabularyAnswerResponse] = Field(default_factory=list)


class CheckLessonAnswerRequest(ApiModel):
    question_id: NonEmptyText
    answer: Annotated[str, Field(min_length=1, max_length=2_000)]


class LessonAssistanceRequest(ApiModel):
    question_id: NonEmptyText
    step: Literal["replayAudio", "visualDetail", "phraseOnset", "chunkBank", "fullModel"]


class LessonAssistanceResponse(ApiModel):
    question_id: NonEmptyText
    step: Literal["replayAudio", "visualDetail", "phraseOnset", "chunkBank", "fullModel"]
    content: NonEmptyText


class MissionScenarioRequest(ApiModel):
    action: Literal["accept", "choose"]
    scene_object_id: UUID | None = None


class MissionScenarioResponse(ApiModel):
    accepted: bool
    tasks: list[SessionTaskPublic] = Field(default_factory=list)


class LessonAnswerCheck(ApiModel):
    basil_earned: int = 0
    question_id: NonEmptyText
    answer: NonEmptyText
    is_correct: bool
    correct_answer: str | None
    outcome: QuestionOutcome
    attempts_left: int | None = Field(default=None, exclude_if=_is_none)
    feedback: str | None = Field(default=None, exclude_if=_is_none)
    wrong_field: str | None = Field(default=None, exclude_if=_is_none)
    assistance_steps_used: list[str] = Field(default_factory=list)


class CheckLessonAnswerResponse(LessonAnswerCheck):
    pass


class LessonChecksResponse(ApiModel):
    checks: list[LessonAnswerCheck] = Field(default_factory=list)
    assistance_steps: dict[str, list[str]] = Field(default_factory=dict)


type SubmitTaskAttemptRequest = Annotated[
    SubmitTextAttemptRequest
    | SubmitSpeechAttemptRequest
    | SubmitObjectSelectionAttemptRequest
    | SubmitMultipleChoiceAttemptRequest
    | SubmitVocabularyReviewAttemptRequest,
    Field(discriminator="input_mode"),
]


class ConfirmGuessRequest(ApiModel):
    attempt_id: UUID


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
    basil_earned: int = 0
    task: SessionTaskPublic
    attempt: TaskAttempt | None = None
    next_task_id: UUID | None = None
    session_progress: SessionProgress
    xp_earned: Annotated[int, Field(ge=0)] = 0
