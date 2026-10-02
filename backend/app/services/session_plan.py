"""Deterministic placeholder plans. No image recognition or AI generation."""

import re
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.repositories.postgres.vocabulary import vocabulary_items, vocabulary_translations
from app.repositories.practice import PracticeConflictError
from app.schemas.ispy_clues import ISpyClueResult
from app.schemas.media import SceneObject
from app.schemas.tasks import SessionTask
from app.schemas.vocabulary import VocabularyItem, VocabularyTranslation
from app.services.image_analysis import PlaceholderImageExtractor

# Fixed, deliberately small upload vocabulary. Unknown languages fail explicitly.
UPLOAD_WORDS = {
    "es": [("silla", "chair"), ("mesa", "table"), ("planta", "plant")],
    "fr": [("chaise", "chair"), ("table", "table"), ("plante", "plant")],
    "it": [("sedia", "chair"), ("tavolo", "table"), ("pianta", "plant")],
    "de": [("Stuhl", "chair"), ("Tisch", "table"), ("Pflanze", "plant")],
    "ko": [("\uc758\uc790", "chair"), ("\ud14c\uc774\ube14", "table"), ("\uc2dd\ubb3c", "plant")],
    "ja": [
        ("\u6905\u5b50", "chair"),
        ("\u30c6\u30fc\u30d6\u30eb", "table"),
        ("\u690d\u7269", "plant"),
    ],
    "en": [("chair", "chair"), ("table", "table"), ("plant", "plant")],
}


