"""Guided I-Spy clue frames use confirmed facts only and never accept the target word."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.media import SceneObject
from app.schemas.tasks import (
    ClueAssistance,
    ISpyRoundContent,
    ReflectionContent,
    SubmitTextAttemptRequest,
)
from app.schemas.vocabulary import VocabularyItem
from app.services.ispy_clue_frames import build_clue_support, check_clue, mentions_target


def scene(language, nouns, *, colours=(), relations=()):
    """``nouns`` maps a name to (translation, article, gender); the first is the target."""
    session_id = uuid4()
    objects = {name: SceneObject(session_id=session_id, label=name) for name in nouns}
    context = {
        "targetLanguage": language,
        "sceneObjects": {
            "objects": [
                {"key": str(objects[name].id), "source": name, "translation": translation,
                 **({"article": article} if article else {}),
                 **({"gender": gender} if gender else {})}
                for name, (translation, article, gender) in nouns.items()
            ],
            "attributes": [
                {"key": f"{objects[name].id}:{kind}", "objectKey": str(objects[name].id),
                 "source": kind, "translation": value}
                for name, kind, value in colours
            ],
            "relations": [
                {"key": str(uuid4()), "source": relation, "translation": translation,
                 "subjectObjectKey": str(objects[subject].id),
                 "referenceObjectKey": str(objects[reference].id)}
                for subject, relation, translation, reference in relations
            ],
        },
    }
    target_name = next(iter(nouns))
    translation, _article, gender = nouns[target_name]
    word = VocabularyItem(
        language_code=language, lemma=translation, display_text=translation,
        part_of_speech="noun", gender=gender,
    )
    return context, objects[target_name], word


def frames_of(context, target, word):
    frames, avoid = build_clue_support(context, target, word)
    return {frame.frame_id: frame for frame in frames}, avoid


def test_spanish_frames_use_confirmed_facts_and_spanish_forms():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine"),
         "sofa": ("sofá", "el", "masculine")},
        colours=[("cup", "color", "roja"), ("table", "color", "marrón")],
        relations=[("cup", "on", "sobre", "table"), ("cup", "next_to", "al lado de", "sofa")],
    )

    frames, avoid = frames_of(context, target, word)

    assert [(f.prefix, f.example) for f in frames.values()] == [
        ("Veo", "Veo una taza"), ("Es", "Es roja"), ("Está", "Está sobre la mesa"),
    ]
    assert all(frame.meaning for frame in frames.values())
    assert frames["name"].chips == ["una mesa", "un sofá"]
    assert frames["colour"].chips == ["roja"]
    assert frames["location"].chips == ["sobre la mesa", "al lado del sofá"]
    assert {"taza", "tazas", "cup", "cups"} <= set(avoid)


def test_french_frames_agree_with_the_target_and_contract_articles():
    context, target, word = scene(
        "fr",
        {"cup": ("tasse", "la", "feminine"), "table": ("table", "la", "feminine"),
         "book": ("livre", "le", "masculine"), "tree": ("arbre", "l'", "masculine")},
        colours=[("cup", "color", "rouge")],
        relations=[("cup", "on", "sur", "table"), ("cup", "next_to", "à côté de", "book"),
                   ("cup", "near", "près de", "tree")],
    )

    frames, _avoid = frames_of(context, target, word)

    assert [(f.prefix, f.example) for f in frames.values()] == [
        ("Je vois", "Je vois une tasse"), ("Elle est", "Elle est rouge"),
        ("Elle est", "Elle est sur la table"),
    ]
    assert frames["name"].chips == ["une table", "un livre", "un arbre"]
    assert frames["location"].chips == ["sur la table", "à côté du livre", "près de l'arbre"]


def test_french_masculine_target_uses_il():
    context, target, word = scene(
        "fr", {"book": ("livre", "le", "masculine")}, colours=[("book", "color", "bleu")]
    )

    frames, _avoid = frames_of(context, target, word)

    assert frames["colour"].prefix == "Il est"


def test_absent_attributes_and_relations_offer_only_the_name_frame():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine")},
        colours=[("cup", "material", "cerámica"), ("table", "color", "marrón")],
        relations=[("table", "on", "sobre", "cup"), ("table", "near", "cerca de", "cup")],
    )

    frames, _avoid = frames_of(context, target, word)

    assert list(frames) == ["name", "location"]
    # Only the symmetric relation can be read from the target's side.
    assert frames["location"].chips == ["cerca de la mesa"]

    context["sceneObjects"]["relations"] = []
    frames, _avoid = frames_of(context, target, word)
    assert list(frames) == ["name"]


def test_name_chips_skip_the_target_and_nouns_without_a_known_gender():
    context, target, word = scene(
        "es", {"cup": ("taza", "la", "feminine"), "lamp": ("lámpara", None, None)}
    )

    frames, _avoid = frames_of(context, target, word)

    assert frames["name"].chips == []


def test_unsupported_languages_keep_free_typing_without_frames():
    context, target, word = scene("de", {"cup": ("Tasse", "die", "feminine")})

    assert build_clue_support(context, target, word) == ([], [])


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("Veo una TAZA", True),
        ("Son tazas rojas.", True),
        ("Es una táza", True),
        ("It is a cup", True),
        ("Es un tazón rojo", False),
        ("Es roja y está sobre la mesa", False),
    ],
)
def test_target_word_matches_whole_words_ignoring_case_and_accents(text, named):
    assert mentions_target(text, ["taza", "tazas", "cup"]) is named


def content_with_frames():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine")},
        colours=[("cup", "color", "roja")],
    )
    frames, avoid = build_clue_support(context, target, word)
    return ReflectionContent(prompt="Describe it", clue_frames=frames, avoid_words=avoid)


def attempt(text, **assistance):
    return SubmitTextAttemptRequest(
        text=text, assistance=ClueAssistance(**assistance) if assistance else None
    )


def test_check_clue_rejects_the_target_word_and_unoffered_assistance():
    content = content_with_frames()
    offered = ["name", "colour"]

    check_clue(content, attempt("Es roja", offered_frame_ids=offered,
                                selected_frame_ids=["colour"], inserted_chips=["roja"]))
    check_clue(content, attempt("Es pequeña y roja."))
    with pytest.raises(ClueNamesTargetError):
        check_clue(content, attempt("Veo una taza roja"))
    for bad in [
        dict(offered_frame_ids=["name"]),
        dict(offered_frame_ids=offered, selected_frame_ids=["location"]),
        dict(offered_frame_ids=offered, selected_frame_ids=["name"], inserted_chips=["roja"]),
    ]:
        with pytest.raises(PracticeConflictError):
            check_clue(content, attempt("Es roja", **bad))


def test_tasks_without_frame_metadata_still_validate_and_accept_free_text():
    content = ReflectionContent.model_validate({"kind": "reflection", "prompt": "Reflect"})

    assert content.clue_frames == [] and content.avoid_words == []
    check_clue(content, attempt("Veo una taza"))
    with pytest.raises(PracticeConflictError):
        check_clue(
            ISpyRoundContent(clue="c", interaction_mode="typeAnswer"),
            attempt("x", offered_frame_ids=[]),
        )


def test_reflection_content_rejects_repeated_frames():
    frame = {"frameId": "name", "prefix": "Veo", "meaning": "I see", "example": "Veo una taza"}

    with pytest.raises(ValidationError):
        ReflectionContent.model_validate(
            {"kind": "reflection", "prompt": "p", "clueFrames": [frame, frame]}
        )
