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
from app.services.session_plan import build_ispy_description_tasks


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
        colours=[("cup", "color", "rojo"), ("table", "color", "marrón")],
        relations=[("cup", "on", "sobre", "table"), ("cup", "next_to", "al lado de", "sofa")],
    )

    frames, avoid = frames_of(context, target, word)

    assert [(f.prefix, f.example) for f in frames.values()] == [
        ("Es", "Es roja"), ("Está", "Está sobre la mesa"),
    ]
    assert all(frame.meaning for frame in frames.values())
    assert frames["colour"].chips == ["roja"]
    assert frames["location"].chips == ["sobre la mesa", "al lado del sofá"]
    assert {"taza", "tazas", "cup", "cups"} <= set(avoid)


def test_french_frames_agree_with_the_target_and_contract_articles():
    context, target, word = scene(
        "fr",
        {"cup": ("tasse", "la", "feminine"), "table": ("table", "la", "feminine"),
         "book": ("livre", "le", "masculine"), "tree": ("arbre", "l'", "masculine")},
        colours=[("cup", "color", "blanc")],
        relations=[("cup", "on", "sur", "table"), ("cup", "next_to", "à côté de", "book"),
                   ("cup", "near", "près de", "tree")],
    )

    frames, _avoid = frames_of(context, target, word)

    assert [(f.prefix, f.example) for f in frames.values()] == [
        ("Elle est", "Elle est blanche"), ("Elle est", "Elle est sur la table"),
    ]
    assert frames["location"].chips == ["sur la table", "à côté du livre", "près de l'arbre"]


@pytest.mark.parametrize(
    ("language", "noun", "gender", "dictionary_form", "expected"),
    [
        ("es", "taza", "feminine", "rojo", ["roja"]),
        ("es", "vaso", "masculine", "roja", ["rojo"]),
        ("es", "taza", "feminine", "azul", ["azul"]),
        ("es", "taza", "feminine", "marron", ["marrón"]),
        ("es", "taza", None, "rojo", []),
        ("es", "taza", "feminine", "carmesí", []),
        ("es", "taza", "feminine", "rojo oscuro", []),
        ("fr", "tasse", "feminine", "blanc", ["blanche"]),
        ("fr", "tasse", "feminine", "violet", ["violette"]),
        ("fr", "livre", "masculine", "verte", ["vert"]),
        ("fr", "tasse", "feminine", "rouge", ["rouge"]),
        ("fr", "tasse", "feminine", "marron", ["marron"]),
        ("fr", "tasse", "feminine", "pourpre", []),
    ],
)
def test_dictionary_form_colours_agree_with_the_target_or_are_omitted(
    language, noun, gender, dictionary_form, expected
):
    context, target, word = scene(
        language, {"thing": (noun, None, gender)},
        colours=[("thing", "color", dictionary_form)],
    )

    frames, _avoid = frames_of(context, target, word)

    assert (frames["colour"].chips if "colour" in frames else []) == expected
    if expected:
        assert frames["colour"].example == f"{frames['colour'].prefix} {expected[0]}"


def test_french_masculine_target_uses_il():
    context, target, word = scene(
        "fr", {"book": ("livre", "le", "masculine")}, colours=[("book", "color", "bleu")]
    )

    frames, _avoid = frames_of(context, target, word)

    assert frames["colour"].prefix == "Il est"
    assert frames["colour"].example == "Il est bleu"


def test_absent_attributes_and_relations_offer_no_frames_and_never_a_name_frame():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine")},
        colours=[("cup", "material", "cerámica"), ("table", "color", "marrón")],
        relations=[("table", "on", "sobre", "cup"), ("table", "near", "cerca de", "cup")],
    )

    frames, _avoid = frames_of(context, target, word)

    assert list(frames) == ["location"]
    # Only the symmetric relation can be read from the target's side.
    assert frames["location"].chips == ["cerca de la mesa"]

    context["sceneObjects"]["relations"] = []
    frames, _avoid = frames_of(context, target, word)
    assert frames == {}


def test_generated_support_never_suggests_a_forbidden_target_name():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "cup2": ("taza", "la", "feminine"),
         "table": ("mesa", "la", "feminine")},
        relations=[("cup", "next_to", "al lado de", "cup2"), ("cup", "on", "sobre", "table")],
    )

    frames, avoid = frames_of(context, target, word)

    assert frames["location"].chips == ["sobre la mesa"]
    assert not any(
        mentions_target(chip, avoid) for frame in frames.values() for chip in frame.chips
    )


def test_unsupported_languages_keep_free_typing_without_frames():
    context, target, word = scene("de", {"cup": ("Tasse", "die", "feminine")})

    assert build_clue_support(context, target, word) == ([], [])


