from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.ai.features.learning_tasks.mission_m06 import validate_m06_lesson
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import lesson_missions
from app.services.mission_eligibility_a2 import eligibility_reasons
from app.services.mission_m06_lexicon import (
    EXCLUDED,
    ITEMS,
    normalize_item_label,
    requestable_objects,
)
from app.services.mission_m06_request_details import (
    CONFIRM,
    build_m06_payload,
    build_m06_result,
    select_transaction,
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


def _questions(payload):
    result = build_m06_result(payload)
    validate_m06_lesson(payload, result)
    return result.questions


@pytest.mark.parametrize(
    "language,expected",
    [
        ("es", "Quisiera dos cafés pequeños, por favor."),
        ("fr", "Je voudrais deux petits cafés, s'il vous plaît."),
        ("de", "Ich hätte gern zwei kleine Kaffees, bitte."),
        ("ko", "작은 커피 두 잔 주세요."),
    ],
)
def test_exact_coffee_request_chunks(language, expected):
    questions = _questions(
        _payload(
            "coffee",
            language,
            2,
            "serviceSetting",
            "takeAway",
            size="small",
        )
    )
    assert questions[0].audio_text == expected
    assert questions[2].correct_text == expected
    assert len(set(question.gap_kind for question in questions)) >= 3


def test_exact_pen_apple_and_korean_cup_sentences():
    pen_es = _questions(_payload("pen", "es", 1, "colour", "blue"))
    assert pen_es[2].correct_text == "¿Me prestas un bolígrafo, por favor?"
    q5 = pen_es[4]
    assert next(
        option.label for option in q5.options if option.option_id == q5.correct_option_id
    ) == "Azul, por favor."

    apple_es = _questions(_payload("apple", "es", 2, "size", "big"))
    assert apple_es[2].correct_text == "Quisiera dos manzanas, por favor."
    assert apple_es[3].audio_text == "¿Grandes o pequeñas?"
    q5 = apple_es[4]
    assert next(
        option.label for option in q5.options if option.option_id == q5.correct_option_id
    ) == ("Grandes, por favor.")

    cup_ko = _questions(_payload("cup", "ko", 2, "colour", "blue"))
    assert cup_ko[2].correct_text == "컵 두 개 주세요."
    q5 = cup_ko[4]
    assert (
        next(option.label for option in q5.options if option.option_id == q5.correct_option_id)
        == "파란색이요."
    )
    assert "두 개" in cup_ko[2].correct_chunks


def test_requestable_lexicon_aliases_exclusions_and_confirmed_order():
    assert normalize_item_label("A coffee cup") == "cup"
    assert normalize_item_label("ballpoint pens") == "pen"
    assert normalize_item_label("coffee") == "coffee"
    assert set(EXCLUDED) == {
        "sky",
        "road",
        "street",
        "building",
        "house",
        "tree",
        "person",
        "man",
        "woman",
        "child",
        "people",
        "wall",
        "floor",
        "ceiling",
        "window",
        "grass",
        "mountain",
        "cloud",
        "sea",
        "scenery",
        "table",
        "chair",
    }
    objects = [_object("sky"), _object("the apple", 2), _object("a cup", 3)]
    assert [item.key for _obj, item in requestable_objects(objects)] == ["apple", "cup"]
    mission = get_mission("M06", "A2", 1)
    assert (
        eligibility_reasons(
            "requestableItem",
            mission,
            [_object("coffee")],
            [],
            [],
        )
        == []
    )
    for label in ("sky", "road", "building", "tree", "person", "scenery"):
        assert eligibility_reasons(
            "requestableItem",
            mission,
            [_object(label)],
            [],
            [],
        ) == ["Confirm a food, drink or everyday object you could ask for."]


def test_m06_is_a2_only_and_language_scoped():
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
    ] == ["M06"]
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
        ] == ["M01", "M02", "M03", "M05", "M13"]


def test_transaction_is_deterministic_does_not_mutate_scene_and_repairs_one_field():
    obj = _object("coffee")
    original = deepcopy(obj.__dict__)
    transactions = [select_transaction("session", ITEMS["coffee"], "es") for _ in range(2)]
    assert transactions[0] == transactions[1]
    assert obj.__dict__ == original
    for seed in range(100):
        payload = _payload(
            "coffee",
            "de",
            2,
            "temperature",
            "hot",
            size="large",
            mismatch={
                "flag": True,
                "field": "size",
                "servedValue": "small",
                "correctedValue": "large",
            }
            if seed % 2
            else {
                "flag": False,
                "field": None,
                "servedValue": None,
                "correctedValue": None,
            },
        )
        questions = _questions(payload)
        assert questions[-1].correct_text == payload["expectedQ6Answer"]
        assert payload["transaction"]["mismatch"]["field"] in {None, "size"}


