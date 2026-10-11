"""Interpret a target-blind I-Spy guess against the task's assigned target."""

from uuid import UUID

from app.ai.features.ispy_guess import ISpyGuessResult
from app.schemas.tasks import ISpyDescriptionEvaluation

EVALUATION_FAILED_MESSAGE = (
    "Linguini couldn't check your clue just now. Your clue is saved, so try guessing again."
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


def interpret_guess(
    guess: ISpyGuessResult | None, target_object_id: UUID | None
) -> ISpyDescriptionEvaluation:
    if guess is None:
        return ISpyDescriptionEvaluation(outcome="evaluationFailed")
    target = str(target_object_id) if target_object_id else None
    alternatives = list(guess.alternative_object_keys)
    ambiguous = guess.ambiguous or bool(alternatives)
    among_alternatives = target is not None and target in alternatives
    if target is not None and guess.guessed_object_key == target:
        if guess.contradicted_evidence_keys:
            outcome = "needsRevision"
        elif ambiguous:
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
