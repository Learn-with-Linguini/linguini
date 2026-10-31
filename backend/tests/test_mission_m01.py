"""M01 A1 eligibility, reviewed colour forms and the deterministic lesson."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.missions import get_mission
from app.services.mission_eligibility import lesson_missions, photo_eligibility

DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least 2 different objects."
)
ONE_DETAIL_REASON = (
    "Confirm a colour, size, shape, material, pattern or state of at least one object."
)
MISSION = get_mission("M01", "A1", 1)
CUP = "11111111-1111-1111-1111-111111111111"
BOOK = "22222222-2222-2222-2222-222222222222"
TABLE = "33333333-3333-3333-3333-333333333333"


def obj(label, **attributes):
    return SimpleNamespace(label=label, attributes=attributes or None)


def word(item_id, text, gender):
    return SimpleNamespace(id=item_id, display_text=text, gender=gender)


def scene_object(item_id, label, colour):
    return SimpleNamespace(id=item_id, label=label, attributes={"color": colour})


@pytest.mark.parametrize(("objects", "reasons"), [
    ([obj("cup", color="red"), obj("book", color="green")], ()),
    ([obj("cup", color="red"), obj("Cup ", color="blue")], (
        "Confirm at least 2 different objects.",
        DETAIL_REASON,
    )),
    # Any confirmed detail counts, in the scene's own words: packs translate it.
    ([obj("cup", color="red"), obj("book", material="paper")], ()),
    ([obj("cup", color="sparkly"), obj("book", color="green")], ()),
    ([obj("cup", color="red"), obj("book")], (DETAIL_REASON,)),
])
def test_eligibility_uses_only_confirmed_names_and_details(objects, reasons):
    result = photo_eligibility(MISSION, objects)
    assert (result.eligible, result.reasons) == (not reasons, reasons)




@pytest.mark.parametrize(("mode", "level", "language", "selected"), [
    ("lesson", "A1", "es", True),
    ("lesson", "A1", "fr", True),
    # A0 is the stored level for "I'm a complete beginner" (pre-A1); it gets the A0 missions.
    ("lesson", "A0", "es", True),
    ("lesson", "A0", "fr", True),
    ("lesson", "A2", "es", True),
    ("lesson", "A2", "fr", True),
    ("lesson", "A2", "de", True),
    ("lesson", "A2", "ko", True),
    ("lesson", "B1", "fr", False),
    ("lesson", None, "es", False),
    ("lesson", "A1", "de", True),
    ("lesson", "A1", "ko", True),
    ("ispyGame", "A1", "es", False),
])
def test_mission_path_only_plans_enabled_levels_and_languages(
    mode, level, language, selected,
):
    profile = {"proficiency_level": level, "target_language_code": language}
    assert bool(lesson_missions(mode, profile)) is selected


SESSION = UUID("44444444-4444-4444-4444-444444444444")




def labels(question):
    return [option.label for option in question.options]


def correct(question):
    return next(o.label for o in question.options if o.option_id == question.correct_option_id)
































def _mutate(result, index, **changes):
    questions = list(result.questions)
    questions[index] = questions[index].model_copy(update=changes)
    return result.model_copy(update={"questions": questions})






def detailed(item_id, label, **attributes):
    return SimpleNamespace(id=item_id, label=label, attributes=attributes)








