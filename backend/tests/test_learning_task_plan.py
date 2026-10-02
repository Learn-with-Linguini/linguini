from uuid import uuid4

from app.ai.features.translation.schemas import TranslatedTerm
from app.schemas.ispy_clues import ISpyClueResult
from app.schemas.learning_tasks import LearningTaskResult
from app.schemas.media import SceneObject
from app.schemas.tasks import SessionTaskPublic
from app.schemas.vocabulary import VocabularyItem
from app.services.session_plan import (
    _with_article,
    build_grammar_lessons,
    build_ispy_clue_tasks,
    build_ispy_description_tasks,
)
from tests.test_learning_task_service import tasks


def test_generated_lessons_become_private_grammar_lesson_tasks():
    session_id = uuid4()
    result = LearningTaskResult.model_validate(tasks())

    lessons = build_grammar_lessons(session_id, result)

    assert [task.kind for task in lessons] == ["grammarLesson"] * 4
    assert [task.public_content.focus for task in lessons] == [
        "genderNumberAgreement",
        "pluralNounForm",
        "sceneDescription",
        "chainedDescription",
    ]
    assert all(task.phase == "learning" for task in lessons)
    assert [task.id for task in build_grammar_lessons(session_id, result)] == [
        task.id for task in lessons
    ]
    scene = lessons[2]
    assert scene.public_content.questions[0].translation == "The cup is red."
    assert scene.answer_key.correct_option_ids == {"scene-1": "scene-1-a", "scene-2": "scene-2-a"}
    public = SessionTaskPublic.from_internal(scene).model_dump(mode="json")
    assert "answerKey" not in public and "correctOptionIds" not in str(public)


def test_generated_ispy_clues_keep_the_answer_key_private():
    session_id = uuid4()
    words = [
        VocabularyItem(language_code="es", lemma=text, display_text=text, part_of_speech="noun")
        for text in ["taza", "mesa"]
    ]
    objects = [
        SceneObject(session_id=session_id, label=label, vocabulary_item_id=word.id)
        for label, word in zip(["cup", "table"], words, strict=True)
    ]
    result = ISpyClueResult.model_validate({"clues": [{
        "clue": "es roja y está a la izquierda",
        "answerObjectKey": str(objects[0].id),
        "objectKeys": [str(objects[0].id)],
        "relationshipKeys": [],
    }]})

    tasks = build_ispy_clue_tasks(session_id, result, objects, words)

    assert tasks[0].public_content.clue == "es roja y está a la izquierda"
    assert tasks[0].answer_key.correct_scene_object_id == objects[0].id
    public = SessionTaskPublic.from_internal(tasks[0]).model_dump(mode="json")
    assert "answerKey" not in public
    assert len(public["publicContent"]["options"]) == 2


def test_ispy_clue_without_a_generated_translation_falls_back_to_the_clue():
    session_id = uuid4()
    words = [
        VocabularyItem(language_code="es", lemma=text, display_text=text, part_of_speech="noun")
        for text in ["taza", "mesa"]
    ]
    objects = [
        SceneObject(session_id=session_id, label=label, vocabulary_item_id=word.id)
        for label, word in zip(["cup", "table"], words, strict=True)
    ]
    result = ISpyClueResult.model_validate({"clues": [
        {
            "clue": "es roja y está a la izquierda",
            "clueTranslation": "is red and on the left",
            "answerObjectKey": str(objects[0].id),
            "objectKeys": [str(objects[0].id)],
            "relationshipKeys": [],
        },
        {
            "clue": "está debajo de algo rojo",
            "answerObjectKey": str(objects[1].id),
            "objectKeys": [str(objects[1].id)],
            "relationshipKeys": [],
        },
    ]})

    tasks = build_ispy_clue_tasks(session_id, result, objects, words)

    assert tasks[0].public_content.clue_translation == "is red and on the left"
    assert tasks[1].public_content.clue_translation == "está debajo de algo rojo"


def test_backend_selects_two_ispy_description_targets_without_storing_one_in_context():
    session_id = uuid4()
    words = [
        VocabularyItem(language_code="fr", lemma=text, display_text=text, part_of_speech="noun")
        for text in ["tasse", "table", "livre"]
    ]
    objects = [
        SceneObject(session_id=session_id, label=label, vocabulary_item_id=word.id)
        for label, word in zip(["cup", "table", "book"], words, strict=True)
    ]
    context = {"targetLanguage": "fr", "sceneObjects": {"objects": []}}

    tasks = build_ispy_description_tasks(session_id, objects, words, context)

    assert [task.scene_object_id for task in tasks] == [objects[0].id, objects[1].id]
    assert all(task.phase == "ispy" for task in tasks)
    assert all(task.answer_key.scene_description_context == context for task in tasks)
    assert "selectedTargetObjectKey" not in str(tasks[0].answer_key.scene_description_context)


def test_with_article_does_not_double_an_article_bearing_display_text():
    term = TranslatedTerm(key="o1", source="road", translation="camino", article="el")

    # Legacy rows already store the article inside display_text.
    assert _with_article("el camino", term) == "el camino"
    assert _with_article("El camino", term) == "El camino"
    # Article-free text still gets the article prepended once.
    assert _with_article("camino", term) == "el camino"
    # A noun that merely starts with the same letters is untouched here —
    # "el camino" and "elche" only collapse on a real word boundary.
    assert _with_article("elche", term) == "el elche"


def test_with_article_handles_apostrophe_articles():
    term = TranslatedTerm(key="o1", source="tree", translation="arbre", article="l'")

    assert _with_article("l'arbre", term) == "l'arbre"
    assert _with_article("l’arbre", term) == "l’arbre"
    assert _with_article("arbre", term) == "l'arbre"
