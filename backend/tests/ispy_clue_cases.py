"""Fixed I-Spy clue cases for every clue language, and the output they produce.

``snapshot()`` runs the clue-frame builder, colour agreement, location phrases and the
room clue builder over the same inputs every time (fixed IDs). The golden file
``fixtures/ispy_clue_frames.json`` holds what the hand-written per-language tables
produced before that grammar moved into each pack's ``clues.toml``; the equivalence
test requires the pack-driven code to produce exactly the same.
"""

from uuid import NAMESPACE_URL, uuid5

from app.ai.features.translation.schemas import SceneTranslationResult
from app.schemas.media import SceneObject, SceneObjectRelation
from app.schemas.vocabulary import VocabularyItem

GOLDEN = "fixtures/ispy_clue_frames.json"
GENDERS = ("masculine", "feminine", "neuter", None)

# name: (translation, article, gender)
NOUNS = {
    "es": {
        "cup": ("taza", "la", "feminine"), "table": ("mesa", "la", "feminine"),
        "sofa": ("sofá", "el", "masculine"), "book": ("libro", "el", "masculine"),
        "pencil": ("lápiz", None, "masculine"), "tree": ("árbol", None, None),
        "lamp": ("lámpara", None, "feminine"),
    },
    "fr": {
        "cup": ("tasse", "la", "feminine"), "table": ("table", "la", "feminine"),
        "book": ("livre", "le", "masculine"), "tree": ("arbre", "l'", "masculine"),
        "chair": ("chaise", None, "feminine"), "cake": ("gâteau", "le", "masculine"),
        "pen": ("stylo", None, None),
    },
    "de": {
        "cup": ("Tasse", "die", "feminine"), "table": ("Tisch", "der", "masculine"),
        "book": ("Buch", "das", "neuter"), "lamp": ("Lampe", None, "feminine"),
        "chair": ("Stuhl", "der", None), "door": ("Tür", None, None),
    },
    "ko": {
        "cup": ("컵", None, None), "desk": ("책상", None, None), "book": ("책", None, None),
        "chair": ("의자", None, None),
    },
}
# (subject, relation type, translation, reference)
RELATIONS = {
    "es": [
        ("cup", "on", "sobre", "table"), ("cup", "next_to", "al lado de", "sofa"),
        ("book", "near", "cerca de", "cup"), ("cup", "behind", "está detrás de", "pencil"),
        ("cup", "in_front_of", "delante de", "book"), ("pencil", "under", "debajo de", "cup"),
        ("cup", "inside", "junto a", "sofa"), ("cup", "left_of", "a la izquierda de", "lamp"),
        ("cup", "right_of", "a la derecha de", "tree"),
    ],
    "fr": [
        ("cup", "on", "sur", "table"), ("cup", "next_to", "à côté de", "book"),
        ("tree", "near", "près de", "cup"), ("cup", "behind", "est derrière", "chair"),
        ("cup", "in_front_of", "devant", "tree"), ("cup", "inside", "à", "book"),
        ("cup", "under", "sous", "pen"),
    ],
    "de": [
        ("cup", "on", "auf", "table"), ("cup", "next_to", "neben", "lamp"),
        ("book", "near", "bei", "cup"), ("cup", "behind", "ist hinter", "chair"),
        ("cup", "inside", "in", "book"), ("cup", "in_front_of", "vor", "chair"),
        ("cup", "above", "zu", "table"), ("cup", "under", "unter", "door"),
    ],
    "ko": [
        ("cup", "on", "위에", "desk"), ("cup", "next_to", "옆에", "book"),
        ("chair", "near", "근처에", "cup"), ("cup", "behind", "뒤에", "chair"),
    ],
}
COLOURS = {
    "es": ["rojo", "Roja", "azul", "gris ", "morado", "naranja", "turquesa", "fucsia", "marrón"],
    "fr": ["rouge", "bleu", "Blanche", "violet", "doré", "marron", "orange", "fuchsia"],
    "de": ["rot", "Grün", "weiß", "lila", "silbern", "türkis", "pink"],
    "ko": ["빨간색", "파란", "녹색", "회색", "베이지", "연두색", "빨간색이에요"],
}
# Clue-frame scenes: (case, target, colours on objects, relations used, introduced).
FRAME_CASES = [
    ("all", None, None, None),
    ("no-relations", None, (), None),
    ("no-introduced", None, None, ()),
    ("first-two-introduced", None, None, 2),
]
BANK_POSITIONS = {
    "es": ["sobre", "debajo de", "al lado de", "delante de", "detrás de"],
    "fr": ["sur", "sous", "à côté de", "devant", "derrière"],
    "de": ["auf", "unter", "neben", "vor", "hinter"],
    "ko": ["위에", "아래에", "옆에", "앞에", "뒤에"],
}
EXTRA_POSITIONS = {
    "es": ["junto a", "cerca de", "está sobre", "de", "a"],
    "fr": ["à", "de", "près de", "est sur", "à côté de"],
    "de": ["an", "in", "zu", "von", "bei", "ist auf"],
    "ko": ["근처에", "안에"],
}
ROOM_CASES = {
    "es": ({"cup": ("taza", "la", "feminine"), "book": ("libro", "el", "masculine"),
            "table": ("mesa", "la", "feminine")},
           {"cup": "rojo", "book": "azul"},
           [("cup", "on", "sobre", "table"), ("book", "next_to", "al lado de", "cup")]),
    "fr": ({"cup": ("tasse", "la", "feminine"), "book": ("livre", "le", "masculine"),
            "tree": ("arbre", "l'", "masculine")},
           {"cup": "rouge", "tree": "vert"},
           [("cup", "next_to", "à côté de", "book"), ("tree", "behind", "derrière", "book")]),
    "de": ({"cup": ("Tasse", "die", "feminine"), "table": ("Tisch", "der", "masculine"),
            "book": ("Buch", "das", "neuter")},
           {"cup": "rot", "book": "blau"},
           [("cup", "on", "auf", "table"), ("book", "next_to", "neben", "table")]),
}


