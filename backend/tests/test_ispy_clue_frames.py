"""Guided I-Spy clue frames offer introduced vocabulary banks and never accept the target word."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.media import SceneObject
from app.schemas.tasks import (
    ClueAssistance,
    ClueSlotChoice,
    ISpyRoundContent,
    ReflectionContent,
    SubmitTextAttemptRequest,
)
from app.schemas.vocabulary import VocabularyItem
from app.services.ispy_clue_frames import (
    _place,
    build_clue_support,
    check_clue,
    clue_assistance_used,
    clue_grammar,
    mentions_target,
)
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


def frames_of(context, target, word, introduced=None):
    keys = [term["key"] for term in context["sceneObjects"]["objects"]]
    frames, avoid = build_clue_support(
        context, target, word, keys if introduced is None else introduced
    )
    return {frame.frame_id: frame for frame in frames}, avoid


def slot_texts(frame, slot_id):
    return [chip.text for slot in frame.slots if slot.slot_id == slot_id for chip in slot.chips]


def test_spanish_location_separates_position_and_reference_slots():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine"),
         "sofa": ("sofá", "el", "masculine"), "book": ("libro", "el", "masculine")},
        colours=[("cup", "color", "rojo"), ("table", "color", "marrón")],
        relations=[("cup", "on", "sobre", "table"), ("cup", "next_to", "al lado de", "sofa")],
    )

    frames, avoid = frames_of(context, target, word)

    location = frames["location"]
    assert location.prefix == "Está"
    assert location.template == "Está [position] [reference object]"
    assert location.chips == []
    assert slot_texts(location, "position") == [
        "sobre", "debajo de", "al lado de", "delante de", "detrás de",
    ]
    assert all(chip.meaning and chip.example for chip in location.slots[0].chips)
    assert slot_texts(location, "reference") == ["el libro", "el sofá", "la mesa"]
    assert location.phrases["sobre|la mesa"] == "sobre la mesa"
    assert location.phrases["al lado de|el libro"] == "al lado del libro"
    assert location.phrases["debajo de|el sofá"] == "debajo del sofá"
    assert location.help == ["sobre la mesa", "al lado del sofá"]
    assert {"taza", "tazas", "cup", "cups"} <= set(avoid)
    assert not any(mentions_target(text, avoid) for text in location.phrases.values())


def test_choices_offer_plausible_alternatives_and_examples_do_not_reveal_the_answer():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine"),
         "sofa": ("sofá", "el", "masculine")},
        colours=[("cup", "color", "rojo")],
        relations=[("cup", "on", "sobre", "table")],
    )

    frames, _avoid = frames_of(context, target, word)

    colour = frames["colour"]
    assert colour.template == "Es [colour]"
    assert slot_texts(colour, "colour") == [
        "amarilla", "azul", "blanca", "negra", "roja", "verde",
    ]
    assert colour.help == ["roja"]
    assert len(slot_texts(frames["location"], "reference")) == 2
    for frame in frames.values():
        assert frame.example not in {f"{frame.prefix} {phrase}" for phrase in frame.help}
        assert "taza" not in frame.example


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

    assert [f.prefix for f in frames.values()] == ["Elle est", "Elle est"]
    assert slot_texts(frames["colour"], "colour") == [
        "blanche", "bleue", "jaune", "noire", "rouge", "verte",
    ]
    location = frames["location"]
    assert "près de" in slot_texts(location, "position")
    assert location.phrases["à côté de|le livre"] == "à côté du livre"
    assert location.phrases["sous|l'arbre"] == "sous l'arbre"
    assert location.help == ["sur la table", "à côté du livre", "près de l'arbre"]


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

    assert (frames["colour"].help if "colour" in frames else []) == expected
    if expected:
        assert set(expected) <= set(slot_texts(frames["colour"], "colour"))


def test_french_masculine_target_uses_il():
    context, target, word = scene(
        "fr", {"book": ("livre", "le", "masculine")}, colours=[("book", "color", "bleu")]
    )

    frames, _avoid = frames_of(context, target, word)

    assert frames["colour"].prefix == "Il est"
    assert frames["colour"].template == "Il est [colour]"
    assert "bleu" in slot_texts(frames["colour"], "colour")


@pytest.mark.parametrize(
    ("gender", "prefix"),
    [("masculine", "Er ist"), ("feminine", "Sie ist"), ("neuter", "Es ist")],
)
def test_german_frames_use_gendered_prefixes_and_uninflected_colours(gender, prefix):
    context, target, word = scene(
        "de", {"thing": ("Tisch", "der", gender)}, colours=[("thing", "color", "rot")],
    )
    frames, _avoid = frames_of(context, target, word)
    assert frames["colour"].prefix == prefix
    assert frames["colour"].template == f"{prefix} [colour]"
    assert frames["colour"].help == ["rot"]


def test_german_locations_use_dative_articles_and_contractions():
    context, target, word = scene(
        "de",
        {
            "book": ("Buch", "das", "neuter"),
            "table": ("Tisch", "der", "masculine"),
            "door": ("Tür", "die", "feminine"),
        },
        colours=[("book", "color", "rot")],
        relations=[("book", "on", "auf", "table"), ("book", "next_to", "neben", "door")],
    )
    frames, _avoid = frames_of(context, target, word)
    location = frames["location"]
    assert location.prefix == "Es ist"
    assert "auf dem Tisch" in location.help
    assert "neben der Tür" in location.help
    assert _place("de", "an", {"translation": "Tisch", "gender": "masculine"}) == "am Tisch"
    assert clue_grammar("de").contraction("an", "dem") == "am"


def test_korean_clue_frames_match_aliases_and_keep_references_articleless():
    context, target, word = scene(
        "ko",
        {"apple": ("사과", None, None), "desk": ("책상", None, None)},
        colours=[("apple", "color", "빨간")],
        relations=[("apple", "on", "위에", "desk")],
    )
    frames, _avoid = frames_of(context, target, word)
    assert frames["colour"].help == ["빨간색이에요"]
    location = frames["location"]
    assert location.template == "이것은 [reference object] [position]"
    assert slot_texts(location, "reference") == ["책상"]
    assert location.phrases["위에|책상"] == "책상 위에 있어요"
    assert location.help == ["책상 위에 있어요"]


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
    assert frames["location"].help == ["cerca de la mesa"]

    context["sceneObjects"]["relations"] = []
    frames, _avoid = frames_of(context, target, word)
    assert frames == {}


def test_reference_chips_only_use_words_introduced_in_this_lesson():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine"),
         "lamp": ("lámpara", "la", "feminine")},
        relations=[("cup", "on", "sobre", "table")],
    )
    keys = {term["source"]: term["key"] for term in context["sceneObjects"]["objects"]}

    frames, _avoid = frames_of(context, target, word, [keys["cup"], keys["table"]])
    assert slot_texts(frames["location"], "reference") == ["la mesa"]

    frames, _avoid = frames_of(context, target, word, [keys["cup"], keys["lamp"]])
    assert frames == {}


def test_generated_support_never_suggests_a_forbidden_target_name():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "cup2": ("taza", "la", "feminine"),
         "table": ("mesa", "la", "feminine")},
        relations=[("cup", "next_to", "al lado de", "cup2"), ("cup", "on", "sobre", "table")],
    )

    frames, avoid = frames_of(context, target, word)

    location = frames["location"]
    assert slot_texts(location, "reference") == ["la mesa"]
    assert location.help == ["sobre la mesa"]
    texts = [*location.help, *location.phrases.values(),
             *(chip.text for slot in location.slots for chip in slot.chips)]
    assert not any(mentions_target(text, avoid) for text in texts)


def test_unsupported_languages_keep_free_typing_without_frames():
    context, target, word = scene("it", {"cup": ("tazza", None, None)})

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
        assert frames and any(frame.help for frame in frames)
        assert all(frame.slots and not frame.chips for frame in frames)
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
        ("Es una mésa", ["mesa", "mesas", "table"], True),
        ("Es un tazón rojo", ["taza", "tazas", "cup"], False),
        ("Es roja y está sobre la mesa", ["taza", "tazas", "cup"], False),
        ("Está al lado de la taza", ["mesa", "mesas", "table"], False),
        # Similar spellings may be different valid words, so they are never hard rejections.
        ("Es una mesaa marrón", ["mesa", "mesas", "table"], False),
        ("Es de la misa", ["mesa", "mesas", "table"], False),
        ("Es de este mes", ["mesa", "mesas", "table"], False),
    ],
)
def test_target_word_blocks_only_actual_target_forms(text, avoid, named):
    assert mentions_target(text, avoid) is named


def content_with_frames():
    context, target, word = scene(
        "es",
        {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine")},
        colours=[("cup", "color", "roja")],
        relations=[("cup", "on", "sobre", "table")],
    )
    keys = [term["key"] for term in context["sceneObjects"]["objects"]]
    frames, avoid = build_clue_support(context, target, word, keys)
    return ReflectionContent(prompt="Describe it", clue_frames=frames, avoid_words=avoid)


def attempt(text, **assistance):
    return SubmitTextAttemptRequest(
        text=text, assistance=ClueAssistance(**assistance) if assistance else None
    )


def test_check_clue_rejects_the_target_word_and_unoffered_assistance():
    content = content_with_frames()
    offered = ["colour", "location"]
    slots = [ClueSlotChoice(frame_id="location", slot_id="position", chip="debajo de"),
             ClueSlotChoice(frame_id="location", slot_id="reference", chip="la mesa")]

    check_clue(content, attempt("Es roja", offered_frame_ids=offered,
                                selected_frame_ids=["colour"], inserted_chips=["roja"]))
    # A wrong combination is a valid language choice; the evaluator judges it.
    check_clue(content, attempt("Está debajo de la mesa", offered_frame_ids=offered,
                                selected_frame_ids=["location"], selected_slots=slots,
                                inserted_chips=["debajo de", "la mesa"]))
    check_clue(content, attempt("Está sobre la mesa", offered_frame_ids=offered,
                                selected_frame_ids=["location"], inserted_chips=["sobre la mesa"],
                                revealed_help_frame_ids=["location"]))
    check_clue(content, attempt("Es pequeña y roja."))
    check_clue(content, attempt("Está cerca de la mesa"))
    with pytest.raises(ClueNamesTargetError):
        check_clue(content, attempt("Veo una taza roja"))
    for bad in [
        dict(offered_frame_ids=["name"]),
        dict(offered_frame_ids=offered, selected_frame_ids=["name"]),
        dict(offered_frame_ids=[], selected_frame_ids=["colour"]),
        dict(offered_frame_ids=offered, inserted_chips=["roja"]),
        dict(offered_frame_ids=offered, selected_frame_ids=["colour"], selected_slots=slots),
        dict(offered_frame_ids=offered, selected_frame_ids=["location"], selected_slots=[
            ClueSlotChoice(frame_id="location", slot_id="reference", chip="la taza")]),
        dict(offered_frame_ids=["colour"], revealed_help_frame_ids=["location"]),
        dict(offered_frame_ids=["colour"], revealed_meaning_frame_ids=["location"]),
        dict(word_bank_shown=True),
        dict(cheat_sheet_opened=True),
    ]:
        with pytest.raises(PracticeConflictError):
            check_clue(content, attempt("Es roja", **bad))


@pytest.mark.parametrize("support", [None, {}, {"targetWordShown": True}, {
    "offeredFrameIds": ["colour", "location"], "practiceMode": "guided",
}])
def test_offered_clue_support_is_not_optional_assistance_usage(support):
    assert clue_assistance_used(support) is False


@pytest.mark.parametrize("support", [
    {"selectedFrameIds": ["colour"]},
    {"insertedChips": ["azul"]},
    {"selectedSlots": [{"frameId": "colour", "slotId": "colour", "chip": "azul"}]},
    {"revealedHelpFrameIds": ["location"]},
    {"revealedMeaningFrameIds": ["location"]},
    {"wordBankShown": True},
    {"cheatSheetOpened": True},
])
def test_used_clue_support_is_assisted_in_api_and_stored_payloads(support):
    parsed = ClueAssistance.model_validate(support)
    assert clue_assistance_used(parsed)
    assert clue_assistance_used(parsed.model_dump(by_alias=False))


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
