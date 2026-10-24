from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.repositories.postgres import vocabulary as vocabulary_repository
from app.repositories.postgres.vocabulary import PostgresVocabularyRepository
from app.schemas.vocabulary import UserVocabularyProgress, VocabularyEncounter, VocabularyItem


def noun(language, text, *, display=None, gender=None):
    return VocabularyItem(
        language_code=language, lemma=text, display_text=display or text,
        part_of_speech="noun", gender=gender,
    )


@pytest.mark.parametrize(("language", "bare", "target"), [
    ("es", "mesa", "la mesa"), ("es", "libro", "el libro"),
    ("fr", "arbre", "l’arbre"), ("fr", "arbre", "l'arbre"),
    ("fr", "haricot", "le haricot"), ("de", "Buch", "das Buch"),
])
def test_exact_taught_article_is_displayed_without_changing_catalog(language, bare, target):
    word = noun(language, bare, gender="neuter" if language == "de" else "feminine")
    shown = vocabulary_repository._taught_noun_display(word, target)
    assert shown.display_text == target
    assert shown.lemma == bare and shown.gender == word.gender
    assert word.display_text == bare
    assert vocabulary_repository._taught_noun_display(shown, target) is shown


@pytest.mark.parametrize(("word", "target"), [
    (noun("ko", "컵"), "컵"),
    (noun("ko", "컵"), "la 컵"),
    (noun("es", "mesa", display="la mesa"), "la mesa"),
    (noun("es", "la mesa"), "la la mesa"),
    (noun("es", "mesa", display="mesita"), "la mesa"),
    (noun("fr", "arbre"), "le livre"),
    (noun("es", "mesa"), "die mesa"),
    (noun("es", "mesa"), None),
    (noun("es", "mesa").model_copy(update={"part_of_speech": "adjective"}), "la mesa"),
])
def test_missing_or_unrelated_teaching_does_not_replace_the_word(word, target):
    assert vocabulary_repository._taught_noun_display(word, target) is word


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


def test_collection_recovers_latest_taught_article_from_this_users_encounter_tasks():
    owner, profile, session, old_task, new_task = [uuid4() for _ in range(5)]
    item = noun("fr", "arbre", gender="masculine")
    progress = UserVocabularyProgress(user_id=owner, vocabulary_item_id=item.id)
    encounters = [
        VocabularyEncounter(
            user_id=owner, vocabulary_item_id=item.id, session_id=session,
            session_task_id=task_id, encounter_type="introduced", outcome="completed",
        ).model_dump(by_alias=False)
        for task_id in (old_task, new_task)
    ]
    queries = []

    def execute(statement):
        sql = str(statement)
        if "FROM public.language_profiles" in sql:
            return Rows([{
                "id": profile, "source_language_code": "en", "target_language_code": "fr",
            }])
        if "FROM public.user_vocabulary_progress" in sql:
            return Rows([progress.model_dump(by_alias=False)])
        if "FROM public.vocabulary_items" in sql:
            return Rows([item.model_dump(by_alias=False)])
        if "FROM public.vocabulary_translations" in sql:
            return Rows([])
        if "FROM public.vocabulary_encounters" in sql:
            return Rows(encounters)
        if "FROM public.session_tasks" in sql:
            queries.append(statement)
            return Rows([
                {"id": task_id, "public_content": {"words": [{
                    "vocabularyItemId": str(item.id), "targetText": target,
                }]}}
                for task_id, target in [(old_task, "l'arbre"), (new_task, "l’arbre")]
            ])
        return Rows([])

    engine = MagicMock()
    connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
    connection.execute.side_effect = execute
    response = PostgresVocabularyRepository(engine).list_vocabulary(owner)
    assert response[0].vocabulary.display_text == "l’arbre"
    assert response[0].vocabulary.lemma == "arbre"
    assert item.display_text == "arbre"
    assert len(queries) == 1
    params = queries[0].compile().params
    assert owner in params.values() and "fr" in params.values()
    assert any(
        isinstance(value, list) and set(value) == {old_task, new_task}
        for value in params.values()
    )
