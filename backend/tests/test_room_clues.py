"""Guided options are truthful, unambiguous and never disclose the target word."""

from uuid import uuid4, uuid5

import pytest

from app.ai.features.translation.schemas import SceneTranslationResult
from app.schemas.media import SceneObject, SceneObjectRelation
from app.services.ispy_clue_frames import mentions_target
from app.services.room_clues import RoomClueError, build_room_pack


def photo(nouns, *, colours=None, relations=(), language="es"):
    identity = uuid4()
    objects = {
        name: SceneObject(
            id=uuid5(identity, name),
            session_id=identity,
            label=name,
            anchor_point={"x": (index + 1) / 10, "y": 0.5},
        )
        for index, name in enumerate(nouns)
    }
    links = [
        SceneObjectRelation(
            id=uuid5(identity, f"relation:{index}"),
            subject_scene_object_id=objects[subject].id,
            reference_scene_object_id=objects[reference].id,
            relation=kind,
        )
        for index, (subject, kind, _translation, reference) in enumerate(relations)
    ]
    translated = SceneTranslationResult(
        objects=[
            {
                "key": str(objects[name].id),
                "source": name,
                "translation": term,
                "article": article,
                "gender": gender,
            }
            for name, (term, article, gender) in nouns.items()
        ],
        attributes=[
            {"key": f"{objects[name].id}:color", "source": colour, "translation": colour}
            for name, colour in (colours or {}).items()
        ],
        relationships=[
            {"key": str(link.id), "source": kind, "translation": translation}
            for link, (_subject, kind, translation, _reference) in zip(
                links, relations, strict=True
            )
        ],
    )
    return identity, list(objects.values()), links, translated, language


def pack(parts):
    identity, objects, relations, translated, language = parts
    return build_room_pack(identity, "My photo", objects, relations, translated, language)


def clues(result, object_key):
    return [
        option["text"]
        for target in result["targets"]
        if target["objectKey"] == object_key
        for option in target["clueOptions"]
    ]


def test_only_confirmed_colours_become_complete_options_with_stable_numbered_markers():
    parts = photo(
        {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "table": ("mesa", "la", "feminine"),
        },
        colours={"cup": "rojo", "book": "azul", "table": "marrón"},
    )
    result = pack(parts)
    assert [obj["marker"] for obj in result["objects"]] == [1, 2, 3]
    assert [obj["key"] for obj in result["objects"]] == [str(obj.id) for obj in parts[1]]
    assert result["objects"][0] == {
        "key": str(parts[1][0].id),
        "marker": 1,
        "label": "cup",
        "word": "la taza",
        "translation": "cup",
        "x": 10.0,
        "y": 50.0,
    }
    assert clues(result, str(parts[1][0].id)) == ["Es roja."]
    assert clues(result, str(parts[1][1].id)) == ["Es azul."]
    assert not any(
        "amarill" in clue or "verde" in clue
        for target in result["targets"]
        for clue in clues(result, target["objectKey"])
    )
    assert pack(parts) == result


def test_combination_can_distinguish_an_object_when_neither_single_cue_does():
    parts = photo(
        {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "bowl": ("bol", "el", "masculine"),
            "table": ("mesa", "la", "feminine"),
            "shelf": ("estantería", "la", "feminine"),
        },
        colours={
            "cup": "rojo",
            "book": "rojo",
            "bowl": "azul",
            "table": "marrón",
            "shelf": "marrón",
        },
        relations=[
            ("cup", "on", "sobre", "table"),
            ("book", "on", "sobre", "shelf"),
            ("bowl", "on", "sobre", "table"),
        ],
    )
    assert clues(pack(parts), str(parts[1][0].id)) == ["Es roja y está sobre la mesa."]


@pytest.mark.parametrize("gender", ["masculine", None])
def test_same_colour_is_ambiguous_even_with_different_or_unknown_noun_gender(gender):
    parts = photo(
        {"cup": ("taza", "la", "feminine"), "book": ("libro", "el", gender)},
        colours={"cup": "roja", "book": "rojo"},
    )
    with pytest.raises(RoomClueError, match="two clearly distinguishable"):
        pack(parts)


