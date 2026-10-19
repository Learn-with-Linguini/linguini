from uuid import uuid4

from app.schemas.media import SceneObject
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation
from app.services.session_plan import build_tasks


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