def bootstrap_word(
    connection, language, source_language, word, translation, part="noun", gender=None,
    example=None, phonetic_text=None,
):
    """Reuse catalog records; deterministic IDs make concurrent bootstrap safe."""
    row = (
        connection.execute(
            select(vocabulary_items)
            .where(
                func.lower(vocabulary_items.c.language_code) == language.lower(),
                func.lower(vocabulary_items.c.lemma) == word.lower(),
                vocabulary_items.c.part_of_speech == part,
            )
            .order_by(vocabulary_items.c.created_at, vocabulary_items.c.id)
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row:
        item = VocabularyItem.model_validate(dict(row))
        if phonetic_text and not item.phonetic_text:
            connection.execute(
                update(vocabulary_items).where(vocabulary_items.c.id == item.id)
                .values(phonetic_text=phonetic_text)
            )
            item = item.model_copy(update={"phonetic_text": phonetic_text})
    else:
        item = VocabularyItem(
            id=uuid5(
                NAMESPACE_URL, f"linguini:vocabulary:{language.lower()}:{part}:{word.lower()}"
            ),
            language_code=language,
            lemma=word,
            display_text=word,
            part_of_speech=part,
            gender=gender,
            example_sentence=example,
            phonetic_text=phonetic_text,
        )
        connection.execute(
            insert(vocabulary_items)
            .values(**item.model_dump(by_alias=False))
            .on_conflict_do_nothing(index_elements=["id"])
        )
        item = VocabularyItem.model_validate(
            dict(
                connection.execute(select(vocabulary_items).where(vocabulary_items.c.id == item.id))
                .mappings()
                .one()
            )
        )
    translated = VocabularyTranslation(
        id=uuid5(item.id, source_language.lower()),
        vocabulary_item_id=item.id,
        source_language_code=source_language,
        translated_text=translation,
    )
    connection.execute(
        insert(vocabulary_translations)
        .values(**translated.model_dump(by_alias=False))
        .on_conflict_do_nothing()
    )
    translated = VocabularyTranslation.model_validate(
        dict(
            connection.execute(
                select(vocabulary_translations).where(
                    vocabulary_translations.c.vocabulary_item_id == item.id,
                    func.lower(vocabulary_translations.c.source_language_code)
                    == source_language.lower(),
                )
            )
            .mappings()
            .one()
        )
    )
    return item, translated


def build_objects(connection, session, asset, profile, scene):
    objects, words, translations = [], [], []
    if profile["source_language_code"].lower() != "en":
        raise PracticeConflictError(
            "Placeholder plans currently support English as the source language."
        )
    if scene:
        entries = scene["content"]["items"]
        for entry in entries:
            word, translated = bootstrap_word(
                connection,
                profile["target_language_code"],
                profile["source_language_code"],
                entry["word"],
                entry["translation"],
                entry.get("wordClass", entry.get("word_class", "noun")),
                entry.get("gender"),
                entry.get("example"),
            )
            obj = SceneObject(
                id=uuid5(session.id, "curated:" + entry["id"]),
                session_id=session.id,
                label=entry["translation"],
                vocabulary_item_id=word.id,
                bounding_box={
                    "x": min(float(entry["x"]) / 100, 0.95),
                    "y": min(float(entry["y"]) / 100, 0.95),
                    "width": 0.05,
                    "height": 0.05,
                },
                anchor_point={"x": float(entry["x"]) / 100, "y": float(entry["y"]) / 100},
                attributes=entry.get("attributes") or None,
            )
            objects.append(obj)
            words.append(word)
            translations.append(translated)
    else:
        language = profile["target_language_code"].lower()
        if language not in UPLOAD_WORDS:
            raise PracticeConflictError("Placeholder uploads are not configured for this language.")
        for obj, (text, translation) in zip(
            PlaceholderImageExtractor().extract(asset, session.id),
            UPLOAD_WORDS[language],
            strict=True,
        ):
            word, translated = bootstrap_word(
                connection,
                language,
                profile["source_language_code"],
                text,
                translation,
                example=text,
            )

            obj.vocabulary_item_id = word.id
            objects.append(obj)
            words.append(word)
            translations.append(translated)
    return objects, words, translations


def _display_source(value):
    """Turn relationship keys such as nextTo/next_to into learner-facing English."""
    result = []
    for character in value.replace("_", " "):
        if character.isupper() and result and result[-1] != " ":
            result.append(" ")
        result.append(character.lower())
    return "".join(result)


def _with_article(text, translated_term):
    if not translated_term or not translated_term.article:
        return text
    article = translated_term.article
    separator = "" if article.endswith(("'", "’")) else " "
    # Legacy rows may already carry the article inside display_text; adding it
    # again produced doubled articles such as "el el camino".
    already_present = (
        re.match(rf"{re.escape(article)}\s", text, re.IGNORECASE)
        if separator
        else re.match(rf"{re.escape(article[:-1])}['’]", text, re.IGNORECASE)
    )
    if already_present:
        return text
    return f"{article}{separator}{text}"


def build_grammar_lessons(session_id, result):
    """Turn generated grammar lessons into tasks; the caller assigns their order."""
    return [
        SessionTask(
            id=uuid5(session_id, "learning-tasks-v1:" + lesson.focus),
            session_id=session_id,
            phase="learning",
            kind="grammarLesson",
            order_index=0,
            public_content=dict(
                kind="grammarLesson",
                focus=lesson.focus,
                title=lesson.title,
                explanation=lesson.explanation,
                questions=[
                    dict(
                        question_id=question.question_id,
                        prompt=question.prompt,
                        interaction_type=question.interaction_type,
                        options=[
                            dict(option_id=option.option_id, label=option.label)
                            for option in question.options
                        ],
                        token_bank=question.token_bank,
                        translation=question.translation,
                    )
                    for question in lesson.questions
                ],
            ),
            answer_key=dict(
                correct_option_ids={
                    question.question_id: question.correct_option_id or question.correct_text
                    for question in lesson.questions
                }
            ),
        )
        for lesson in result.tasks
    ]


def build_ispy_clue_tasks(session_id, result: ISpyClueResult, objects, words):
    """Make provider-selected Phase 1 clue rounds using server-side answer keys."""
    by_key = {str(obj.id): (obj, word) for obj, word in zip(objects, words, strict=True)}
    options = [
        dict(option_id=str(obj.id), label=word.display_text, scene_object_id=obj.id)
        for obj, word in zip(objects, words, strict=True)
    ]
    return [
        SessionTask(
            id=uuid5(session_id, f"ispy-clues-v1:{clue.answer_object_key}"),
            session_id=session_id,
            phase="ispy",
            kind="ispyRound",
            order_index=0,
            public_content=dict(
                kind="ispyRound",
                clue=clue.clue,
                # Falls back to the clue itself so the reveal control always
                # has something to show.
                clue_translation=clue.clue_translation.strip() or clue.clue,
                interaction_mode="selectObject",
                options=options,
                encouragement="Keep looking closely!",
                hint_available=False,
            ),
            answer_key=dict(
                correct_scene_object_id=by_key[clue.answer_object_key][0].id,
                correct_option_id=str(by_key[clue.answer_object_key][0].id),
            ),
            vocabulary_item_id=by_key[clue.answer_object_key][1].id,
            scene_object_id=by_key[clue.answer_object_key][0].id,
        )
        for clue in result.clues
    ]


def build_ispy_description_tasks(session_id, objects, words, description_context):
    """Choose up to two targets in code; the guess model never sees these IDs."""
    return [
        SessionTask(
            id=uuid5(session_id, f"ispy-descriptions-v1:{obj.id}"),
            session_id=session_id,
            phase="ispy",
            kind="reflection",
            order_index=0,
            public_content=dict(
                kind="reflection",
                prompt=(
                    "Describe this object in your learning language. "
                    "Use any words below that help."
                ),
                suggested_vocabulary_ids=[word.id for word in words],
                allow_speech=False,
                allow_text=True,
            ),
            answer_key=dict(scene_description_context=description_context),
            vocabulary_item_id=word.id,
            scene_object_id=obj.id,
        )
        for obj, word in list(zip(objects, words, strict=True))[:2]
    ]


def build_tasks(session_id, objects, words, translations, uploaded, translated_scene=None):
    # Two sets choose different focus objects and context, with the same public contract.
    index = min(1, len(words) - 1) if uploaded else 0
    word, translation, obj = words[index], translations[index], objects[index]
    focus = word.display_text
    context = "photo sample" if uploaded else "ready scene"
    example = word.example_sentence or focus
    related = [item.id for item in words]
    translated_objects = (
        {term.key: term for term in translated_scene.objects} if translated_scene else {}
    )
    learning_words = [
        dict(
            learning_key=str(item.id),
            term_type="object",
            vocabulary_item_id=item.id,
            scene_object_id=scene_object.id,
            target_text=_with_article(
                item.display_text, translated_objects.get(str(scene_object.id))
            ),
            translation=translated.translated_text,
            part_of_speech=item.part_of_speech,
            gender=item.gender,
            phonetic_text=item.phonetic_text,
            example_sentence=item.example_sentence,
        )
        for scene_object, item, translated in zip(objects, words, translations, strict=True)
    ]
    if translated_scene:
        supplemental_terms = [
            (term, "attribute", "adjective") for term in translated_scene.attributes
        ] + [
            (term, "relationship", "preposition")
            for term in translated_scene.relationships
        ]
        seen_terms = {
            (entry["target_text"].casefold(), entry["translation"].casefold())
            for entry in learning_words
        }
        for term, term_type, part_of_speech in supplemental_terms:
            identity = (term.translation.casefold(), term.source.casefold())
            if identity in seen_terms:
                continue
            seen_terms.add(identity)
            learning_words.append(
                dict(
                    learning_key=f"{term_type}:{term.key}",
                    term_type=term_type,
                    target_text=term.translation,
                    translation=_display_source(term.source),
                    part_of_speech=part_of_speech,
                    phonetic_text=term.phonetic_text,
                )
            )
    questions = []
    correct_option_ids = {}
    for question_index, learning_word in enumerate(learning_words):
        ordered = [
            learning_word,
            *learning_words[question_index + 1 :],
            *learning_words[:question_index],
        ]
        choices = list(dict.fromkeys(candidate["target_text"] for candidate in ordered))[:4]
        fallback_choices = {
            "es": ["No sé", "No estoy seguro"],
            "fr": ["Je ne sais pas", "Je ne suis pas sûr"],
        }.get(words[0].language_code.lower(), ["I'm not sure", "Something else"])
        for choice in fallback_choices:
            if len(choices) >= 4:
                break
            if choice not in choices:
                choices.append(choice)
        question_id = f"word-{learning_word['learning_key']}"
        questions.append(
            dict(
                question_id=question_id,
                prompt=f'Which word means "{learning_word["translation"]}"?',
                options=[dict(option_id=choice, label=choice) for choice in choices],
                correct_option_id=learning_word["target_text"],
            )
        )
        correct_option_ids[question_id] = learning_word["target_text"]
    contents = [
        dict(
            kind="vocabularyIntroduction",
            title="Learn the words in this scene",
            words=learning_words,
            questions=questions,
            allow_typing_practice=True,
        ),
        dict(
            kind="grammarExplanation",
            title="Words in context",
            explanation=f"This word is a {word.part_of_speech.value}. Read the sample below.",
            examples=[example],
            related_vocabulary_ids=related,
        ),
        dict(
            kind="grammarPractice",
            prompt=f'Which word means "{translation.translated_text}"?',
            options=list(dict.fromkeys([words[(index + 1) % len(words)].display_text, focus])),
            related_vocabulary_ids=related,
        ),
        dict(
            kind="syntaxExplanation",
            title="A sample expression",
            sentence_pattern=example,
            explanation="Read the expression, then practise putting its tokens in order.",
            examples=[example],
            related_vocabulary_ids=related,
        ),
        dict(
            kind="sentenceBuilding",
            prompt="Rebuild the sample expression.",
            source_text=example,
            token_bank=list(reversed(example.split())),
            related_vocabulary_ids=related,
            allow_speech=False,
        ),
        dict(
            kind="ispyRound",
            clue=f"Find: {translation.translated_text}",
            clue_translation=f"Find: {word.display_text}",
            interaction_mode="selectObject",
            options=[
                dict(option_id=str(o.id), label=w.display_text, scene_object_id=o.id)
                for o, w in zip(objects, words, strict=True)
            ],
            encouragement="Keep practising!",
            hint_available=False,
        ),
        dict(
            kind="reflection",
            prompt=(
                f"Write a short reflection about your {context}. "
                "This sample task records participation."
            ),
            suggested_vocabulary_ids=related,
            allow_speech=False,
        ),
    ]
    keys = [
        dict(
            correct_option_ids=correct_option_ids,
            accepted_text_answers_by_vocabulary_id={
                entry["learning_key"]: [entry["target_text"]] for entry in learning_words
            },
        ),
        None,
        dict(accepted_text_answers=[focus], correct_option_id=focus),
        None,
        dict(accepted_text_answers=[example], expected_token_order=example.split()),
        dict(
            correct_scene_object_id=obj.id,
            correct_option_id=str(obj.id),
            accepted_text_answers=[focus],
        ),
        None,
    ]
    return [
        SessionTask(
            id=uuid5(session_id, "placeholder-v1:" + content["kind"]),
            session_id=session_id,
            phase="ispy" if content["kind"] == "ispyRound" else "learning",
            kind=content["kind"],
            order_index=i,
            public_content=content,
            answer_key=key,
            vocabulary_item_id=None if content["kind"] == "vocabularyIntroduction" else word.id,
            scene_object_id=None if content["kind"] == "vocabularyIntroduction" else obj.id,
        )
        for i, (content, key) in enumerate(zip(contents, keys, strict=True))
    ]