@pytest.mark.parametrize(
    "completed,independent,expected",
    [
        (0, 0, "chunkChoice"),
        (1, 0, "wordBank"),
        (2, 1, "wordBank"),
        (2, 2, "openCloze"),
    ],
)
def test_q5_mode_requires_profile_history(completed, independent, expected):
    obj = _object("coffee")
    payload = build_m06_payload(
        get_mission("M06", "A2", 1),
        "es",
        [obj],
        uuid4(),
        {"m06CompletedLessons": completed, "m06IndependentQ5": independent},
        {str(obj.id): 0},
        {},
    )
    assert payload["q5Mode"] == expected


ORDER_CASES = [
    ("coffee", 2, "serviceSetting", "takeAway", "small"),
    ("pen", 1, "colour", "blue", None),
    ("apple", 2, "size", "big", None),
    ("cup", 2, "colour", "blue", None),
]


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("item_key,quantity,follow_type,follow_value,size", ORDER_CASES)
def test_q1_distractors_change_exactly_one_order_field(
    language, item_key, quantity, follow_type, follow_value, size
):
    questions = _questions(
        _payload(item_key, language, quantity, follow_type, follow_value, size=size)
    )
    assert len({question.gap_kind for question in questions}) >= 3
    q1 = questions[0]
    correct = {
        "item": item_key,
        "quantity": str(quantity),
        **({"size": size} if size else {}),
    }
    distractors = {
        option_id: fields for option_id, fields in q1.option_fields.items()
        if option_id != q1.correct_option_id
    }
    assert set(distractors) == {
        option.option_id for option in q1.options if option.option_id != q1.correct_option_id
    }
    for fields in distractors.values():
        assert len(fields) == 1
        field, changed_value = next(iter(fields.items()))
        assert field in correct
        assert changed_value != correct[field]


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("item_key,quantity,follow_type,follow_value,size", ORDER_CASES)
def test_q4_asks_for_a_missing_detail_and_maps_given_detail_distractor(
    language, item_key, quantity, follow_type, follow_value, size
):
    payload = _payload(item_key, language, quantity, follow_type, follow_value, size=size)
    questions = _questions(payload)
    q4 = questions[3]
    assert q4.correct_option_id == "correct"
    assert payload["transaction"]["followUp"]["type"] not in (
        {"item", "quantity"} | set(payload["transaction"]["requestDetails"])
    )
    assert q4.distractor_fields["given"] == "quantity"
    assert any(option.option_id == "given" for option in q4.options)
    assert any(option.option_id == "other" for option in q4.options)


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_every_distractor_in_all_six_questions_has_a_field_mapping(language):
    payload = _payload("coffee", language, 2, "serviceSetting", "takeAway", size="small")
    questions = _questions(payload)
    for question in questions:
        if question.options:
            distractors = {
                option.option_id for option in question.options
                if option.option_id != question.correct_option_id
            }
        elif question.interaction_type == "sentenceBuilding":
            distractors = set(question.token_bank) - set(question.correct_chunks)
        else:
            distractors = set()
        assert distractors <= set(question.distractor_fields), question.question_id
    assert len(questions[-1].token_bank) == len(set(questions[-1].token_bank))
    assert questions[-1].token_bank.count(".") == 1
    if language == "ko":
        assert any(
            field == "quantity" and chunk in {"한 잔", "세 잔"}
            for chunk, field in questions[2].distractor_fields.items()
        )


def test_transaction_mismatch_is_single_field_and_repeat_matches_served_order():
    for session_number in range(50):
        for item in ITEMS.values():
            for language in ("es", "fr", "de", "ko"):
                transaction = select_transaction(f"session-{session_number}", item, language)
                transaction.update(
                    {
                        "itemKey": item.key,
                        "itemLabel": item.label,
                        "sceneObjectId": str(UUID(int=1)),
                        "scenarioAccepted": False,
                        "alternatives": [],
                        "q5Mode": "chunkChoice",
                    }
                )
                payload = {
                    "targetLanguage": language,
                    "itemKey": item.key,
                    "transaction": transaction,
                    "alternatives": [],
                    "q5Mode": "chunkChoice",
                }
                questions = _questions(payload)
                mismatch = transaction["mismatch"]
                assert len(mismatch) == 4
                assert mismatch["flag"] is (mismatch["field"] is not None)
                assert (questions[-1].correct_text == CONFIRM[language]) is not mismatch["flag"]
                if mismatch["flag"]:
                    assert mismatch["servedValue"] != mismatch["correctedValue"]
                    served = deepcopy(transaction)
                    if mismatch["field"] == "quantity":
                        served["quantity"] = mismatch["servedValue"]
                    elif mismatch["field"] == "size" and transaction["requestDetails"].get("size"):
                        served["requestDetails"]["size"] = mismatch["servedValue"]
                    else:
                        served["followUp"]["value"] = mismatch["servedValue"]
                    served["mismatch"] = {
                        "flag": False,
                        "field": None,
                        "servedValue": None,
                        "correctedValue": None,
                    }
                    served_payload = {
                        **payload,
                        "transaction": served,
                    }
                    served_repeat = build_m06_result(served_payload).questions[-1].audio_text
                    assert questions[-1].audio_text == served_repeat