def test_duplicate_reference_nouns_do_not_create_false_unique_location_options():
    parts = photo(
        {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "table-one": ("mesa", "la", "feminine"),
            "table-two": ("mesa", "la", "feminine"),
        },
        colours={"cup": "rojo", "book": "rojo", "table-one": "marrón", "table-two": "marrón"},
        relations=[("cup", "on", "sobre", "table-one"), ("book", "on", "sobre", "table-two")],
    )
    with pytest.raises(RoomClueError, match="two clearly distinguishable"):
        pack(parts)


def test_synonymous_translations_of_one_relation_do_not_create_false_unique_clues():
    parts = photo(
        {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "table": ("mesa", "la", "feminine"),
        },
        colours={"cup": "rojo", "book": "rojo"},
        relations=[("cup", "on", "sobre", "table"), ("book", "on", "encima de", "table")],
    )
    with pytest.raises(RoomClueError, match="two clearly distinguishable"):
        pack(parts)


def test_symmetric_reviewed_relation_supports_both_objects_without_inventing_inverse():
    nouns = {"cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine")}
    result = pack(photo(nouns, relations=[("cup", "next_to", "al lado de", "table")]))
    assert {option["text"] for target in result["targets"] for option in target["clueOptions"]} == {
        "Está al lado de la mesa.",
        "Está al lado de la taza.",
    }
    with pytest.raises(RoomClueError):
        pack(photo(nouns, relations=[("cup", "on", "sobre", "table")]))


def test_each_option_omits_target_forms_and_wrong_relational_alternatives():
    parts = photo(
        {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "table": ("mesa", "la", "feminine"),
        },
        colours={"cup": "rojo", "book": "azul", "table": "marrón"},
        relations=[("cup", "on", "sobre", "table")],
    )
    result = pack(parts)
    for obj, term in zip(parts[1], parts[3].objects, strict=True):
        for text in clues(result, str(obj.id)):
            assert not mentions_target(text, [term.translation, obj.label])
            assert "debajo" not in text
    assert "Es roja y está sobre la mesa." in clues(result, str(parts[1][0].id))


def test_compound_noun_head_cannot_name_the_target_inside_a_reference_clue():
    parts = photo(
        {
            "coffee machine": ("máquina de café", "la", "feminine"),
            "machine": ("máquina", "la", "feminine"),
        },
        colours={"coffee machine": "rojo", "machine": "azul"},
        relations=[("coffee machine", "next_to", "al lado de", "machine")],
    )
    assert clues(pack(parts), str(parts[1][0].id)) == ["Es roja."]


@pytest.mark.parametrize("article", ["un", "la taza", "las", None])
def test_unsupported_articles_never_enter_complete_clues(article):
    parts = photo(
        {"cup": ("taza", article, "feminine"), "book": ("libro", "el", "masculine")},
        colours={"cup": "rojo", "book": "azul"},
    )
    with pytest.raises(RoomClueError, match="singular object names"):
        pack(parts)


def test_french_agreement_contractions_and_elision_remain_complete():
    parts = photo(
        {
            "cup": ("tasse", "la", "feminine"),
            "book": ("livre", "le", "masculine"),
            "tree": ("arbre", "l'", "masculine"),
        },
        language="fr",
        colours={"cup": "blanc", "book": "bleu", "tree": "vert"},
        relations=[("cup", "next_to", "à côté de", "book"), ("book", "under", "sous", "tree")],
    )
    result = pack(parts)
    assert "Elle est blanche et elle est à côté du livre." in clues(result, str(parts[1][0].id))
    assert "Il est bleu et il est sous l'arbre." in clues(result, str(parts[1][1].id))
    assert result["objects"][2]["word"] == "l'arbre"


def test_no_support_or_unsupported_colour_never_generates_facts_from_markers():
    nouns = {"cup": ("taza", "la", "feminine"), "book": ("libro", "el", "masculine")}
    with pytest.raises(RoomClueError):
        pack(photo(nouns))
    with pytest.raises(RoomClueError):
        pack(photo(nouns, colours={"cup": "carmesí", "book": "azul"}))


def test_foreign_photo_objects_and_unplaced_markers_are_rejected():
    parts = photo(
        {"cup": ("taza", "la", "feminine"), "book": ("libro", "el", "masculine")},
        colours={"cup": "rojo", "book": "azul"},
    )
    with pytest.raises(RoomClueError, match="different photo"):
        build_room_pack(uuid4(), "Other photo", *parts[1:])
    parts[1][0].anchor_point = None
    with pytest.raises(RoomClueError, match="Place a marker"):
        pack(parts)
