"""Closed sets of reviewed scene facts available to A2 mission lessons."""

import random
import re

from app.ai.features.learning_tasks.mission import tokens
from app.services.ispy_clue_frames import CONTRACTIONS, DEFINITE_ARTICLES, _with_article
from app.services.mission_eligibility import (
    REVIEWED_ATTRIBUTES,
    REVIEWED_COLOURS,
    REVIEWED_POSITIONS,
    agreed_attribute,
    confirmed_attributes,
    relation_type,
)
from app.services.mission_lessons import mission_gender
from app.services.mission_lessons_m02 import _article_and_noun, scene_markers
from app.services.quantities import NUMBER_WORDS, regular_plural, taught_numbers

_CONNECTORS = {
    "es": ["y", "pero", "también"],
    "fr": ["et", "mais", "aussi"],
}
_COMPARATIVES = {
    "es": ["más", "menos", "que"],
    "fr": ["plus", "moins", "que", "de"],
}
_FUNCTION_WORDS = {
    "es": (
        "hay la el los las un una está es son y pero también no sí mi mis su esta "
        "este de dónde qué cuál cuál es una pista toca objeto es roja rojo grande "
        "pequeño describe cuántos cuántas más menos que color cómo pregunta "
        "no es tu taza mi libro tuyo tuya ese esa"
        " corresponde frase construye segunda descripción coincide con foto a "
        "escena estas frases amigo señala marcador aclaras significa elige "
        "comparación correcta dice respondes grupo marcado detalle nombra di "
        "lugar confirma confirmado pertenece las dos pistas está también "
        "palabra indica aclara descríbelo es escribe sobre grupos cuantos compara "
        "tiene razón "
    ).split(),
    "fr": (
        "il y a le la les un une des est sont et mais aussi non oui ma mon mes ta "
        "ton tes sa cette ce cet où que quelle combien plus moins de d' est-ce "
        "touche objet piste elle il rouge rouge grande petit petite décris couleur "
        "question est c'est n'est pas qui correspond phrase construis deuxième "
        "description photo scène avec ces faits touche objet comment couleur "
        "ami montre repère dis indice groupe marqué choisis comparaison correcte "
        "dit réponds les deux groupes précise quel appartient"
        " à toi possessif convient sur groupe marqué phrase compare deux aux indices a a-t-il "
        "signifie c réponds-tu "
        "réponds tu dis dis-tu nomme l'objet indique où se trouve détail confirmé "
        "décris-le raison"
    ).split(),
}


def _fold(value):
    return " ".join(str(value).replace("’", "'").casefold().split())


def _as_id(value):
    return str(value)


def _phrase(article, noun):
    return _with_article(article, noun)


def _position_phrase(language, expression, reference):
    article = reference["article"]
    words = expression.split()
    contraction = CONTRACTIONS.get(language, {}).get((words[-1].casefold(), article.casefold()))
    if contraction:
        return " ".join([*words[:-1], contraction, reference["bareNoun"]])
    return f"{expression} {_phrase(article, reference['bareNoun'])}"


