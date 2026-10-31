"""Interpret a target-blind I-Spy guess against the task's assigned target."""

from uuid import UUID

from app.ai.features.ispy_guess import ISpyGuessResult
from app.schemas.tasks import ISpyDescriptionEvaluation
from app.services.ispy_levels import ispy_level

EVALUATION_FAILED_MESSAGE = (
    "Linguini couldn't check your clue just now. Your clue is saved, so try guessing again."
)
MORE_DETAIL_MESSAGE = (
    "Linguini thinks it knows, but add one more detail, like its colour or where it is, "
    "to be sure."
)

# Only a clear match is correct and only a confident wrong guess is incorrect;
# clarification, revision and failures stay unresolved.
OUTCOME_CORRECTNESS = {
    "clearMatch": True,
    "needsClarification": None,
    "needsRevision": None,
    "noMatch": False,
    "evaluationFailed": None,
}


def target_evidence(context: dict | None, target: str | None) -> set[str]:
    """The confirmed attribute and relation keys a description of ``target`` could match."""
    facts = (context or {}).get("sceneObjects", {})
    return {
        row["key"] for row in facts.get("attributes", []) if row.get("objectKey") == target
    } | {
        row["key"] for row in facts.get("relations", [])
        if target in (row.get("subjectObjectKey"), row.get("referenceObjectKey"))
    }


def needs_more_detail(guess: ISpyGuessResult, settings, available: set[str]) -> bool:
    """A level that wants several details (A2) gets them, up to what the object has."""
    if settings.min_clear_evidence <= 1 or not available:
        return False
    needed = min(settings.min_clear_evidence, len(available))
    return len(set(guess.matched_evidence_keys) & available) < needed


def interpret_guess(
    guess: ISpyGuessResult | None, target_object_id: UUID | None, *,
    level=None, context: dict | None = None,
) -> ISpyDescriptionEvaluation:
    if guess is None:
        return ISpyDescriptionEvaluation(outcome="evaluationFailed")
    settings = ispy_level(level)
    target = str(target_object_id) if target_object_id else None
    alternatives = list(guess.alternative_object_keys)
    ambiguous = guess.ambiguous or bool(alternatives)
    among_alternatives = target is not None and target in alternatives
    if target is not None and guess.guessed_object_key == target:
        if guess.contradicted_evidence_keys:
            outcome = "needsRevision"
        elif ambiguous and not settings.accept_ambiguous_match:
            outcome = "needsClarification"
        elif needs_more_detail(guess, settings, target_evidence(context, target)):
            outcome = "needsClarification"
        else:
            outcome = "clearMatch"
    elif among_alternatives:
        outcome = "needsClarification"
    else:
        outcome = "noMatch"
    return ISpyDescriptionEvaluation(
        outcome=outcome,
        guessed_object_key=guess.guessed_object_key,
        ambiguous=ambiguous,
        alternative_object_keys=alternatives,
        matched_evidence_keys=list(guess.matched_evidence_keys),
        contradicted_evidence_keys=list(guess.contradicted_evidence_keys),
        target_among_alternatives=among_alternatives,
    )


def guess_feedback(
    guess: ISpyGuessResult | None, interpretation: ISpyDescriptionEvaluation,
    target_object_id: UUID | None,
) -> str:
    """The model's feedback, unless the level asked for more detail than the model judged."""
    if guess is None:
        return EVALUATION_FAILED_MESSAGE
    if (
        interpretation.outcome == "needsClarification"
        and guess.guessed_object_key == (str(target_object_id) if target_object_id else None)
        and not interpretation.ambiguous
    ):
        return MORE_DETAIL_MESSAGE
    return guess.feedback
