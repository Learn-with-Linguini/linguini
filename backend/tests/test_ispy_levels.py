"""I-Spy adapts its clues, answer choices, help and judging to the learner's level."""

from uuid import uuid4

import pytest

from app.ai.features.ispy_clues.validation import ISpyClueGenerationError, validate_ispy_clues
from app.ai.features.ispy_guess import ISpyGuessResult
from app.schemas.enums import SessionMode
from app.schemas.ispy_clues import ISpyClueResult
from app.schemas.media import SceneObject
from app.schemas.tasks import SessionTaskPublic
from app.schemas.vocabulary import VocabularyItem
from app.services.ispy_descriptions import MORE_DETAIL_MESSAGE, guess_feedback, interpret_guess
from app.services.ispy_levels import ispy_level
from app.services.session_plan import build_ispy_clue_tasks, build_ispy_description_tasks

SESSION = uuid4()


def _scene(names, labels, language="fr"):
    words = [
        VocabularyItem(language_code=language, lemma=text, display_text=text, part_of_speech="noun")
        for text in names
    ]
    objects = [
        SceneObject(session_id=SESSION, label=label, vocabulary_item_id=word.id)
        for label, word in zip(labels, words, strict=True)
    ]
    return objects, words


def _clue(target, text="est rouge"):
    return ISpyClueResult.model_validate({"clues": [{
        "clue": text, "clueTranslation": "is red", "answerObjectKey": str(target.id),
        "objectKeys": [str(target.id)], "relationshipKeys": [],
    }]})


def test_unknown_levels_play_the_a1_game():
    assert ispy_level(None).level == "A1"
    assert ispy_level("b2").level == "A1"
    assert ispy_level("a0").level == "A0"


def test_a0_clues_offer_three_differently_named_choices_with_translation_and_help():
    objects, words = _scene(
        ["tasse", "tasse", "table", "livre", "chaise"], ["cup", "cup", "table", "book", "chair"],
    )
    [task] = build_ispy_clue_tasks(
        SESSION, _clue(objects[3]), objects, words, level="A0", language="fr",
    )
    content = task.public_content
    labels = [option.label for option in content.options]
    assert len(labels) == 3 and "livre" in labels and len(set(labels)) == 3
    assert task.answer_key.correct_option_id in {option.option_id for option in content.options}
    assert content.translation_shown and not content.listen_first
    assert content.learner_level == "A0"
    assert [entry.text for entry in content.word_bank] == ["tasse", "table", "livre", "chaise"]
    assert content.word_bank[0].translation == "cup"
    assert content.cheat_sheet.model_dump(mode="json") == {
        "missionId": "M02", "practiceLevel": "A0", "contentVersion": 2,
    }
    public = SessionTaskPublic.from_internal(
        task, mode=SessionMode.ISPY
    ).model_dump(mode="json")
    assert public["publicContent"]["cheatSheet"]["missionId"] == "M02"


def test_a1_keeps_every_choice_and_no_extra_help():
    objects, words = _scene(
        ["tasse", "table", "livre", "chaise"], ["cup", "table", "book", "chair"],
    )
    [task] = build_ispy_clue_tasks(SESSION, _clue(objects[0]), objects, words, level="A1",
                                   language="fr")
    content = task.public_content
    assert len(content.options) == 4
    assert not content.translation_shown and not content.listen_first
    assert content.word_bank == [] and content.cheat_sheet is None
    public = SessionTaskPublic.from_internal(
        task, mode=SessionMode.ISPY
    ).model_dump(mode="json")
    assert "wordBank" not in public["publicContent"] and "cheatSheet" not in public["publicContent"]


def test_a2_clues_are_heard_before_they_are_read():
    objects, words = _scene(["tasse", "table"], ["cup", "table"])
    [task] = build_ispy_clue_tasks(SESSION, _clue(objects[0]), objects, words, level="A2")
    assert task.public_content.listen_first and not task.public_content.translation_shown


def test_a0_cheatsheet_is_only_offered_when_the_language_has_it():
    objects, words = _scene(["tasse", "table"], ["cup", "table"])
    [task] = build_ispy_clue_tasks(SESSION, _clue(objects[0]), objects, words, level="A0",
                                   language="it")
    assert task.public_content.cheat_sheet is None