def _roleplay_selection(mission, objects, attributes, relationships, groups, seed):
    object_by_key = {row["key"]: row for row in objects}
    if mission.mission_id == "M02":
        relation_rows = [
            relation
            for relation in relationships
            if relation["position"] in mission.photo_requirements.relations
        ]
        for relation in relation_rows:
            for attribute in attributes:
                if attribute["objectKey"] != relation["subjectKey"]:
                    continue
                matching = [
                    row["key"]
                    for row in objects
                    if any(
                        item["objectKey"] == row["key"]
                        and (item["kind"], item["value"]) == (attribute["kind"], attribute["value"])
                        for item in attributes
                    )
                    and any(
                        item["subjectKey"] == row["key"]
                        and item["position"] == relation["position"]
                        and item["referenceKey"] == relation["referenceKey"]
                        for item in relationships
                    )
                ]
                if len(matching) != 1:
                    continue
                distractors = [
                    row
                    for row in objects
                    if row["key"] != relation["subjectKey"]
                    and int(
                        any(
                            item["objectKey"] == row["key"]
                            and (item["kind"], item["value"])
                            == (attribute["kind"], attribute["value"])
                            for item in attributes
                        )
                    )
                    + int(
                        any(
                            item["subjectKey"] == row["key"]
                            and item["position"] == relation["position"]
                            and item["referenceKey"] == relation["referenceKey"]
                            for item in relationships
                        )
                    )
                    <= 1
                ]
                same_label = [
                    row
                    for row in distractors
                    if _fold(row["englishLabel"])
                    == _fold(object_by_key[relation["subjectKey"]]["englishLabel"])
                ]
                preferred = (
                    same_label
                    or [
                        row
                        for row in distractors
                        if (attribute["kind"], attribute["value"])
                        in {
                            (item["kind"], item["value"])
                            for item in attributes
                            if item["objectKey"] == row["key"]
                        }
                    ]
                    or distractors
                )
                if preferred:
                    distractor = preferred[0]
                    return {
                        "targetObjectKey": relation["subjectKey"],
                        "distractorObjectKey": distractor["key"],
                        "attributeKey": attribute["key"],
                        "relationshipKey": relation["key"],
                    }
    if mission.mission_id == "M04":
        for assigned in objects:
            details = [
                ("attribute", item) for item in attributes if item["objectKey"] == assigned["key"]
            ]
            details.extend(
                ("relationship", item)
                for item in relationships
                if item["subjectKey"] == assigned["key"]
            )
            for detail_kind, detail in details:
                alternatives = [row for row in objects if row["key"] != assigned["key"]]
                same_label = [
                    row
                    for row in alternatives
                    if _fold(row["englishLabel"]) == _fold(assigned["englishLabel"])
                ]
                alternatives = same_label + [row for row in alternatives if row not in same_label]
                for alternative in alternatives:
                    shared = (
                        any(
                            item["objectKey"] == alternative["key"]
                            and (item["kind"], item["value"]) == (detail["kind"], detail["value"])
                            for item in attributes
                        )
                        if detail_kind == "attribute"
                        else any(
                            item["subjectKey"] == alternative["key"]
                            and item["position"] == detail["position"]
                            and item["referenceKey"] == detail["referenceKey"]
                            for item in relationships
                        )
                    )
                    if not shared:
                        return {
                            "assignedObjectKey": assigned["key"],
                            "alternativeObjectKey": alternative["key"],
                            "detailKind": detail_kind,
                            "detailKey": detail["key"],
                        }
    if mission.mission_id == "M03" and len(groups) >= 2:
        pairs = [
            (left, right)
            for index, left in enumerate(groups)
            for right in groups[index + 1 :]
            if _fold(left["label"]) != _fold(right["label"])
            and left["quantity"] != right["quantity"]
        ]
        if pairs:
            rng = random.Random(f"{seed}:M03-A2")
            first, second = rng.choice(pairs)
            return {"firstGroupKey": first["key"], "secondGroupKey": second["key"]}
    return {}