@pytest.mark.parametrize(
    "language,expected_request,expected_reply,expected_confirm,expected_repeat",
    [
        (
            "es", "¿Me prestas un bolígrafo, por favor?", "Azul, por favor.",
            "Sí, eso es.", "Entonces, un bolígrafo, azul, ¿verdad?",
        ),
        (
            "fr", "Tu peux me prêter un stylo, s'il te plaît ?", "Bleu, s'il te plaît.",
            "Oui, c'est ça.", "Alors, un stylo, bleu, c'est ça ?",
        ),
        (
            "de", "Kannst du mir bitte einen Stift leihen?", "Blau, bitte.",
            "Ja, genau.", "Also, ein Stift, blau, richtig?",
        ),
        ("ko", "펜 한 자루 빌려 주세요.", "파란색이요.", "네, 맞아요.", "펜 한 자루, 파란색이요?"),
    ],
)
def test_q5_q6_reply_strings_and_capitalization(
    language, expected_request, expected_reply, expected_confirm, expected_repeat
):
    payload = _payload("pen", language, 1, "colour", "blue")
    payload["q5Mode"] = "wordBank"
    questions = _questions(payload)
    q5 = questions[4]
    assert questions[0].audio_text == expected_request
    assert (
        expected_reply in [option.label for option in q5.options]
        or expected_reply == q5.correct_text
    )
    assert q5.accepted_answers[0][0].isupper() or language == "ko"
    if q5.interaction_type == "sentenceBuilding":
        assert q5.token_bank.count(".") == 1
        assert q5.correct_chunks[0][0].isupper() or language == "ko"
    assert questions[5].correct_text == expected_confirm
    assert questions[5].audio_text == expected_repeat


@pytest.mark.parametrize(
    "language,expected",
    [
        (
                "es",
                [
                    "Quisiera dos cafés pequeños, por favor.",
                    "¿Me prestas un bolígrafo, por favor?",
                    "Quisiera dos manzanas, por favor.",
                    "¿Me pasas dos tazas, por favor?",
                ],
        ),
        (
                "fr",
                [
                    "Je voudrais deux petits cafés, s'il vous plaît.",
                    "Tu peux me prêter un stylo, s'il te plaît ?",
                    "Je voudrais deux pommes, s'il vous plaît.",
                    "Tu peux me passer deux tasses, s'il te plaît ?",
                ],
        ),
        (
                "de",
                [
                    "Ich hätte gern zwei kleine Kaffees, bitte.",
                    "Kannst du mir bitte einen Stift leihen?",
                    "Ich hätte gern zwei Äpfel, bitte.",
                    "Kannst du mir bitte zwei Tassen geben?",
                ],
        ),
        (
                "ko",
                [
                    "작은 커피 두 잔 주세요.",
                    "펜 한 자루 빌려 주세요.",
                    "사과 두 개 주세요.",
                    "컵 두 개 주세요.",
                ],
        ),
    ],
)
def test_exact_natural_requests_for_all_reviewed_items(language, expected):
    for (item_key, quantity, follow_type, follow_value, size), sentence in zip(
        ORDER_CASES, expected, strict=True
    ):
        assert _questions(
            _payload(item_key, language, quantity, follow_type, follow_value, size=size)
        )[2].correct_text == sentence


def test_validator_rejects_answer_leak_duplicate_mismatch_and_invalid_chunks():
    payload = _payload("coffee", "es", 2, "serviceSetting", "takeAway", size="small")
    result = build_m06_result(payload)
    result.questions[-1].slot_template = "Sí, eso es ___"
    with pytest.raises(LearningTaskGenerationError, match="must not reveal"):
        validate_m06_lesson(payload, result)

    payload = _payload(
        "coffee",
        "es",
        2,
        "serviceSetting",
        "takeAway",
        size="small",
        mismatch={
            "flag": True,
            "field": "quantity",
            "servedValue": 3,
            "correctedValue": 2,
            "fields": ["quantity", "size"],
        },
    )
    with pytest.raises(LearningTaskGenerationError, match="one mismatch"):
        validate_m06_lesson(payload, build_m06_result(payload))

    payload = _payload("coffee", "es", 2, "size", "small", size="small")
    with pytest.raises(LearningTaskGenerationError, match="missing detail"):
        validate_m06_lesson(payload, build_m06_result(payload))

    payload = _payload("coffee", "ko", 2, "serviceSetting", "takeAway", size="small")
    result = build_m06_result(payload)
    result.questions[2].correct_chunks = [
        "작은 커피 두 잔",
        *result.questions[2].correct_chunks[2:],
    ]
    with pytest.raises(LearningTaskGenerationError, match="separate"):
        validate_m06_lesson(payload, result)