def _description_scene():
    objects, words = _scene(["tasse", "table", "livre"], ["cup", "table", "book"])
    cup, table, book = (str(obj.id) for obj in objects)
    context = {"targetLanguage": "fr", "sceneObjects": {
        "objects": [
            {"key": cup, "source": "cup", "translation": "tasse", "gender": "feminine"},
            {"key": table, "source": "table", "translation": "table", "gender": "feminine"},
            {"key": book, "source": "book", "translation": "livre", "gender": "masculine"},
        ],
        "attributes": [
            {"key": f"{book}:color", "source": "white", "translation": "blanc", "objectKey": book},
            {"key": f"{cup}:color", "source": "red", "translation": "rouge", "objectKey": cup},
        ],
        "relations": [
            {"key": "r1", "source": "on", "translation": "sur",
             "subjectObjectKey": cup, "referenceObjectKey": table},
        ],
    }}
    return objects, words, context


def test_a0_describes_one_object_by_building_from_tiles():
    objects, words, context = _description_scene()
    tasks = build_ispy_description_tasks(SESSION, objects, words, context, level="A0")
    assert len(tasks) == 1
    content = tasks[0].public_content
    assert content.allow_text is False and not content.help_collapsed
    assert content.clue_frames and all(frame.help for frame in content.clue_frames)
    assert "word tiles" in content.prompt
    assert content.word_bank and content.cheat_sheet is not None
    assert tasks[0].answer_key.learner_level == "A0"


def test_a1_and_a2_describe_two_objects_by_typing():
    objects, words, context = _description_scene()
    a1 = build_ispy_description_tasks(SESSION, objects, words, context, level="A1")
    a2 = build_ispy_description_tasks(SESSION, objects, words, context, level="A2")
    assert len(a1) == len(a2) == 2
    assert all(task.public_content.allow_text for task in [*a1, *a2])
    assert not any(task.public_content.help_collapsed for task in a1)
    assert all(task.public_content.help_collapsed for task in a2)
    assert {task.answer_key.learner_level for task in a2} == {"A2"}


def _payload(level, target):
    payload = {"objects": [{"key": str(target.id), "source": "cup", "translation": "tasse"}],
               "relationships": []}
    if level:
        payload["learnerLevel"] = level
    return payload


def test_a0_clues_stay_short():
    objects, _words = _scene(["tasse"], ["cup"])
    validate_ispy_clues(_payload("A0", objects[0]), _clue(objects[0], "est sur la table"))
    long_clue = _clue(objects[0], "est rouge et elle est sur la table à gauche")
    with pytest.raises(ISpyClueGenerationError, match="6 words"):
        validate_ispy_clues(_payload("A0", objects[0]), long_clue)
    validate_ispy_clues(_payload(None, objects[0]), long_clue)


def _guess(target, matched, *, ambiguous=False):
    return ISpyGuessResult(
        guessed_object_key=target, ambiguous=ambiguous, matched_evidence_keys=matched,
        feedback="Great clue!",
    )


def test_a0_accepts_the_right_object_even_when_the_detail_is_shared():
    objects, _words, context = _description_scene()
    cup = objects[0]
    guess = _guess(str(cup.id), [f"{cup.id}:color"], ambiguous=True)
    assert interpret_guess(guess, cup.id, level="A0", context=context).outcome == "clearMatch"
    assert interpret_guess(guess, cup.id, level="A1", context=context).outcome == (
        "needsClarification"
    )


def test_a2_needs_two_matching_details_when_the_object_has_them():
    objects, _words, context = _description_scene()
    cup, _table, book = objects
    one = _guess(str(cup.id), [f"{cup.id}:color"])
    judged = interpret_guess(one, cup.id, level="A2", context=context)
    assert judged.outcome == "needsClarification"
    assert guess_feedback(one, judged, cup.id) == MORE_DETAIL_MESSAGE
    assert interpret_guess(one, cup.id, level="A1", context=context).outcome == "clearMatch"
    two = _guess(str(cup.id), [f"{cup.id}:color", "r1"])
    assert interpret_guess(two, cup.id, level="A2", context=context).outcome == "clearMatch"
    # The book has a single confirmed detail, so one is all A2 can ask for.
    only = _guess(str(book.id), [f"{book.id}:color"])
    judged = interpret_guess(only, book.id, level="A2", context=context)
    assert judged.outcome == "clearMatch"
    assert guess_feedback(only, judged, book.id) == "Great clue!"