def describable_scene():
    session_id = uuid4()
    context, cup, cup_word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "lamp": ("lámpara", "la", "feminine"),
         "sofa": ("sofá", "el", "masculine"), "table": ("mesa", "la", "feminine")},
        colours=[("table", "color", "carmesí"), ("sofa", "color", "verde")],
        relations=[("table", "on", "sobre", "lamp")],
    )
    keys = {term["source"]: term["key"] for term in context["sceneObjects"]["objects"]}
    objects = [SceneObject(id=keys[name], session_id=session_id, label=name)
               for name in ("cup", "lamp", "sofa", "table")]
    words = [VocabularyItem(language_code="es", lemma=t, display_text=t, part_of_speech="noun")
             for t in ("taza", "lámpara", "sofá", "mesa")]
    return session_id, objects, words, context


def test_new_tasks_only_target_objects_with_usable_description_support():
    session_id, objects, words, context = describable_scene()

    tasks = build_ispy_description_tasks(session_id, objects, words, context)

    # The cup and lamp have no confirmed colour or outgoing relation; the table's
    # colour cannot be inflected safely, but its position can be described.
    assert [task.scene_object_id for task in tasks] == [objects[2].id, objects[3].id]
    for task in tasks:
        frames = task.public_content.clue_frames
        assert frames and all(frame.chips for frame in frames)
        assert "name" not in {frame.frame_id for frame in frames}


def test_a_photo_without_description_support_creates_no_description_tasks():
    session_id, objects, words, context = describable_scene()
    context["sceneObjects"]["attributes"] = []
    context["sceneObjects"]["relations"] = []

    assert build_ispy_description_tasks(session_id, objects, words, context) == []


@pytest.mark.parametrize(
    ("text", "avoid", "named"),
    [
        ("Veo una TAZA", ["taza", "tazas", "cup"], True),
        ("Son tazas rojas.", ["taza", "tazas", "cup"], True),
        ("Es una táza", ["taza", "tazas", "cup"], True),
        ("It is a cup", ["taza", "tazas", "cup"], True),
        ("Es un tazón rojo", ["taza", "tazas", "cup"], False),
        ("Es roja y está sobre la mesa", ["taza", "tazas", "cup"], False),
        ("Es una mesaa marrón", ["mesa", "mesas", "table"], True),
        ("Es una mesaaa", ["mesa", "mesas", "table"], True),
        ("Es una mésa", ["mesa", "mesas", "table"], True),
        ("Está al lado de la taza", ["mesa", "mesas", "table"], False),
        ("Es de este mes", ["mesa", "mesas", "table"], False),
    ],
)
def test_target_word_matches_whole_words_and_one_letter_misspellings(text, avoid, named):
    assert mentions_target(text, avoid) is named


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
    offered = ["colour"]

    check_clue(content, attempt("Es roja", offered_frame_ids=offered,
                                selected_frame_ids=["colour"], inserted_chips=["roja"]))
    check_clue(content, attempt("Es pequeña y roja."))
    check_clue(content, attempt("Está cerca de la mesa"))
    with pytest.raises(ClueNamesTargetError):
        check_clue(content, attempt("Veo una taza roja"))
    for bad in [
        dict(offered_frame_ids=["name"]),
        dict(offered_frame_ids=offered, selected_frame_ids=["location"]),
        dict(offered_frame_ids=[], selected_frame_ids=["colour"]),
        dict(offered_frame_ids=offered, inserted_chips=["roja"]),
    ]:
        with pytest.raises(PracticeConflictError):
            check_clue(content, attempt("Es roja", **bad))


def test_legacy_name_frames_still_validate_whether_shown_or_hidden():
    legacy_name = {"frameId": "name", "prefix": "Veo", "meaning": "I see",
                   "example": "Veo una taza", "chips": ["una mesa"]}
    colour = {"frameId": "colour", "prefix": "Es", "meaning": "It is",
              "example": "Es roja", "chips": ["roja"]}
    content = ReflectionContent.model_validate(
        {"kind": "reflection", "prompt": "p", "clueFrames": [legacy_name, colour],
         "avoidWords": ["taza"]}
    )

    check_clue(content, attempt("Es roja", offered_frame_ids=["colour"],
                                selected_frame_ids=["colour"], inserted_chips=["roja"]))
    check_clue(content, attempt("Veo una mesa", offered_frame_ids=["name", "colour"],
                                selected_frame_ids=["name"], inserted_chips=["una mesa"]))
    with pytest.raises(PracticeConflictError):
        check_clue(content, attempt("Es roja", offered_frame_ids=["colour", "name"]))


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
    frame = {"frameId": "colour", "prefix": "Es", "meaning": "It is", "example": "Es roja"}

    with pytest.raises(ValidationError):
        ReflectionContent.model_validate(
            {"kind": "reflection", "prompt": "p", "clueFrames": [frame, frame]}
        )
