from types import SimpleNamespace
from uuid import UUID

from app.services.lesson_tasks.m06 import select_transaction
from app.services.mission_eligibility import lesson_missions
from app.services.mission_m06_lexicon import (
    ITEMS,
)


def _object(label, number=1):
    return SimpleNamespace(id=UUID(int=number), label=label, attributes={"colour": "red"})


def _payload(item_key, language, quantity, follow_type, follow_value, *, size=None, mismatch=None):
    item = ITEMS[item_key]
    transaction = select_transaction("m06-test", item, language)
    transaction.update(
        {
            "itemKey": item.key,
            "itemLabel": item.label,
            "quantity": quantity,
            "requestDetails": {"size": size} if size else {},
            "followUp": {"type": follow_type, "value": follow_value},
            "serviceSetting": follow_value
            if item.category == "cafe" and follow_type == "serviceSetting"
            else ("takeAway" if item.category == "cafe" else None),
            "mismatch": mismatch
            or {
                "flag": False,
                "field": None,
                "servedValue": None,
                "correctedValue": None,
            },
            "sceneObjectId": str(UUID(int=1)),
            "scenarioAccepted": False,
            "alternatives": [],
            "q5Mode": "chunkChoice",
        }
    )
    return {
        "targetLanguage": language,
        "itemKey": item.key,
        "transaction": transaction,
        "alternatives": [],
        "q5Mode": "chunkChoice",
    }










def test_m06_is_a2_only():
    for level in ("A0", "A1", "B1"):
        missions = lesson_missions(
            "lesson",
            {"proficiency_level": level, "target_language_code": "es"},
        )
        assert all(mission.mission_id != "M06" for mission in missions)
    assert [
        item.mission_id
        for item in lesson_missions(
            "lesson",
            {"proficiency_level": "A2", "target_language_code": "de"},
        )
    ] == ["M01", "M02", "M03", "M04", "M06"]
    assert "M06" in {
        item.mission_id
        for item in lesson_missions(
            "lesson",
            {"proficiency_level": "A2", "target_language_code": "es"},
        )
    }
    for language in ("de", "es"):
        assert [
            item.mission_id
            for item in lesson_missions(
                "lesson", {"proficiency_level": "A1", "target_language_code": language}
            )
        ] == ["M01", "M02", "M03", "M04", "M05"]
        assert [
            item.mission_id
            for item in lesson_missions(
                "lesson", {"proficiency_level": "A0", "target_language_code": language}
            )
        ] == ["M01", "M02", "M03", "M04", "M05", "M13"]






ORDER_CASES = [
    ("coffee", 2, "serviceSetting", "takeAway", "small"),
    ("pen", 1, "colour", "blue", None),
    ("apple", 2, "size", "big", None),
    ("cup", 2, "colour", "blue", None),
]