def approved_facts(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    counted,
    progress,
    session_id,
    review_markers,
) -> dict:
    """Build the exact scene vocabulary and facts an A2 lesson may use."""
    language = language.lower()
    if language not in {"es", "fr"}:
        return {
            "approvedObjects": [],
            "approvedAttributes": [],
            "approvedRelationships": [],
            "approvedCountedGroups": [],
            "approvedRoleplayFacts": [],
            "approvedVocabulary": [],
            "approvedSentencePatterns": [],
            "approvedConnectors": [],
            "approvedComparatives": [],
        }
    terms = {term.key: term for term in getattr(translated_scene, "objects", [])}
    by_key = {}
    approved_objects = []
    _ordered, markers = scene_markers(objects, review_markers)
    marker_numbers = {row["key"]: row["marker"] for row in markers}
    for obj, word in zip(objects, words, strict=True):
        key = _as_id(obj.id)
        term = terms.get(key)
        if term is None:
            continue
        translated = term.translation.strip()
        article, bare = _article_and_noun(translated, term)
        gender = mission_gender(term, word)
        if not article:
            article = DEFINITE_ARTICLES[language].get(gender)
        if (
            not article
            or gender not in {"masculine", "feminine"}
            or not bare
            or not re.search(r"[^\W\d_]", bare)
        ):
            continue
        plural = regular_plural(language, bare)
        recorded_plural = getattr(word, "plural_form", None)
        if plural and recorded_plural and _fold(plural) != _fold(recorded_plural):
            plural = None
        row = {
            "key": key,
            "englishLabel": obj.label,
            "marker": marker_numbers[key],
            "article": article,
            "bareNoun": bare,
            "nounPhrase": _phrase(article, bare),
            "gender": gender,
            "plural": plural,
            "vocabularyItemId": _as_id(word.id),
        }
        by_key[key] = row
        approved_objects.append(row)

    from app.services.mission_eligibility import confirmed_relations, countable_groups

    allowed_relations = set(mission.photo_requirements.relations) or set(REVIEWED_POSITIONS)
    approved_attributes = []
    for obj in objects:
        key = _as_id(obj.id)
        if key not in by_key:
            continue
        for source_key, kind, value in confirmed_attributes(obj):
            agreement = agreed_attribute(kind, value, language, by_key[key]["gender"])
            if not agreement:
                continue
            form, before = agreement
            approved_attributes.append(
                {
                    "key": f"{key}:{source_key}",
                    "objectKey": key,
                    "kind": kind,
                    "value": value,
                    "form": form,
                    "before": before,
                }
            )

    relation_objects = [obj for obj in objects if _as_id(obj.id) in by_key]
    approved_relationships = []
    for relation in relations:
        subject = _as_id(relation.subject_scene_object_id)
        reference = _as_id(relation.reference_scene_object_id)
        position = relation_type(relation)
        if (
            subject not in by_key
            or reference not in by_key
            or position not in allowed_relations
            or position not in REVIEWED_POSITIONS
            or not any(
                row.id == relation.id
                for row in confirmed_relations(
                    mission.model_copy(
                        update={
                            "photo_requirements": mission.photo_requirements.model_copy(
                                update={
                                    "relations": sorted(allowed_relations),
                                }
                            ),
                        }
                    ),
                    relation_objects,
                    relations,
                )
            )
        ):
            continue
        expression = REVIEWED_POSITIONS[position][language]
        reference_term = by_key[reference]
        approved_relationships.append(
            {
                "key": _as_id(relation.id),
                "subjectKey": subject,
                "referenceKey": reference,
                "position": position,
                "expression": expression,
                "phrase": _position_phrase(language, expression, reference_term),
            }
        )

    eligible_counts = countable_groups(mission, counted)
    approved_groups = []
    for index, group in enumerate(eligible_counts):
        label = str(group.get("label", "")).strip()
        object_ids = [
            _as_id(item)
            for item in group.get("sceneObjectIds", [])
            if _as_id(item) in by_key
            and _fold(next(obj.label for obj in objects if _as_id(obj.id) == _as_id(item)))
            == _fold(label)
        ]
        representative = next((by_key[key] for key in object_ids if by_key[key]["plural"]), None)
        quantity = group.get("quantity")
        if (
            not label
            or not object_ids
            or representative is None
            or quantity not in NUMBER_WORDS[language]
        ):
            continue
        approved_groups.append(
            {
                "key": f"group:{index}:{_fold(label)}",
                "label": label,
                "objectIds": object_ids,
                "objectKey": object_ids[0],
                "nounPhrase": representative["nounPhrase"],
                "singular": representative["bareNoun"],
                "plural": representative["plural"],
                "gender": representative["gender"],
                "quantity": quantity,
                "numberWord": NUMBER_WORDS[language][quantity],
            }
        )

    seed = str(session_id)
    selection = _roleplay_selection(
        mission,
        approved_objects,
        approved_attributes,
        approved_relationships,
        approved_groups,
        seed,
    )
    roleplay_facts = []
    if mission.mission_id == "M02" and selection:
        roleplay_facts.append(
            {
                "kind": "lostObject",
                "objectKey": selection["targetObjectKey"],
                "isFictional": True,
                "source": "assignedRoleplay",
            }
        )
    elif mission.mission_id == "M03" and selection:
        first = next(row for row in approved_groups if row["key"] == selection["firstGroupKey"])
        taught, _source = taught_numbers(mission, progress)
        confirmed_quantities = {row["quantity"] for row in approved_groups}
        wrong = [number for number in taught if number not in confirmed_quantities]
        rng = random.Random(f"{seed}:M03-A2-roleplay")
        if wrong:
            wrong_quantity = rng.choice(wrong)
            roleplay_facts.append(
                {
                    "kind": "falseCount",
                    "groupKey": first["key"],
                    "quantity": wrong_quantity,
                    "numberWord": NUMBER_WORDS[language][wrong_quantity],
                    "isFictional": True,
                    "source": "assignedRoleplay",
                }
            )
    elif mission.mission_id == "M04" and selection:
        owner_name = {"es": "Marta", "fr": "Léa"}[language]
        roleplay_facts.extend(
            [
                {
                    "kind": "ownership",
                    "objectKey": selection["assignedObjectKey"],
                    "owner": "learner",
                    "isFictional": True,
                    "source": "assignedRoleplay",
                },
                {
                    "kind": "ownership",
                    "objectKey": selection["alternativeObjectKey"],
                    "owner": owner_name,
                    "isFictional": True,
                    "source": "assignedRoleplay",
                },
            ]
        )

    patterns = [
        {
            "patternId": f"mission-{mission.mission_id.lower()}-a2",
            "language": language,
            "frames": [
                "hay",
                "il y a",
                "es",
                "est",
                "está",
                "y",
                "et",
                "más",
                "plus",
                "menos",
                "moins",
                "que",
                "de",
                "mi",
                "ma",
                "mon",
                "no",
                "pas",
            ],
        }
    ]
    vocabulary = set()
    for item in _FUNCTION_WORDS[language]:
        vocabulary.update(tokens(item))
    for row in approved_objects:
        vocabulary.update(tokens(row["nounPhrase"].casefold().replace("’", "'")))
        vocabulary.update(tokens(row["bareNoun"].casefold().replace("’", "'")))
        if row["plural"]:
            vocabulary.update(tokens(row["plural"].casefold().replace("’", "'")))
    for row in approved_attributes:
        vocabulary.update(tokens(row["form"].casefold().replace("’", "'")))
    for row in approved_relationships:
        vocabulary.update(tokens(row["phrase"].casefold().replace("’", "'")))
    for row in approved_groups:
        vocabulary.update(tokens(row["numberWord"].casefold()))
    for fact in roleplay_facts:
        if fact.get("owner") not in {None, "learner"}:
            vocabulary.add(fact["owner"].casefold())
        if fact.get("numberWord"):
            vocabulary.update(tokens(fact["numberWord"].casefold()))
    for connector in _CONNECTORS[language] + _COMPARATIVES[language]:
        vocabulary.update(tokens(connector.casefold()))
    taught, _source = taught_numbers(mission, progress)
    for number in taught:
        if number in NUMBER_WORDS[language]:
            vocabulary.update(tokens(NUMBER_WORDS[language][number].casefold()))
    vocabulary.update(
        tokens(" ".join(REVIEWED_POSITIONS[pos][language] for pos in REVIEWED_POSITIONS))
    )
    for entry in REVIEWED_ATTRIBUTES.values():
        for value in entry.values():
            if forms := value.get(language):
                vocabulary.update(tokens(" ".join(forms).casefold()))
    for forms in REVIEWED_COLOURS.values():
        if language_forms := forms.get(language):
            vocabulary.update(tokens(" ".join(language_forms).casefold()))

    return {
        "approvedObjects": approved_objects,
        "approvedAttributes": approved_attributes,
        "approvedRelationships": approved_relationships,
        "approvedCountedGroups": approved_groups,
        "approvedRoleplayFacts": roleplay_facts,
        "approvedVocabulary": sorted(vocabulary),
        "approvedSentencePatterns": patterns,
        "approvedConnectors": _CONNECTORS[language],
        "approvedComparatives": _COMPARATIVES[language],
    }
