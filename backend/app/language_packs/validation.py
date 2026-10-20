"""Validate the shared M01 product contract, independently of linguistic assessment."""

from collections import Counter

from .schema import join_pack_chunks

PURPOSES = {
    "A0": ["matchName", "confirmName", "buildIdentify"] * 2,
    "A1": ["confirmObject", "confirmObject", "chooseAttribute", "describeObject"],
    "A2": [
        "chooseSceneMarker",
        "buildSceneFact",
        "chooseSceneDescription",
        "buildSceneDescription",
        "followUpSceneFact",
    ],
}


def validate_assembled_lesson(level, result, approved, pack):
    """Keep the existing count, order, grouping and interaction contract."""
    questions = result.questions
    if [question.purpose for question in questions] != PURPOSES[level]:
        raise ValueError("assembled M01 questions do not preserve the mission sequence")
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError("assembled M01 question IDs must be unique")
    if (
        list(Counter(question.section for question in questions).values())
        != {
            "A0": [3, 3],
            "A1": [2, 2],
            "A2": [2, 2, 1],
        }[level]
    ):
        raise ValueError("assembled M01 task grouping has changed")
    for sentence in approved:
        if (
            join_pack_chunks(sentence.candidate.chunks, pack.language.word_separator)
            != sentence.candidate.text
        ):
            raise ValueError("approved chunks no longer reconstruct the validated sentence")
    for question in questions:
        building = question.purpose in {
            "buildIdentify",
            "describeObject",
            "buildSceneFact",
            "buildSceneDescription",
        }
        if (question.interaction_type == "sentenceBuilding") != building:
            raise ValueError("assembled M01 changed a question's interaction type")
        if building:
            if not question.correct_text or not question.token_bank or question.options:
                raise ValueError("assembled building question needs a native answer and tiles")
        else:
            ids = [option.option_id for option in question.options]
            if len(ids) < 2 or len(ids) != len(set(ids)) or question.correct_option_id not in ids:
                raise ValueError("assembled choices need unique IDs and an offered answer")
