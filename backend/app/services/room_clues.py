"""Immutable guided room content from reviewed facts, without turn-time model calls."""

from dataclasses import dataclass
from itertools import combinations
from uuid import UUID, uuid5

from app.ai.features.translation.schemas import SceneTranslationResult
from app.schemas.enums import SYMMETRIC_SCENE_RELATION_TYPES
from app.schemas.media import SceneObject, SceneObjectRelation
from app.schemas.vocabulary import VocabularyItem
from app.services.ispy_clue_frames import (
    _place,
    agree_colour,
    build_clue_support,
    mentions_target,
)

ROOM_LANGUAGES = {"es", "fr", "de"}


class RoomClueError(ValueError):
    """Reviewed facts do not yet support an unambiguous guided game."""


@dataclass(frozen=True)
class _Cue:
    text: str
    kind: str
    value: str

    @property
    def signature(self) -> tuple[str, str]:
        return self.kind, self.value.casefold()


def build_room_pack(
    photo_id: UUID,
    title: str,
    objects: list[SceneObject],
    relations: list[SceneObjectRelation],
    translated: SceneTranslationResult,
    language: str,
) -> dict:
    """Offer complete truthful clues that match exactly one reviewed object.

    The solo support builder intentionally offers wrong alternatives. Only its
    confirmed ``help`` phrases become room candidates. Match colour independently
    of grammatical gender, and location by its spoken phrase rather than opaque
    reference ID, so duplicate reference nouns cannot create false uniqueness.
    Marker coordinates never invent colour or spatial relationships.
    """
    if language not in ROOM_LANGUAGES:
        raise RoomClueError(
            "Guided photo rooms currently support Spanish, French and German."
        )
    if not 2 <= len(objects) <= 6 or len({obj.id for obj in objects}) != len(objects):
        raise RoomClueError("Choose between two and six different objects in this photo.")
    selected = {obj.id for obj in objects}
    if any(obj.session_id != photo_id for obj in objects):
        raise RoomClueError("The reviewed objects belong to a different photo.")
    if any(
        not {row.subject_scene_object_id, row.reference_scene_object_id} <= selected
        for row in relations
    ):
        raise RoomClueError("Every relationship must connect objects in this photo.")
    terms = {row.key: row for row in translated.objects}
    if len(terms) != len(objects) or set(terms) != {str(obj.id) for obj in objects}:
        raise RoomClueError("Translate exactly the reviewed objects before starting the game.")
    articles = {"es": {"el", "la"}, "fr": {"le", "la", "l'"},
                "de": {"der", "die", "das"}}
    if any(
        (term.article or "").lower().replace("’", "'") not in articles[language]
        for term in terms.values()
    ):
        raise RoomClueError(
            "These guided clues need singular object names with a definite article. "
            "Review the object labels, or choose another photo."
        )
    terms = {
        key: term.model_copy(update={"article": term.article.lower().replace("’", "'")})
        for key, term in terms.items()
    }

    facts = {
        "objects": [row.model_dump(mode="json", by_alias=True) for row in terms.values()],
        "attributes": [
            {**row.model_dump(mode="json", by_alias=True), "objectKey": row.key.rsplit(":", 1)[0]}
            for row in translated.attributes
        ],
        "relations": [],
    }
    relation_terms = {row.key: row for row in translated.relationships}
    for relation in relations:
        term = relation_terms.get(str(relation.id))
        if term is None:
            raise RoomClueError("Translate every reviewed relationship before starting the game.")
        facts["relations"].append(
            {
                **term.model_dump(mode="json", by_alias=True),
                "subjectObjectKey": str(relation.subject_scene_object_id),
                "referenceObjectKey": str(relation.reference_scene_object_id),
            }
        )
    context = {"targetLanguage": language, "sceneObjects": facts}
    introduced = [str(obj.id) for obj in objects]
    cues, avoid = {}, {}
    markers = []
    for marker, obj in enumerate(objects, 1):
        term = terms[str(obj.id)]
        word = VocabularyItem(
            language_code=language,
            lemma=term.translation,
            display_text=term.translation,
            part_of_speech="noun",
            gender=term.gender,
        )
        frames, forbidden = build_clue_support(context, obj, word, introduced)
        # For singular French/Spanish compound nouns the first noun still names
        # the target: "máquina" must not reveal "máquina de café". The solo
        # builder only forbids the complete phrase, so tighten room options here.
        if len(term.translation.split()) > 1:
            head = term.translation.split()[0]
            forbidden = [*forbidden, head, head + "s"]
        item_cues = []
        for frame in frames:
            for phrase in frame.help:
                canonical = (
                    agree_colour(language, phrase, "masculine")
                    if frame.frame_id == "colour"
                    else phrase
                )
                if canonical:
                    item_cues.append(
                        _Cue(
                            text=f"{frame.prefix} {phrase}",
                            kind=frame.frame_id,
                            value=canonical,
                        )
                    )
        cues[str(obj.id)] = item_cues
        avoid[str(obj.id)] = forbidden
        if obj.anchor_point:
            x, y = float(obj.anchor_point.x), float(obj.anchor_point.y)
        elif obj.bounding_box:
            box = obj.bounding_box
            x = float(box.x + box.width / 2)
            y = float(box.y + box.height / 2)
        else:
            raise RoomClueError("Place a marker on every selected object before confirming.")
        article = term.article or ""
        display = f"{article}{'' if article.endswith(("'", '’')) else ' '}{term.translation}"
        markers.append(
            {
                "key": str(obj.id),
                "marker": marker,
                "label": obj.label,
                "word": display.strip(),
                "translation": term.source,
                "x": round(x * 100, 4),
                "y": round(y * 100, 4),
            }
        )

    # A competitor's truth set must not depend on whether that competitor can
    # itself offer a clue. Unknown noun gender or its forbidden target word may
    # hide a support frame, but cannot make the object disappear from matching.
    signatures = {str(obj.id): set() for obj in objects}
    for attribute in facts["attributes"]:
        if attribute["key"].rsplit(":", 1)[-1] not in {"color", "colour"}:
            continue
        canonical = agree_colour(language, attribute["translation"], "masculine")
        if canonical and attribute["objectKey"] in signatures:
            signatures[attribute["objectKey"]].add(("colour", canonical.casefold()))
    # A provider can translate the same relation with synonyms in different rows.
    # Compare all supplied synonyms, so wording differences cannot make two
    # objects with the same confirmed spatial fact look uniquely identifiable.
    relation_variants = {}
    for relation in facts["relations"]:
        relation_variants.setdefault(relation["source"], set()).add(relation["translation"])
    for relation in facts["relations"]:
        pairs = [(relation["subjectObjectKey"], relation["referenceObjectKey"])]
        if relation["source"] in SYMMETRIC_SCENE_RELATION_TYPES:
            pairs.append((relation["referenceObjectKey"], relation["subjectObjectKey"]))
        for subject, reference in pairs:
            for variant in relation_variants[relation["source"]]:
                phrase = _place(
                    language,
                    variant,
                    terms[reference].model_dump(mode="json", by_alias=True),
                )
                if phrase:
                    signatures[subject].add(("location", phrase.casefold()))
    conjunction = {"es": " y ", "fr": " et ", "de": " und "}[language]
    targets = []
    for obj in objects:
        key = str(obj.id)
        choices = cues[key]
        # Prefer two-cue descriptions, while keeping a single verified cue when
        # it already distinguishes the target within the reviewed photo pack.
        compound = [pair for pair in combinations(choices, 2) if pair[0] != pair[1]]
        compound.sort(key=lambda pair: pair[0].kind == pair[1].kind)
        candidates = [*compound, *((cue,) for cue in choices)]
        options, used_texts = [], set()
        for candidate in candidates:
            required = {cue.signature for cue in candidate}
            matches = {other for other, known in signatures.items() if required <= known}
            if matches != {key}:
                continue
            text = (
                conjunction.join(
                    cue.text if index == 0 else cue.text[:1].lower() + cue.text[1:]
                    for index, cue in enumerate(candidate)
                )
                + "."
            )
            if text.casefold() in used_texts or mentions_target(text, avoid[key]):
                continue
            used_texts.add(text.casefold())
            options.append({"id": str(uuid5(obj.id, "room-clue-v1:" + text)), "text": text})
            if len(options) == 4:
                break
        if options:
            targets.append({"objectKey": key, "clueOptions": options})
    if len(targets) < 2:
        raise RoomClueError(
            "This photo needs two clearly distinguishable objects. Review their colours "
            "and relationships, or choose another photo."
        )
    return {"version": 1, "title": title, "objects": markers, "targets": targets}
