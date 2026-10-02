"""Deterministic plans and server-only evaluation, without a vision provider."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from app.repositories.postgres.workflow import evaluate
from app.repositories.practice import PracticeConflictError
from app.schemas.enums import TaskKind
from app.schemas.media import MediaAsset
from app.schemas.sessions import Session
from app.schemas.tasks import SessionTaskPublic, SubmitTaskAttemptRequest
from app.schemas.translation import SceneTranslationResult
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation
from app.services.session_plan import UPLOAD_WORDS, build_objects, build_tasks


def make_plan(uploaded=True, language="es"):
    asset = MediaAsset(
        owner_user_id=uuid4() if uploaded else None,
        source="userUpload" if uploaded else "preloaded",
        media_type="image",
        storage_key="test.jpg",
        mime_type="image/jpeg",
    )
    session = Session(
        user_id=asset.owner_user_id or uuid4(),
        language_profile_id=uuid4(),
        scene_media_asset_id=asset.id,
    )

    def bootstrap(c, target, source, word, translation, part="noun", gender=None, example=None):
        item = VocabularyItem(
            language_code=target,
            lemma=word,
            display_text=word,
            part_of_speech=part,
            example_sentence=example,
        )
        return item, VocabularyTranslation(
            vocabulary_item_id=item.id, source_language_code=source, translated_text=translation
        )

    scene = (
        None
        if uploaded
        else {
            "content": {
                "items": [
                    dict(
                        id="one",
                        word="puerta",
                        translation="door",
                        wordClass="noun",
                        x=99,
                        y=99,
                        example="La puerta es azul.",
                    )
                ]
            }
        }
    )
    with patch("app.services.session_plan.bootstrap_word", side_effect=bootstrap):
        objects, words, translations = build_objects(
            MagicMock(),
            session,
            asset,
            {"target_language_code": language, "source_language_code": "en"},
            scene,
        )
    return objects, build_tasks(session.id, objects, words, translations, uploaded)


@pytest.mark.parametrize("uploaded", [False, True])
def test_every_task_kind_is_persistable_skippable_and_private(uploaded):
    objects, tasks = make_plan(uploaded)
    # Grammar lessons come from the learning-task generator, not the deterministic plan.
    expected = set(TaskKind) - {TaskKind.GRAMMAR_LESSON}
    assert {t.kind for t in tasks} == expected
    assert len(tasks) == len(expected)
    assert all(o.vocabulary_item_id for o in objects)
    assert all(
        t.is_skippable
        and (t.scene_object_id is None or t.scene_object_id in {o.id for o in objects})
        for t in tasks
    )
    for task in tasks:
        public = SessionTaskPublic.from_internal(task).model_dump(mode="json")
        assert "answerKey" not in public
        assert "acceptedTextAnswers" not in str(public)


@pytest.mark.parametrize("language", list(UPLOAD_WORDS))
def test_upload_placeholders_cover_supported_languages(language):
    objects, tasks = make_plan(language=language)
    assert len(objects) == 3
    assert all("?" not in o.label for o in objects)
    assert [word.target_text for word in tasks[0].public_content.words] == [
        entry[0] for entry in UPLOAD_WORDS[language]
    ]


def test_vocabulary_lesson_includes_translated_attributes_and_relationships():
    objects, tasks = make_plan()
    _, base_tasks = make_plan()
    # Reuse the deterministic plan inputs while adding translated scene descriptors.
    vocabulary_task = base_tasks[0]
    assert all(word.term_type == "object" for word in vocabulary_task.public_content.words)
    translated_scene = SceneTranslationResult(
        objects=[
            {
                "key": str(objects[0].id),
                "source": "chair",
                "translation": "silla",
                "article": "la",
                "gender": "feminine",
            }
        ],
        attributes=[{"key": "object-1:color", "source": "blue", "translation": "azul"}],
        relationships=[{"key": "relation-1", "source": "nextTo", "translation": "al lado de"}],
    )
    # The helper data can be read from the already-created object task.
    words = []
    translations = []
    for learning_word in vocabulary_task.public_content.words:
        words.append(
            VocabularyItem(
                id=learning_word.vocabulary_item_id,
                language_code="es",
                lemma=learning_word.target_text,
                display_text=learning_word.target_text,
                part_of_speech=learning_word.part_of_speech,
            )
        )
        translations.append(
            VocabularyTranslation(
                vocabulary_item_id=learning_word.vocabulary_item_id,
                source_language_code="en",
                translated_text=learning_word.translation,
            )
        )
    enriched = build_tasks(
        vocabulary_task.session_id,
        objects,
        words,
        translations,
        True,
        translated_scene,
    )[0].public_content
    assert enriched.words[0].target_text == "la silla"
    descriptors = [
        (word.target_text, word.translation, word.term_type)
        for word in enriched.words[-2:]
    ]
    assert descriptors == [
        ("azul", "blue", "attribute"),
        ("al lado de", "next to", "relationship"),
    ]


def attempt(data):
    return TypeAdapter(SubmitTaskAttemptRequest).validate_python(data)


def test_evaluation_uses_private_keys_and_checks_modes():
    objects, tasks = make_plan()
    vocabulary = tasks[0]
    answers = vocabulary.answer_key.correct_option_ids
    assert evaluate(
        vocabulary,
        attempt({"inputMode": "vocabularyReview", "answers": answers}),
    )
    wrong = answers | {next(iter(answers)): "wrong"}
    with pytest.raises(PracticeConflictError):
        evaluate(vocabulary, attempt({"inputMode": "vocabularyReview", "answers": wrong}))
    with pytest.raises(PracticeConflictError):
        evaluate(tasks[0], attempt({"inputMode": "text", "text": "mesa"}))
    with pytest.raises(PracticeConflictError):
        evaluate(tasks[5], attempt({"inputMode": "objectSelection", "sceneObjectId": str(uuid4())}))
    assert evaluate(
        tasks[5], attempt({"inputMode": "objectSelection", "sceneObjectId": str(objects[1].id)})
    )
    assert evaluate(tasks[6], attempt({"inputMode": "text", "text": "I practised today."})) is None
    with pytest.raises(PracticeConflictError):
        evaluate(vocabulary, attempt({"inputMode": "multipleChoice", "optionId": "mesa"}))
