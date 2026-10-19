from uuid import uuid4

import pytest

from app.repositories.postgres.onboarding import placement_attempts, placement_level
from app.schemas.onboarding import PlacementQuestion


def questions():
    return [
        PlacementQuestion(
            id=uuid4(), questionKey=f"q{index}", orderIndex=index,
            prompt="Question", promptTranslation="Question", skill="comprehension",
            difficulty="A2" if index > 4 else ("A1" if index > 2 else "A0"),
            options=[{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}],
        )
        for index in range(1, 7)
    ]


@pytest.mark.parametrize(("path_keys", "correct_keys", "expected"), [
    (("q3", "q1", "q2"), {"q2"}, "A0"),
    (("q3", "q1", "q4"), {"q1", "q4"}, "A1"),
    (("q3", "q5", "q6"), {"q3", "q5"}, "A1"),
    (("q3", "q5", "q6"), {"q3", "q5", "q6"}, "A2"),
])
def test_placement_level_scores_an_adaptive_three_question_path(
    path_keys, correct_keys, expected
):
    items = questions()
    keys = {item.id: "yes" for item in items}
    path = [item for item in items if item.question_key in path_keys]
    answers = {item.id: ("yes" if item.question_key in correct_keys else "no") for item in path}

    level, score = placement_level(items, answers, keys)

    assert level == expected
    assert score == len(correct_keys)


def test_placement_requires_every_answer():
    items = questions()
    with pytest.raises(ValueError, match="placement path"):
        placement_level(items, {}, {item.id: "yes" for item in items})


def test_placement_attempt_ids_are_generated_before_insert():
    assert placement_attempts.c.id.default is not None
