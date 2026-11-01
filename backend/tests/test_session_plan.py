from uuid import uuid4

import pytest

from app.ai.features.translation.schemas import SceneTranslationResult
from app.schemas.media import SceneObject
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation
from app.services.session_plan import build_tasks, strip_english_article


def test_strip_english_article_collapses_whitespace_and_removes_one_prefix():
    assert strip_english_article("  THE   pillow  ") == "pillow"
    assert strip_english_article("an Apple") == "Apple"
    assert strip_english_article("a") == "a"


def test_build_tasks_introduces_one_entry_per_vocabulary_item():
    session_id = uuid4()
    chair = VocabularyItem(
        language_code="es",
        lemma="silla",
        display_text="silla",
        part_of_speech="noun",
    )
    table = VocabularyItem(
        language_code="es",
        lemma="mesa",
        display_text="mesa",
        part_of_speech="noun",
    )
    chair_objects = [
        SceneObject(
            session_id=session_id,
            label="chair",
            vocabulary_item_id=chair.id,
        )
        for _ in range(3)
    ]
    table_object = SceneObject(
        session_id=session_id,
        label="table",
        vocabulary_item_id=table.id,
    )
    objects = [*chair_objects, table_object]
    words = [chair, chair, chair, table]
    translations = [
        VocabularyTranslation(
            vocabulary_item_id=chair.id,
            source_language_code="en",
            translated_text="chair",
        )
        for _ in range(3)
    ] + [
        VocabularyTranslation(
            vocabulary_item_id=table.id,
            source_language_code="en",
            translated_text="table",
        )
    ]

    introduction = next(
        task
        for task in build_tasks(session_id, objects, words, translations, uploaded=False)
        if task.kind == "vocabularyIntroduction"
    )

    chair_entries = [
        word
        for word in introduction.public_content.words
        if word.vocabulary_item_id == chair.id
    ]
    assert len(chair_entries) == 1
    assert chair_entries[0].scene_object_id == chair_objects[0].id
    assert [question.question_id for question in introduction.public_content.questions] == [
        f"word-{chair.id}",
        f"word-{table.id}",
    ]


@pytest.mark.parametrize(
    ("language", "noun", "article", "expected_options"),
    [
        ("es", "silla", "la", ["el", "la"]),
        ("fr", "arbre", "l’", ["le", "la", "l'"]),
        ("de", "Tisch", "der", ["der", "die", "das"]),
    ],
)
def test_vocabulary_review_practises_articles_for_article_languages(
    language, noun, article, expected_options,
):
    session_id = uuid4()
    item = VocabularyItem(
        language_code=language, lemma=noun, display_text=noun, part_of_speech="noun"
    )
    scene_object = SceneObject(
        session_id=session_id, label="object", vocabulary_item_id=item.id
    )
    translation = VocabularyTranslation(
        vocabulary_item_id=item.id,
        source_language_code="en",
        translated_text="object",
    )
    translated_scene = SceneTranslationResult(
        objects=[{
            "key": str(scene_object.id),
            "source": "object",
            "translation": noun,
            "article": article,
        }],
        attributes=[],
        relationships=[],
    )

    introduction = build_tasks(
        session_id,
        [scene_object],
        [item],
        [translation],
        uploaded=False,
        translated_scene=translated_scene,
    )[0]

    article_question = introduction.public_content.questions[-1]
    assert article_question.question_id == f"article-{item.id}"
    assert article_question.prompt == f'Which article goes with "{noun}"?'
    assert [option.label for option in article_question.options] == expected_options
    assert article_question.correct_option_id == article.replace("’", "'")
    assert introduction.answer_key.correct_option_ids[article_question.question_id] == (
        article.replace("’", "'")
    )


def test_vocabulary_review_skips_article_questions_for_korean():
    session_id = uuid4()
    item = VocabularyItem(
        language_code="ko", lemma="의자", display_text="의자", part_of_speech="noun"
    )
    scene_object = SceneObject(
        session_id=session_id, label="chair", vocabulary_item_id=item.id
    )
    translation = VocabularyTranslation(
        vocabulary_item_id=item.id,
        source_language_code="en",
        translated_text="chair",
    )
    translated_scene = SceneTranslationResult(
        objects=[{
            "key": str(scene_object.id),
            "source": "chair",
            "translation": "의자",
        }],
        attributes=[],
        relationships=[],
    )

    introduction = build_tasks(
        session_id,
        [scene_object],
        [item],
        [translation],
        uploaded=False,
        translated_scene=translated_scene,
    )[0]

    assert [question.question_id for question in introduction.public_content.questions] == [
        f"word-{item.id}"
    ]
