"""Shared API and domain enum values."""

from collections.abc import Mapping
from enum import StrEnum


class ProficiencyLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class PreferredInputMode(StrEnum):
    SPEECH = "speech"
    TEXT = "text"
    BOTH = "both"


class MediaType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"


class MediaSource(StrEnum):
    USER_UPLOAD = "userUpload"
    CAMERA = "camera"
    PRELOADED = "preloaded"
    GENERATED = "generated"


class SceneRelationType(StrEnum):
    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    ABOVE = "above"
    BELOW = "below"
    ON = "on"
    UNDER = "under"
    INSIDE = "inside"
    IN_FRONT_OF = "in_front_of"
    BEHIND = "behind"
    NEXT_TO = "next_to"
    NEAR = "near"


SYMMETRIC_SCENE_RELATION_TYPES: frozenset[SceneRelationType] = frozenset(
    {SceneRelationType.NEXT_TO, SceneRelationType.NEAR}
)

INVERSE_SCENE_RELATION_TYPES: Mapping[SceneRelationType, SceneRelationType] = {
    SceneRelationType.LEFT_OF: SceneRelationType.RIGHT_OF,
    SceneRelationType.RIGHT_OF: SceneRelationType.LEFT_OF,
    SceneRelationType.ABOVE: SceneRelationType.BELOW,
    SceneRelationType.BELOW: SceneRelationType.ABOVE,
    SceneRelationType.ON: SceneRelationType.UNDER,
    SceneRelationType.UNDER: SceneRelationType.ON,
    SceneRelationType.IN_FRONT_OF: SceneRelationType.BEHIND,
    SceneRelationType.BEHIND: SceneRelationType.IN_FRONT_OF,
}


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    INTERJECTION = "interjection"
    DETERMINER = "determiner"
    PHRASE = "phrase"
    OTHER = "other"


class VocabularyLearningStatus(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    MASTERED = "mastered"


class VocabularyEncounterType(StrEnum):
    INTRODUCED = "introduced"
    PRACTISED = "practised"
    RECALLED = "recalled"
    MASTERED = "mastered"


class VocabularyEncounterOutcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    COMPLETED = "completed"


class SessionStatus(StrEnum):
    CREATED = "created"
    ANALYZING_SCENE = "analyzingScene"
    AWAITING_OBJECT_REVIEW = "awaitingObjectReview"
    GENERATING_TASKS = "generatingTasks"
    READY = "ready"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    FAILED = "failed"


class SessionFailureCode(StrEnum):
    IMAGE_UPLOAD_FAILED = "imageUploadFailed"
    SCENE_ANALYSIS_FAILED = "sceneAnalysisFailed"
    IMAGE_MODERATION_FAILED = "imageModerationFailed"
    NO_VALID_OBJECTS = "noValidObjects"
    VOCABULARY_MAPPING_FAILED = "vocabularyMappingFailed"
    TASK_GENERATION_FAILED = "taskGenerationFailed"


class TaskPhase(StrEnum):
    LEARNING = "learning"
    ISPY = "ispy"


class TaskKind(StrEnum):
    VOCABULARY_INTRODUCTION = "vocabularyIntroduction"
    GRAMMAR_LESSON = "grammarLesson"
    GRAMMAR_EXPLANATION = "grammarExplanation"
    GRAMMAR_PRACTICE = "grammarPractice"
    SYNTAX_EXPLANATION = "syntaxExplanation"
    SENTENCE_BUILDING = "sentenceBuilding"
    ISPY_ROUND = "ispyRound"
    REFLECTION = "reflection"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class AttemptInputMode(StrEnum):
    SPEECH = "speech"
    TEXT = "text"
    OBJECT_SELECTION = "objectSelection"
    MULTIPLE_CHOICE = "multipleChoice"
    VOCABULARY_REVIEW = "vocabularyReview"


class ISpyInteractionMode(StrEnum):
    SELECT_OBJECT = "selectObject"
    SPEAK_ANSWER = "speakAnswer"
    TYPE_ANSWER = "typeAnswer"


class JournalStatus(StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"


class JournalRevisionCreator(StrEnum):
    USER = "user"
    AI = "ai"
    MERGED = "merged"


class JournalSuggestionType(StrEnum):
    GRAMMAR = "grammar"
    SPELLING = "spelling"
    SYNTAX = "syntax"
    VOCABULARY = "vocabulary"
    CLARITY = "clarity"


class JournalSuggestionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class WordMatchMethod(StrEnum):
    EXACT = "exact"
    INFLECTED = "inflected"
    SEMANTIC = "semantic"
    USER_CONFIRMED = "userConfirmed"


class XpEventType(StrEnum):
    TASK_COMPLETED = "taskCompleted"
    ISPY_CORRECT = "ispyCorrect"
    SESSION_COMPLETED = "sessionCompleted"
    PERFECT_SESSION = "perfectSession"
    JOURNAL_ENTRY = "journalEntry"
    LEGACY_BACKFILL = "legacyBackfill"