def _id(*parts):
    return uuid5(NAMESPACE_URL, "ispy-clue-case:" + ":".join(parts))


def _colours_for(language):
    """One confirmed colour per object, cycling through the language's colour cases."""
    names = list(NOUNS[language])
    colours = COLOURS[language]
    return [(name, "color", colours[index % len(colours)]) for index, name in enumerate(names)]


def _context(language, case, colours, relations):
    nouns = NOUNS[language]
    ids = {name: _id(language, case, name) for name in nouns}
    return ids, {
        "targetLanguage": language,
        "sceneObjects": {
            "objects": [
                {"key": str(ids[name]), "source": name, "translation": translation,
                 **({"article": article} if article else {}),
                 **({"gender": gender} if gender else {})}
                for name, (translation, article, gender) in nouns.items()
            ],
            "attributes": [
                {"key": f"{ids[name]}:{kind}", "objectKey": str(ids[name]),
                 "source": kind, "translation": value}
                for name, kind, value in colours
            ],
            "relations": [
                {"key": str(_id(language, case, "relation", str(index))), "source": relation,
                 "translation": translation, "subjectObjectKey": str(ids[subject]),
                 "referenceObjectKey": str(ids[reference])}
                for index, (subject, relation, translation, reference) in enumerate(relations)
            ],
        },
    }


def _frames(language):
    from app.services.ispy_clue_frames import build_clue_support

    results = {}
    for case, _target, colours, introduced in FRAME_CASES:
        colours = _colours_for(language) if colours is None else colours
        relations = RELATIONS[language] if case != "no-relations" else []
        for target_name, (translation, _article, gender) in NOUNS[language].items():
            ids, context = _context(language, f"{case}:{target_name}", colours, relations)
            keys = [str(ids[name]) for name in NOUNS[language]]
            if introduced is None:
                chosen = keys
            elif isinstance(introduced, int):
                chosen = keys[:introduced]
            else:
                chosen = list(introduced)
            target = SceneObject(id=ids[target_name], session_id=_id(language, case),
                                 label=target_name)
            word = VocabularyItem(
                language_code=language, lemma=translation, display_text=translation,
                part_of_speech="noun", gender=gender,
            )
            frames, avoid = build_clue_support(context, target, word, chosen)
            results[f"{case}:{target_name}"] = {
                "frames": [frame.model_dump(mode="json") for frame in frames],
                "avoid": avoid,
            }
    return results


def _agreement(language):
    from app.services.ispy_clue_frames import agree_colour

    return {
        f"{colour}|{gender}": agree_colour(language, colour, gender)
        for colour in COLOURS[language] for gender in GENDERS
    }


def _places(language):
    from app.services.ispy_clue_frames import _place

    terms = [
        {"translation": translation, **({"article": article} if article else {}),
         **({"gender": gender} if gender else {})}
        for translation, article, gender in NOUNS[language].values()
    ]
    return {
        f"{position}|{term['translation']}": _place(language, position, term)
        for position in [*BANK_POSITIONS[language], *EXTRA_POSITIONS[language]]
        for term in terms
    }


def _room(language):
    from app.services.room_clues import RoomClueError, build_room_pack

    nouns, colours, relations = ROOM_CASES[language]
    photo_id = _id(language, "room")
    objects = [
        SceneObject(id=_id(language, "room", name), session_id=photo_id, label=name,
                    anchor_point={"x": (index + 1) / 10, "y": 0.5})
        for index, name in enumerate(nouns)
    ]
    by_name = {obj.label: obj for obj in objects}
    links = [
        SceneObjectRelation(
            id=_id(language, "room-relation", str(index)),
            subject_scene_object_id=by_name[subject].id,
            reference_scene_object_id=by_name[reference].id, relation=kind,
        )
        for index, (subject, kind, _translation, reference) in enumerate(relations)
    ]
    translated = SceneTranslationResult(
        objects=[
            {"key": str(by_name[name].id), "source": name, "translation": term,
             "article": article, "gender": gender}
            for name, (term, article, gender) in nouns.items()
        ],
        attributes=[
            {"key": f"{by_name[name].id}:color", "source": colour, "translation": colour}
            for name, colour in colours.items()
        ],
        relationships=[
            {"key": str(link.id), "source": kind, "translation": translation}
            for link, (_subject, kind, translation, _reference) in zip(
                links, relations, strict=True
            )
        ],
    )
    try:
        return build_room_pack(photo_id, "My photo", objects, links, translated, language)
    except RoomClueError as error:
        return {"error": str(error)}


def snapshot():
    """Every case's output, by language, as JSON-ready data."""
    return {
        language: {
            "frames": _frames(language),
            "agreement": _agreement(language),
            "places": _places(language),
            **({"room": _room(language)} if language in ROOM_CASES else {}),
        }
        for language in NOUNS
    }
