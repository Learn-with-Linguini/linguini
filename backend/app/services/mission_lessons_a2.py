"""Approved-fact payloads and deterministic A2 mission lesson builders."""

import random
from uuid import UUID

from app.ai.features.learning_tasks.mission import tokens
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.services.ispy_clue_frames import _with_article
from app.services.mission_eligibility import (
    REVIEWED_COLOURS,
    REVIEWED_POSITIONS,
    agreed_attribute,
    attribute_contrasts,
)
from app.services.mission_facts_a2 import _roleplay_selection, approved_facts
from app.services.mission_lessons import build_mission_task
from app.services.quantities import NUMBER_WORDS

_ATTRIBUTE_ENGLISH = {
    "big": "big",
    "small": "small",
    "long": "long",
    "short": "short",
    "round": "round",
    "square": "square",
    "rectangular": "rectangular",
    "wooden": "wooden",
    "metal": "metal",
    "plastic": "plastic",
    "glass": "glass",
    "fabric": "fabric",
    "stone": "stone",
    "striped": "striped",
    "spotted": "spotted",
    "open": "open",
    "closed": "closed",
    "empty": "empty",
    "full": "full",
    "clean": "clean",
    "dirty": "dirty",
    "red": "red",
    "white": "white",
    "black": "black",
    "yellow": "yellow",
    "purple": "purple",
    "gold": "gold",
    "silver": "silver",
    "blue": "blue",
    "green": "green",
    "grey": "grey",
    "gray": "grey",
    "brown": "brown",
    "pink": "pink",
    "orange": "orange",
    "beige": "beige",
}
_CONNECTOR = {"es": "y", "fr": "et"}
_ALSO = {"es": "También", "fr": "Il y a aussi"}
_LOCATION_VERB = {"es": "está", "fr": "est"}
_POSSESSIVE = {
    "es": {"masculine": "mi", "feminine": "mi"},
    "fr": {"masculine": "mon", "feminine": "ma"},
}
_SECTIONS = {
    "M01": (
        "Task 1 · Notice the facts",
        "Task 2 · Describe the scene",
        "Task 3 · Check a detail",
    ),
    "M02": (
        "Task 1 · Understand the clues",
        "Task 2 · Find the object",
        "Task 3 · Name the target",
    ),
    "M03": (
        "Task 1 · Count the groups",
        "Task 2 · Compare the quantities",
        "Task 3 · Correct the count",
    ),
    "M04": (
        "Task 1 · Meet the role-play",
        "Task 2 · Clarify ownership",
        "Task 3 · Describe your belonging",
    ),
}
_META = {
    "M01": {
        "chooseSceneMarker": (
            ["identify-scene-object"],
            "objectSelection",
            ["scene-object-matches-fact"],
        ),
        "buildSceneFact": (
            ["describe-scene-facts"],
            "construction",
            ["scene-sentence-matches-facts"],
        ),
        "chooseSceneDescription": (
            ["describe-scene-facts"],
            "recognition",
            ["scene-sentence-matches-facts"],
        ),
        "buildSceneDescription": (
            ["connect-scene-facts"],
            "construction",
            ["scene-facts-connected"],
        ),
        "followUpSceneFact": (["follow-up-scene-fact"], "recognition", ["scene-follow-up-matches"]),
    },
    "M02": {
        "readAttributeClue": (["understand-target-clues"], "recognition", ["target-clue-matches"]),
        "buildLocationClue": (["understand-target-clues"], "construction", ["target-clue-matches"]),
        "chooseUniqueTarget": (
            ["find-target-object"],
            "objectSelection",
            ["both-clues-find-target"],
        ),
        "clarifyDistractor": (["clarify-target"], "recognition", ["clarification-corrects-target"]),
        "buildTargetSentence": (
            ["name-located-target"],
            "construction",
            ["target-is-named-and-located"],
        ),
    },
    "M03": {
        "countGroup": (["understand-counts"], "recognition", ["count-matches-photo"]),
        "buildQuantity": (["describe-counts"], "construction", ["quantity-sentence-matches"]),
        "compareGroups": (["compare-counts"], "recognition", ["comparison-direction-correct"]),
        "correctRoleplayCount": (
            ["correct-count-mistake"],
            "recognition",
            ["count-correction-correct"],
        ),
        "buildComparison": (["compare-counts"], "construction", ["comparison-direction-correct"]),
    },
    "M04": {
        "chooseAssignedObject": (
            ["identify-owned-object"],
            "objectSelection",
            ["assigned-object-matches"],
        ),
        "choosePossessive": (["use-possessive"], "recognition", ["possessive-agrees"]),
        "clarifyOwnership": (["clarify-ownership"], "recognition", ["ownership-clarified"]),
        "buildBelonging": (["describe-belonging"], "construction", ["belonging-described"]),
        "buildOwnershipDescription": (
            ["describe-belonging"],
            "construction",
            ["belonging-described"],
        ),
    },
}
_EXTRA_TEXT = {
    "es": {
        "no": "No",
        "yes": "Sí",
        "es": "es",
        "está": "está",
        "hay": "hay",
        "not": "no",
        "attribute": "atributo",
        "existence": "objeto",
    },
    "fr": {
        "no": "Non",
        "yes": "Oui",
        "es": "est",
        "está": "est",
        "hay": "Il y a",
        "not": "pas",
        "attribute": "détail",
        "existence": "objet",
    },
}


def _fold(text):
    return " ".join(str(text).replace("’", "'").casefold().split())


def _joined(chunks):
    text = ""
    for chunk in chunks:
        if chunk in {".", ",", "?", "!", ";", ":"}:
            text = text.rstrip() + chunk
        elif text.endswith(("'", "’")):
            text += chunk
        else:
            text = f"{text} {chunk}".strip()
    return text


_PHRASE_CONNECTORS = {
    "es": {"y", "que", "pero", "también"},
    "fr": {"et", "que", "mais", "aussi"},
}


def _phrase_chunks(text, language):
    chunks = []
    current = []

    def flush():
        if current:
            chunks.append(_joined(current))
            current.clear()

    for token in tokens(text):
        if token in {".", ",", "?", "!", ";", ":"}:
            flush()
            chunks.append(token)
        elif _fold(token) in _PHRASE_CONNECTORS[language]:
            flush()
            chunks.append(token)
        else:
            current.append(token)
    flush()
    return chunks


def _object_map(facts):
    return {row["key"]: row for row in facts["approvedObjects"]}


def _attribute_map(facts):
    return {row["key"]: row for row in facts["approvedAttributes"]}


def _relation_map(facts):
    return {row["key"]: row for row in facts["approvedRelationships"]}


def _group_map(facts):
    return {row["key"]: row for row in facts["approvedCountedGroups"]}


def _sentence_chunks(text, *, distractors=(), rng, language=None, phrase_chunks=False):
    answer = _phrase_chunks(text, language) if phrase_chunks else tokens(text)
    if phrase_chunks:
        distractors = [
            chunk
            for distractor in distractors
            for chunk in _phrase_chunks(distractor, language)
        ]
    else:
        distractors = [token for distractor in distractors for token in tokens(distractor)]
    bank = [*answer, *distractors]
    rng.shuffle(bank)
    return dict(
        correct_text=text, answer_chunks=answer, token_bank=bank, distractor_chunks=distractors
    )


def _option_rows(question_id, rows, correct_id, rng):
    options = [{"option_id": option_id, "label": label} for option_id, label, *_ in rows]
    rng.shuffle(options)
    marker_ids = {option_id: object_key for option_id, _label, object_key in rows if object_key}
    return options, marker_ids or None


def _mc(
    payload,
    qid,
    purpose,
    prompt,
    rows,
    correct_id,
    object_key,
    section,
    *,
    marker_ids=None,
    group_object_ids=None,
    roleplay_premise=None,
    translation=None,
    target_language_text=(),
    option_language="target",
):
    rng = random.Random(f"{payload['seed']}:{qid}")
    options = [{"option_id": option_id, "label": label} for option_id, label in rows]
    rng.shuffle(options)
    return MissionA2Question(
        question_id=qid,
        purpose=purpose,
        prompt=prompt,
        interaction_type="multipleChoice",
        options=options,
        correct_option_id=correct_id,
        object_key=object_key,
        section=section,
        marker_object_ids=(
            {key: str(value) for key, value in marker_ids.items()} if marker_ids else None
        ),
        roleplay_premise=roleplay_premise,
        group_object_ids=[str(value) for value in group_object_ids or []],
        translation=translation,
        target_language_text=list(target_language_text),
        option_language=option_language,
    )


def _build(
    payload,
    qid,
    purpose,
    prompt,
    text,
    object_key,
    section,
    *,
    distractors=(),
    group_object_ids=None,
    translation=None,
    roleplay_premise=None,
    planning_facts=None,
    target_language_text=(),
    phrase_chunks=False,
):
    rng = random.Random(f"{payload['seed']}:{qid}")
    chunks = _sentence_chunks(
        text,
        distractors=distractors,
        rng=rng,
        language=payload["targetLanguage"],
        phrase_chunks=phrase_chunks,
    )
    return MissionA2Question(
        question_id=qid,
        purpose=purpose,
        prompt=prompt,
        interaction_type="sentenceBuilding",
        object_key=object_key,
        section=section,
        group_object_ids=[str(value) for value in group_object_ids or []],
        translation=translation,
        roleplay_premise=roleplay_premise,
        planning_facts=planning_facts or [],
        target_language_text=list(target_language_text),
        **chunks,
    )


def _indefinite(language, obj):
    article = {
        "es": {"masculine": "un", "feminine": "una"},
        "fr": {"masculine": "un", "feminine": "une"},
    }[language][obj["gender"]]
    return _with_article(article, obj["bareNoun"])


def _object_with_attribute(obj, attribute):
    article, bare = obj["article"], obj["bareNoun"]
    if attribute["before"]:
        return f"{article} {attribute['form']} {bare}"
    return f"{article} {bare} {attribute['form']}"


def _existence(language, obj, attribute=None, *, also=False):
    noun = _indefinite(language, obj)
    if attribute:
        if attribute["before"]:
            noun = _indefinite(
                language,
                {
                    **obj,
                    "bareNoun": f"{attribute['form']} {obj['bareNoun']}",
                },
            )
        else:
            noun = f"{noun} {attribute['form']}"
    if language == "es":
        prefix = "También hay" if also else "Hay"
    else:
        prefix = "Il y a aussi" if also else "Il y a"
    return f"{prefix} {noun}."


def _relation_sentence(language, subject, relation):
    return f"{subject['nounPhrase']} {_LOCATION_VERB[language]} {relation['phrase']}."


def _english_fact(facts, kind, row):
    objects = _object_map(facts)
    if kind == "attribute":
        return f"{objects[row['objectKey']]['englishLabel']} is {row['value']}."
    if kind == "relation":
        return (
            f"{objects[row['subjectKey']]['englishLabel']} is {row['position']} "
            f"{objects[row['referenceKey']]['englishLabel']}."
        )
    return f"{objects[row['key']]['englishLabel']} is in the scene."


def _m01_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    progress,
    session_id,
    review_markers,
):
    facts = approved_facts(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        (),
        progress,
        session_id,
        review_markers,
    )
    attributes = facts["approvedAttributes"]
    scene_objects = facts["approvedObjects"]
    relationships = facts["approvedRelationships"]
    if (not attributes and not relationships) or len(scene_objects) < 3:
        return None
    first_kind = "attribute" if attributes else "relation"
    f1 = attributes[0] if attributes else relationships[0]
    first_object_key = f1["objectKey"] if first_kind == "attribute" else f1["subjectKey"]
    f1_obj = _object_map(facts)[first_object_key]
    relation = (
        next((row for row in relationships if row["subjectKey"] == first_object_key), None)
        if first_kind == "attribute"
        else f1
    )
    if first_kind == "attribute" and relation:
        f2_kind, f2 = "relation", relation
        used = {f1_obj["key"], relation["referenceKey"]}
    else:
        f2_obj = next(
            row for row in scene_objects
            if row["key"] != f1_obj["key"]
            and (not relation or row["key"] == relation["referenceKey"])
        )
        f2_kind, f2 = "existence", {"key": f2_obj["key"]}
        used = {f1_obj["key"], f2_obj["key"]}
    f3_obj = next(
        row
        for row in scene_objects
        if row["key"] not in used
        and _fold(row["englishLabel"])
        not in {_fold(_object_map(facts)[key]["englishLabel"]) for key in used}
    )
    fact3 = {"key": f3_obj["key"]}
    f1_sentence = (
        _existence(language, f1_obj, f1)
        if first_kind == "attribute"
        else _relation_sentence(language, f1_obj, f1)
    )
    if f2_kind == "relation":
        f2_sentence = _relation_sentence(language, f1_obj, f2)
    else:
        f2_sentence = _existence(language, _object_map(facts)[f2["key"]])
    f3_sentence = _existence(language, f3_obj, also=True)
    q3 = f"{f1_sentence[:-1]} {_CONNECTOR[language]} {f3_sentence[0].lower()}{f3_sentence[1:]}"
    if language == "es":
        false_existence = f"No hay {_indefinite(language, f3_obj)}."
    else:
        false_existence = f"Il n'y a pas de {f3_obj['bareNoun']}."
    if first_kind == "attribute":
        alternate = (
            ("blue" if f1["value"] == "red" else "red")
            if f1["kind"] == "colour"
            else next(iter(attribute_contrasts(f1["kind"], f1["value"])), None)
        )
        alt_form = None
        if alternate:
            alt_agreement = agreed_attribute(f1["kind"], alternate, language, f1_obj["gender"])
            alt_form = alt_agreement[0] if alt_agreement else None
        if alt_form:
            false_obj = _object_with_attribute(
                f1_obj, {**f1, "form": alt_form, "before": alt_agreement[1]}
            )
            false_first = f"{_EXTRA_TEXT[language]['hay']} {false_obj}."
        else:
            false_first = (
                f"Hay {_indefinite(language, f1_obj)} que no es {f1['form']}."
                if language == "es"
                else f"Il y a {_indefinite(language, f1_obj)} qui n'est pas {f1['form']}."
            )
    else:
        false_first = (
            f"{f1_obj['nounPhrase']} no está {f1['phrase']}."
            if language == "es"
            else f"{f1_obj['nounPhrase']} n'est pas {f1['phrase']}."
        )
    wrong_one = (
        f"{false_first[:-1]} {_CONNECTOR[language]} {f3_sentence[0].lower()}{f3_sentence[1:]}"
    )
    wrong_two = f"{f1_sentence[:-1]} {_CONNECTOR[language]} {false_existence}"
    full = " ".join((f1_sentence, f2_sentence, f3_sentence))
    detail_prompt = (
        f"¿De qué color es {f1_obj['nounPhrase']}?"
        if language == "es" and f1["kind"] == "colour"
        else f"De quelle couleur est {f1_obj['nounPhrase']} ?"
        if language == "fr" and f1["kind"] == "colour"
        else f"¿Cómo es {f1_obj['nounPhrase']}?"
        if language == "es"
        else f"Comment est {f1_obj['nounPhrase']} ?"
    ) if first_kind == "attribute" else (
        f"¿Dónde está {f1_obj['nounPhrase']}?"
        if language == "es"
        else f"Où est {f1_obj['nounPhrase']} ?"
    )
    planning = [
        _english_fact(facts, first_kind, f1),
        _english_fact(facts, f2_kind, f2),
        _english_fact(facts, "existence", fact3),
    ]
    return {
        "approvedFacts": facts,
        "selection": {
            "attributeKey": f1["key"] if first_kind == "attribute" else None,
            "relationKey": relation["key"] if relation else None,
            "firstFactKind": first_kind,
            "secondObjectKey": f2["key"],
            "thirdObjectKey": f3_obj["key"],
        },
        "targetLanguage": language,
        "missionId": "M01",
        "practiceLevel": "A2",
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M01-A2",
        "facts": {
            "first": f1_sentence,
            "second": f2_sentence,
            "third": f3_sentence,
            "description": full,
            "falseFirst": false_first,
            "q3": q3,
            "wrongOne": wrong_one,
            "wrongTwo": wrong_two,
            "detailPrompt": detail_prompt,
            "attribute": f1 if first_kind == "attribute" else None,
            "relation": f1 if first_kind == "relation" else relation,
            "firstKind": first_kind,
            "firstObject": f1_obj,
            "thirdObject": f3_obj,
        },
        "planningFacts": planning,
    }


def _m02_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    progress,
    session_id,
    review_markers,
):
    facts = approved_facts(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        (),
        progress,
        session_id,
        review_markers,
    )
    selection = _roleplay_selection(
        mission,
        facts["approvedObjects"],
        facts["approvedAttributes"],
        facts["approvedRelationships"],
        facts["approvedCountedGroups"],
        session_id,
    )
    if not selection:
        return None
    attr = _attribute_map(facts)[selection["attributeKey"]]
    relation = _relation_map(facts)[selection["relationshipKey"]]
    objects_by_key = _object_map(facts)
    target = objects_by_key[selection["targetObjectKey"]]
    distractor = objects_by_key[selection["distractorObjectKey"]]
    adjective = attr["form"]
    if language == "es":
        attribute_clue = f"Es {adjective}."
        location_clue = f"Está {relation['phrase']}."
    else:
        pronoun = "Elle" if target["gender"] == "feminine" else "Il"
        attribute_clue = f"{pronoun} est {adjective}."
        location_clue = f"{pronoun} est {relation['phrase']}."
    full_clue = f"{attribute_clue} {location_clue}"
    distractor_shares_attr = any(
        row["objectKey"] == distractor["key"]
        and (row["kind"], row["value"]) == (attr["kind"], attr["value"])
        for row in facts["approvedAttributes"]
    )
    distractor_shares_relation = any(
        row["subjectKey"] == distractor["key"]
        and row["position"] == relation["position"]
        and row["referenceKey"] == relation["referenceKey"]
        for row in facts["approvedRelationships"]
    )
    if distractor_shares_attr and distractor_shares_relation:
        return None
    corrected_detail = location_clue if distractor_shares_attr else attribute_clue
    shared_detail = attribute_clue if distractor_shares_attr else location_clue
    if language == "es":
        correct_clarification = f"No, {corrected_detail[0].lower()}{corrected_detail[1:]}"
        wrong_clarification = f"No, {shared_detail[0].lower()}{shared_detail[1:]}"
        yes = "Sí."
        q1_prompt = f"{attribute_clue} ¿Qué significa?"
        q3_prompt = f"{full_clue} Toca el objeto que coincide con las dos pistas."
        q4_prompt = f"Tu amigo señala el marcador {distractor['marker']}. ¿Qué aclaras?"
        location_prompt = "Construye la segunda pista."
        target_prompt = "Nombra el objeto y di dónde está."
    else:
        correct_clarification = f"Non, {corrected_detail[0].lower()}{corrected_detail[1:]}"
        wrong_clarification = f"Non, {shared_detail[0].lower()}{shared_detail[1:]}"
        yes = "Oui."
        q1_prompt = f"{attribute_clue} Que signifie cette phrase ?"
        q3_prompt = f"{full_clue} Touche l'objet qui correspond aux deux indices."
        q4_prompt = f"Ton ami montre le repère {distractor['marker']}. Que dis-tu ?"
        location_prompt = "Construis le deuxième indice."
        target_prompt = "Nomme l'objet et indique où il se trouve."
    correct_label = f"It is {_ATTRIBUTE_ENGLISH.get(attr['value'], attr['value'])}."
    correct_folded = _fold(correct_label)
    choices = []
    for index, row in enumerate(facts["approvedAttributes"]):
        if (
            row["kind"] != attr["kind"]
            or row["key"] == attr["key"]
            or row["value"] == attr["value"]
        ):
            continue
        meaning = _ATTRIBUTE_ENGLISH.get(row["value"], row["value"])
        label = f"It is {meaning}."
        if _fold(label) != correct_folded:
            choices.append((f"meaning-{index}", label))
    for value in attribute_contrasts(attr["kind"], attr["value"]):
        meaning = _ATTRIBUTE_ENGLISH.get(value, value)
        label = f"It is {meaning}."
        if value != attr["value"] and _fold(label) != correct_folded:
            choices.append((f"meaning-{value}", label))
    # A fixed reviewed colour contrast keeps the English meanings understandable.
    if len(choices) < 2:
        for value in ("blue", "red", "black", "white"):
            if value != attr["value"] and value in _ATTRIBUTE_ENGLISH:
                label = f"It is {value}."
                if _fold(label) != correct_folded:
                    choices.append((f"meaning-{value}", label))
    choices = [("meaning-correct", correct_label), *choices]
    unique_choices = []
    seen_labels = set()
    for key, label in choices:
        if _fold(label) not in seen_labels:
            seen_labels.add(_fold(label))
            unique_choices.append((key, label))
    choices = unique_choices[:3]
    position_distractor = next(
        (
            REVIEWED_POSITIONS[pos][language]
            for pos in REVIEWED_POSITIONS
            if pos != relation["position"]
        ),
        None,
    )
    relation_tokens = tokens(location_clue)
    target_sentence = (
        f"{_object_with_attribute(target, attr)} está {relation['phrase']}."
        if language == "es"
        else f"{_object_with_attribute(target, attr)} est {relation['phrase']}."
    )
    selected_ids = [target["key"], distractor["key"]]
    for row in facts["approvedObjects"]:
        if row["key"] not in selected_ids:
            selected_ids.append(row["key"])
            break
    marker_rows = [
        (row["key"], str(row["marker"]), row["key"])
        for row in facts["approvedObjects"]
        if row["key"] in selected_ids
    ]
    marker_rows.sort(key=lambda row: int(row[1]))
    return {
        "approvedFacts": facts,
        "selection": selection,
        "targetLanguage": language,
        "missionId": "M02",
        "practiceLevel": "A2",
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M02-A2",
        "facts": {
            "attribute": attr,
            "relation": relation,
            "target": target,
            "distractor": distractor,
            "attributeClue": attribute_clue,
            "locationClue": location_clue,
            "fullClue": full_clue,
            "correctClarification": correct_clarification,
            "wrongClarification": wrong_clarification,
            "yes": yes,
            "attributePrompt": q1_prompt,
            "locationPrompt": location_prompt,
            "targetPrompt": target_prompt,
            "roleplayPremise": "Role-play: a friend is looking for an object in the photo.",
            "distractorPrompt": q4_prompt,
            "markerPrompt": q3_prompt,
            "englishChoices": choices,
            "distractorSharesAttribute": distractor_shares_attr,
            "distractorSharesRelation": distractor_shares_relation,
            "positionDistractor": position_distractor,
            "locationTokens": relation_tokens,
            "targetSentence": target_sentence,
            "markerRows": marker_rows,
        },
    }


def _m03_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    counts,
    progress,
    session_id,
    review_markers,
):
    facts = approved_facts(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        counts,
        progress,
        session_id,
        review_markers,
    )
    selection = _roleplay_selection(
        mission,
        facts["approvedObjects"],
        facts["approvedAttributes"],
        facts["approvedRelationships"],
        facts["approvedCountedGroups"],
        session_id,
    )
    groups = _group_map(facts)
    if not selection or not any(
        fact.get("kind") == "falseCount" for fact in facts["approvedRoleplayFacts"]
    ):
        return None
    first, second = groups[selection["firstGroupKey"]], groups[selection["secondGroupKey"]]
    language_words = NUMBER_WORDS[language]
    min_quantity = mission.photo_requirements.min_quantity
    max_quantity = mission.photo_requirements.max_quantity
    taught = [
        number for number in range(min_quantity, max_quantity + 1) if number in language_words
    ]
    if first["quantity"] not in taught or second["quantity"] not in taught:
        return None
    false_count = next(
        fact for fact in facts["approvedRoleplayFacts"] if fact["kind"] == "falseCount"
    )
    first_marker = _object_map(facts)[first["objectKey"]]["marker"]
    second_marker = _object_map(facts)[second["objectKey"]]["marker"]
    if language == "es":
        count_prompt = (
            f"¿Cuántos {first['plural']} hay?"
            if first["gender"] == "masculine"
            else f"¿Cuántas {first['plural']} hay?"
        )
        build_prompt = "Escribe una frase sobre el grupo marcado."
        friend_statement = f"Hay {false_count['numberWord']} {first['plural']}."
        first_sentence = f"Hay {first['numberWord']} {first['plural']}."
        second_sentence = f"Hay {second['numberWord']} {second['plural']}."
        more = first["quantity"] > second["quantity"]
        comparative = "más" if more else "menos"
        compare_sentence = f"Hay {comparative} {first['plural']} que {second['plural']}."
        reverse = f"Hay {'menos' if more else 'más'} {first['plural']} que {second['plural']}."
    else:
        count_prompt = (
            f"Combien d'{first['plural']} y a-t-il ?"
            if first["plural"][:1].casefold() in "aeiouyàâäéèêëîïôöùûü"
            else f"Combien de {first['plural']} y a-t-il ?"
        )
        build_prompt = "Construis une phrase sur le groupe marqué."
        friend_statement = f"Il y a {false_count['numberWord']} {first['plural']}."
        first_sentence = f"Il y a {first['numberWord']} {first['plural']}."
        second_sentence = f"Il y a {second['numberWord']} {second['plural']}."
        more = first["quantity"] > second["quantity"]
        comparative = "plus" if more else "moins"
        compare_sentence = f"Il y a {comparative} de {first['plural']} que de {second['plural']}."
        reverse = (
            f"Il y a {'moins' if more else 'plus'} de {first['plural']} que de {second['plural']}."
        )
    if language == "es":
        combined = (
            f"{first_sentence[:-1]} y {second['numberWord']} {second['plural']}. {compare_sentence}"
        )
    else:
        combined = (
            f"{first_sentence[:-1]} et {second['numberWord']} {second['plural']}. "
            f"{compare_sentence}"
        )
    number_options = [first["numberWord"]]
    number_options.extend(
        language_words[number]
        for number in taught
        if number not in {first["quantity"], false_count["quantity"]}
        and len(number_options) < 3
    )
    count_rows = [(f"number-{index}", word) for index, word in enumerate(number_options)]
    distractor_number = language_words[second["quantity"]]
    return {
        "approvedFacts": facts,
        "selection": selection,
        "targetLanguage": language,
        "missionId": "M03",
        "practiceLevel": "A2",
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M03-A2",
        "quantityRange": {"min": min_quantity, "max": max_quantity},
        "facts": {
            "first": first,
            "second": second,
            "firstMarker": first_marker,
            "secondMarker": second_marker,
            "countPrompt": count_prompt,
            "buildPrompt": build_prompt,
            "friendStatement": friend_statement,
            "firstSentence": first_sentence,
            "secondSentence": second_sentence,
            "compareSentence": compare_sentence,
            "reverseComparison": reverse,
            "combined": combined,
            "more": more,
            "comparative": comparative,
            "numberOptions": count_rows,
            "distractorNumber": distractor_number,
            "falseCount": false_count,
        },
    }


def _possessive(language, obj):
    if language == "es":
        return "mi"
    first = obj["bareNoun"].casefold()[:1]
    if obj["gender"] == "feminine" and first not in "aeiouyàâäéèêëîïôöùûüh":
        return "ma"
    return "mon"


def _m04_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    progress,
    session_id,
    review_markers,
):
    facts = approved_facts(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        (),
        progress,
        session_id,
        review_markers,
    )
    selection = _roleplay_selection(
        mission,
        facts["approvedObjects"],
        facts["approvedAttributes"],
        facts["approvedRelationships"],
        facts["approvedCountedGroups"],
        session_id,
    )
    if not selection:
        return None
    objects_by_key = _object_map(facts)
    assigned = objects_by_key[selection["assignedObjectKey"]]
    alternative = objects_by_key[selection["alternativeObjectKey"]]
    detail_kind = selection["detailKind"]
    if detail_kind == "attribute":
        detail = _attribute_map(facts)[selection["detailKey"]]
        assigned_detail = detail["form"]
        detail_phrase = (
            f"{assigned['nounPhrase']} {assigned_detail}"
            if not detail["before"]
            else f"{assigned['article']} {assigned_detail} {assigned['bareNoun']}"
        )
        if language == "es":
            prompt_detail = f"Es {assigned_detail}."
        else:
            pronoun = "Elle" if assigned["gender"] == "feminine" else "Il"
            prompt_detail = f"{pronoun} est {assigned_detail}."
    else:
        relation = _relation_map(facts)[selection["detailKey"]]
        detail = relation
        detail_phrase = relation["phrase"]
        prompt_detail = (
            f"Está {detail_phrase}."
            if language == "es"
            else f"{'Elle' if assigned['gender'] == 'feminine' else 'Il'} est {detail_phrase}."
        )
        assigned_detail = relation["phrase"]
    possessive = _possessive(language, assigned)
    if language == "es":
        premise = (
            f"Role-play: marker {assigned['marker']} is yours. "
            f"Marker {alternative['marker']} belongs to Marta."
        )
        choose_prompt = f"¿Cuál es tu objeto? {prompt_detail}"
        possessive_prompt = (
            f"{assigned['nounPhrase']} es tuya, no es de Marta. ¿Qué palabra indica que es tuya?"
            if assigned["gender"] == "feminine"
            else f"{assigned['nounPhrase']} es tuyo, no es de Marta. "
            "¿Qué palabra indica que es tuyo?"
        )
        demonstrative = "esta" if assigned["gender"] == "feminine" else "este"
        clarify_prompt = (
            f"Tu amigo señala el marcador {alternative['marker']}. "
            f"¿Es {demonstrative} tu {assigned['bareNoun']}?"
        )
        no_answer = f"No, es {alternative['nounPhrase']} de Marta."
        yes_answer = f"Sí, es mi {assigned['bareNoun']}."
        wrong_no_answer = f"No, es mi {assigned['bareNoun']}."
        if detail_kind == "attribute":
            answer_sentence = (
                f"{possessive.capitalize()} {assigned['bareNoun']} es {detail['form']}."
            )
        else:
            answer_sentence = (
                f"{possessive.capitalize()} {assigned['bareNoun']} está {assigned_detail}."
            )
        demonstrative = "Esa" if assigned["gender"] == "feminine" else "Ese"
        final_sentence = f"{answer_sentence} {alternative['nounPhrase']} es de Marta."
        possessive_options = [
            (("possessive-right", possessive)),
            ("possessive-marta", "su"),
            ("possessive-plural", "mis"),
        ]
    else:
        owner = "Léa"
        premise = (
            f"Role-play: marker {assigned['marker']} is yours. "
            f"Marker {alternative['marker']} belongs to {owner}."
        )
        choose_prompt = f"Quel objet est à toi ? {prompt_detail}"
        possessive_prompt = (
            f"{assigned['nounPhrase']} est à toi, pas à Léa. Quel possessif convient ?"
        )
        you_possessive = "ta" if possessive == "ma" else "ton"
        clarify_prompt = (
            f"Ton ami montre le repère {alternative['marker']}. "
            f"C'est {you_possessive} {assigned['bareNoun']} ?"
        )
        no_answer = f"Non, c'est {alternative['nounPhrase']} de {owner}."
        yes_answer = f"Oui, c'est {possessive} {assigned['bareNoun']}."
        wrong_no_answer = f"Non, c'est {possessive} {assigned['bareNoun']}."
        if detail_kind == "attribute":
            answer_sentence = (
                f"{possessive.capitalize()} {assigned['bareNoun']} est {detail['form']}."
            )
        else:
            answer_sentence = (
                f"{possessive.capitalize()} {assigned['bareNoun']} est {assigned_detail}."
            )
        final_sentence = f"{answer_sentence} {alternative['nounPhrase']} est à {owner}."
        possessive_options = [
            (
                "possessive-right" if form == possessive else f"possessive-{form}",
                form,
            )
            for form in ("ma", "mon", "mes", "sa")
        ]
    options = [
        (assigned["key"], str(assigned["marker"]), assigned["key"]),
        (alternative["key"], str(alternative["marker"]), alternative["key"]),
    ]
    return {
        "approvedFacts": facts,
        "selection": selection,
        "targetLanguage": language,
        "missionId": "M04",
        "practiceLevel": "A2",
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M04-A2",
        "facts": {
            "assigned": assigned,
            "alternative": alternative,
            "detail": detail,
            "detailKind": detail_kind,
            "possessive": possessive,
            "premise": premise,
            "choosePrompt": choose_prompt,
            "possessivePrompt": possessive_prompt,
            "clarifyPrompt": clarify_prompt,
            "noAnswer": no_answer,
            "yesAnswer": yes_answer,
            "wrongNoAnswer": wrong_no_answer,
            "answerSentence": answer_sentence,
            "finalSentence": final_sentence,
            "wrongOwnershipSentence": (
                f"{assigned['nounPhrase']} es de Marta."
                if language == "es"
                else f"{assigned['nounPhrase']} est à {owner}."
            ),
            "possessiveOptions": possessive_options,
            "markerOptions": options,
        },
    }


def a2_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    counts,
    progress,
    session_id,
    review_markers=None,
):
    language = language.lower()
    if language not in {"es", "fr"}:
        return None
    if mission.mission_id == "M01":
        return _m01_payload(
            mission,
            language,
            objects,
            relations,
            words,
            translated_scene,
            progress,
            session_id,
            review_markers,
        )
    if mission.mission_id == "M02":
        return _m02_payload(
            mission,
            language,
            objects,
            relations,
            words,
            translated_scene,
            progress,
            session_id,
            review_markers,
        )
    if mission.mission_id == "M03":
        return _m03_payload(
            mission,
            language,
            objects,
            relations,
            words,
            translated_scene,
            counts,
            progress,
            session_id,
            review_markers,
        )
    return _m04_payload(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        progress,
        session_id,
        review_markers,
    )


def _m01_questions(payload):
    f = payload["facts"]
    facts = payload["approvedFacts"]
    first, third = f["firstObject"], f["thirdObject"]
    markers = {row["key"]: str(row["marker"]) for row in facts["approvedObjects"]}
    first_marker = markers[first["key"]]
    option_rows = [
        (first["key"], first_marker, first["key"]),
        (third["key"], markers[third["key"]], third["key"]),
    ]
    marker_map = {row[0]: UUID(row[2]) for row in option_rows}
    section1, section2, section3 = _SECTIONS["M01"]
    prompt1 = (
        f"Toca el objeto que corresponde a la frase: «{f['first']}»."
        if payload["targetLanguage"] == "es"
        else f"Touche l'objet qui correspond à la phrase : « {f['first']} »."
    )
    q1 = _mc(
        payload,
        "m01-q1",
        "chooseSceneMarker",
        prompt1,
        [(object_key, label) for object_key, label, _ in option_rows],
        first["key"],
        first["key"],
        section1,
        marker_ids=marker_map,
        target_language_text=[prompt1],
    )
    prompt2 = (
        "Construye la segunda frase."
        if payload["targetLanguage"] == "es"
        else "Construis la deuxième phrase."
    )
    q2 = _build(
        payload,
        "m01-q2",
        "buildSceneFact",
        prompt2,
        f["second"],
        f["firstObject"]["key"],
        section1,
        distractors=["pero" if payload["targetLanguage"] == "es" else "mais"],
        target_language_text=[prompt2],
    )
    correct = f["q3"]
    choices = [
        ("description-correct", correct),
        ("description-attribute", f["wrongOne"]),
        ("description-existence", f["wrongTwo"]),
    ]
    q3_prompt = (
        "¿Qué descripción coincide con la foto?"
        if payload["targetLanguage"] == "es"
        else "Quelle description correspond à la photo ?"
    )
    q3 = _mc(
        payload,
        "m01-q3",
        "chooseSceneDescription",
        q3_prompt,
        choices,
        "description-correct",
        first["key"],
        section2,
        target_language_text=[q3_prompt],
    )
    q4_prompt = (
        "Describe la escena con estas frases."
        if payload["targetLanguage"] == "es"
        else "Décris la scène avec ces faits."
    )
    q4 = _build(
        payload,
        "m01-q4",
        "buildSceneDescription",
        q4_prompt,
        f["description"],
        first["key"],
        section2,
        distractors=[f["falseFirst"]],
        planning_facts=payload["planningFacts"],
        target_language_text=[q4_prompt],
        phrase_chunks=True,
    )
    attribute = f["attribute"]
    if attribute:
        attribute_options = [("detail-correct", attribute["form"])]
        values = (
            ("black", "white", "blue", "green", "red")
            if attribute["kind"] == "colour"
            else attribute_contrasts(attribute["kind"], attribute["value"])
        )
        for index, value in enumerate(values):
            if len(attribute_options) == 3:
                break
            if attribute["kind"] == "colour":
                info = REVIEWED_COLOURS.get(value, {}).get(payload["targetLanguage"])
                form = (
                    info[0 if f["firstObject"]["gender"] == "masculine" else 1]
                    if info
                    else None
                )
            else:
                agreement = agreed_attribute(
                    attribute["kind"],
                    value,
                    payload["targetLanguage"],
                    f["firstObject"]["gender"],
                )
                form = agreement[0] if agreement else None
            if form and _fold(form) not in {_fold(row[1]) for row in attribute_options}:
                attribute_options.append((f"detail-{index}", form))
    else:
        relation = f["relation"]
        reference = next(
            row for row in facts["approvedObjects"] if row["key"] == relation["referenceKey"]
        )
        attribute_options = [("detail-correct", relation["phrase"])]
        for position, expressions in REVIEWED_POSITIONS.items():
            if position == relation["position"] or len(attribute_options) == 3:
                continue
            phrase = f"{expressions[payload['targetLanguage']]} {reference['nounPhrase']}"
            if _fold(phrase) not in {_fold(row[1]) for row in attribute_options}:
                attribute_options.append((f"detail-{position}", phrase))
    q5_prompt = f["detailPrompt"]
    q5 = _mc(
        payload,
        "m01-q5",
        "followUpSceneFact",
        q5_prompt,
        attribute_options,
        "detail-correct",
        first["key"],
        section3,
        target_language_text=[q5_prompt],
    )
    return [q1, q2, q3, q4, q5]


def _m02_questions(payload):
    language = payload["targetLanguage"]
    f = payload["facts"]
    target = f["target"]
    s1, s2, s3 = _SECTIONS["M02"]
    choices = f["englishChoices"]
    correct_id = choices[0][0]
    q1 = _mc(
        payload,
        "m02-q1",
        "readAttributeClue",
        f["attributePrompt"],
        [(key, label) for key, label in choices],
        correct_id,
        target["key"],
        s1,
        translation="Choose the English meaning of the clue.",
        roleplay_premise=f["roleplayPremise"],
        target_language_text=[f["attributePrompt"]],
        option_language="en",
    )
    q2 = _build(
        payload,
        "m02-q2",
        "buildLocationClue",
        f["locationPrompt"],
        f["locationClue"],
        target["key"],
        s1,
        distractors=[f["positionDistractor"]] if f["positionDistractor"] else [],
        translation="Build the second clue without naming the object.",
        target_language_text=[f["locationPrompt"]],
    )
    marker_ids = {object_key: UUID(object_key) for object_key, _label, _key in f["markerRows"]}
    q3 = _mc(
        payload,
        "m02-q3",
        "chooseUniqueTarget",
        f["markerPrompt"],
        [(key, label) for key, label, _object in f["markerRows"]],
        target["key"],
        target["key"],
        s2,
        marker_ids=marker_ids,
        target_language_text=[f["markerPrompt"]],
    )
    q4_rows = [("clarify-correct", f["correctClarification"])]
    if f["distractorSharesAttribute"] or f["distractorSharesRelation"]:
        q4_rows.append(("clarify-shared", f["wrongClarification"]))
    q4_rows.append(("clarify-yes", f["yes"]))
    q4 = _mc(
        payload,
        "m02-q4",
        "clarifyDistractor",
        f["distractorPrompt"],
        q4_rows,
        "clarify-correct",
        target["key"],
        s2,
        target_language_text=[f["distractorPrompt"]],
        roleplay_premise=f["roleplayPremise"],
        group_object_ids=[f["distractor"]["key"]],
    )
    q5 = _build(
        payload,
        "m02-q5",
        "buildTargetSentence",
        f["targetPrompt"],
        f["targetSentence"],
        target["key"],
        s3,
        distractors=["pero" if language == "es" else "mais"],
        translation="Name the target and include its confirmed location.",
        target_language_text=[f["targetPrompt"]],
    )
    return [q1, q2, q3, q4, q5]


def _m03_questions(payload):
    language = payload["targetLanguage"]
    f = payload["facts"]
    first, second = f["first"], f["second"]
    s1, s2, s3 = _SECTIONS["M03"]
    q1_rows = f["numberOptions"]
    q1_correct = q1_rows[0][0]
    q1 = _mc(
        payload,
        "m03-q1",
        "countGroup",
        f["countPrompt"],
        [(option_id, label) for option_id, label in q1_rows],
        q1_correct,
        first["objectKey"],
        s1,
        group_object_ids=first["objectIds"],
        target_language_text=[f["countPrompt"]],
    )
    sentence2 = f["secondSentence"]
    distractor_number = f["distractorNumber"]
    q2 = _build(
        payload,
        "m03-q2",
        "buildQuantity",
        f["buildPrompt"],
        sentence2,
        second["objectKey"],
        s1,
        distractors=(
            [distractor_number] if distractor_number != second["numberWord"] else []
        ),
        group_object_ids=second["objectIds"],
        target_language_text=[f["buildPrompt"]],
    )
    comparison_rows = [
        ("comparison-correct", f["compareSentence"]),
        ("comparison-reverse", f["reverseComparison"]),
        (
            "comparison-swapped",
            f"Hay {f['comparative']} {second['plural']} que {first['plural']}."
            if language == "es"
            else f"Il y a {f['comparative']} de {second['plural']} que de {first['plural']}.",
        ),
    ]
    q3 = _mc(
        payload,
        "m03-q3",
        "compareGroups",
        "Elige la comparación correcta."
        if language == "es"
        else "Choisis la comparaison correcte.",
        comparison_rows,
        "comparison-correct",
        first["objectKey"],
        s2,
        roleplay_premise=(
            f"Group {f['firstMarker']} has {first['quantity']}; "
            f"group {f['secondMarker']} has {second['quantity']}."
        ),
        group_object_ids=list(dict.fromkeys(first["objectIds"] + second["objectIds"])),
        target_language_text=[
            "Elige la comparación correcta."
            if language == "es"
            else "Choisis la comparaison correcte."
        ],
    )
    if language == "es":
        q4_prompt = f"Tu amigo dice: «{f['friendStatement']}» ¿Qué respondes?"
        no_text = f"No, {f['firstSentence'][0].lower()}{f['firstSentence'][1:]}"
        yes_text = "Sí, tu amigo tiene razón."
    else:
        q4_prompt = f"Ton ami dit : « {f['friendStatement']} » Que réponds-tu ?"
        no_text = f"Non, {f['firstSentence'][0].lower()}{f['firstSentence'][1:]}"
        yes_text = "Oui, ton ami a raison."
    alternative_quantity = next(
        NUMBER_WORDS[language][number]
        for number in range(payload["quantityRange"]["min"], payload["quantityRange"]["max"] + 1)
        if number in NUMBER_WORDS[language]
        and number not in {first["quantity"], f["falseCount"]["quantity"]}
    )
    q4 = _mc(
        payload,
        "m03-q4",
        "correctRoleplayCount",
        q4_prompt,
        [
            ("count-correct", no_text),
            ("count-repeat", yes_text),
            (
                "count-wrong",
                f"Hay {alternative_quantity} {first['plural']}."
                if language == "es"
                else f"Il y a {alternative_quantity} {first['plural']}.",
            ),
        ],
        "count-correct",
        first["objectKey"],
        s3,
        roleplay_premise=f"Role-play: a friend says «{f['friendStatement']}».",
        group_object_ids=first["objectIds"],
        target_language_text=[q4_prompt, f["friendStatement"]],
    )
    q5 = _build(
        payload,
        "m03-q5",
        "buildComparison",
        "Describe y compara los dos grupos."
        if language == "es"
        else "Décris et compare les deux groupes.",
        f["combined"],
        first["objectKey"],
        s3,
        distractors=[f["reverseComparison"]],
        group_object_ids=list(dict.fromkeys(first["objectIds"] + second["objectIds"])),
        target_language_text=[
            "Describe y compara los dos grupos."
            if language == "es"
            else "Décris et compare les deux groupes."
        ],
        phrase_chunks=True,
    )
    return [q1, q2, q3, q4, q5]


def _m04_questions(payload):
    language = payload["targetLanguage"]
    f = payload["facts"]
    assigned, alternative = f["assigned"], f["alternative"]
    s1, s2, s3 = _SECTIONS["M04"]
    marker_map = {key: UUID(key) for key, _label, _object in f["markerOptions"]}
    q1 = _mc(
        payload,
        "m04-q1",
        "chooseAssignedObject",
        f["choosePrompt"],
        [(key, label) for key, label, _object in f["markerOptions"]],
        assigned["key"],
        assigned["key"],
        s1,
        marker_ids=marker_map,
        roleplay_premise=f["premise"],
        target_language_text=[f["choosePrompt"]],
    )
    q2 = _mc(
        payload,
        "m04-q2",
        "choosePossessive",
        f["possessivePrompt"],
        f["possessiveOptions"],
        "possessive-right",
        assigned["key"],
        s1,
        target_language_text=[f["possessivePrompt"]],
    )
    q3 = _build(
        payload,
        "m04-q3",
        "buildBelonging",
        "Describe tu objeto con un detalle confirmado."
        if language == "es"
        else "Décris ton objet avec un détail confirmé.",
        f["answerSentence"],
        assigned["key"],
        s1,
        distractors=["su" if language == "es" else "sa"],
        target_language_text=[
            "Describe tu objeto con un detalle confirmado."
            if language == "es"
            else "Décris ton objet avec un détail confirmé."
        ],
    )
    q4 = _mc(
        payload,
        "m04-q4",
        "clarifyOwnership",
        f["clarifyPrompt"],
        [
            ("owner-no", f["noAnswer"]),
            ("owner-yes", f["yesAnswer"]),
            ("owner-wrong", f["wrongNoAnswer"]),
        ],
        "owner-no",
        alternative["key"],
        s2,
        target_language_text=[f["clarifyPrompt"]],
        roleplay_premise=f["premise"],
        group_object_ids=[alternative["key"]],
    )
    q5 = _build(
        payload,
        "m04-q5",
        "buildOwnershipDescription",
        "Aclara cuál es tu objeto y descríbelo."
        if language == "es"
        else "Précise quel objet est à toi et décris-le.",
        f["finalSentence"],
        assigned["key"],
        s3,
        distractors=[f["wrongOwnershipSentence"]],
        target_language_text=[
            "Aclara cuál es tu objeto y descríbelo."
            if language == "es"
            else "Précise quel objet est à toi et décris-le."
        ],
        phrase_chunks=True,
    )
    return [q1, q2, q3, q4, q5]


def build_a2_result(payload, mission_id):
    """Build five seeded questions from one mission's approved facts."""
    questions = {
        "M01": _m01_questions,
        "M02": _m02_questions,
        "M03": _m03_questions,
        "M04": _m04_questions,
    }[mission_id](payload)
    title = {
        "M01": "Describe the scene",
        "M02": "Help someone find it",
        "M03": "Describe and compare quantities",
        "M04": "Identify your belonging clearly",
    }[mission_id]
    return MissionA2Result(title=title, questions=questions)


def _mission_payload(
    mission,
    language,
    objects,
    relations,
    words,
    translated_scene,
    counts,
    progress,
    session_id,
    review_markers=None,
):
    return a2_payload(
        mission,
        language,
        objects,
        relations,
        words,
        translated_scene,
        counts,
        progress or {},
        session_id,
        review_markers,
    )


def _ready(payload):
    return bool(payload and payload.get("approvedFacts", {}).get("approvedObjects"))


def _task(session_id, mission, payload, result, vocabulary_ids):
    from app.schemas.tasks import SessionTask

    mission_id = mission.mission_id
    question_meta = _META[mission_id]

    def evaluate(question, _label):
        target_ids, evidence_type, criteria = question_meta[question.purpose]
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=(
                [vocabulary_ids[question.object_key]]
                if question.object_key in vocabulary_ids
                and question.purpose not in {"correctRoleplayCount", "clarifyOwnership"}
                else []
            ),
        )

    def shown(question):
        fields = {
            "section": question.section,
            "keep_option_order": True if question.interaction_type == "multipleChoice" else None,
        }
        if question.roleplay_premise:
            fields["roleplay_premise"] = question.roleplay_premise
        if question.planning_facts:
            fields["planning_facts"] = question.planning_facts
        if question.marker_object_ids:
            fields["marker_object_ids"] = {
                key: UUID(value) for key, value in question.marker_object_ids.items()
            }
        if question.group_object_ids:
            fields["group_object_ids"] = [UUID(value) for value in question.group_object_ids]
        return fields

    task = build_mission_task(
        session_id, mission, f"sceneMission{mission_id}A2", result, evaluate, shown
    )
    data = task.model_dump(by_alias=False)
    data["public_content"]["check_each_question"] = True
    data["answer_key"]["mission_state"] = {
        "approvedFacts": payload["approvedFacts"],
        "selection": payload["selection"],
        "seed": payload["seed"],
    }
    return SessionTask.model_validate(data)


def m01_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m02_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m03_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def m04_a2_task(session_id, mission, payload, result, vocabulary_ids):
    return _task(session_id, mission, payload, result, vocabulary_ids)


def a2_mission_spec(mission_id):
    """Return payload/task functions for one A2 mission registry entry."""
    return (
        _mission_payload,
        {
            "M01": m01_a2_task,
            "M02": m02_a2_task,
            "M03": m03_a2_task,
            "M04": m04_a2_task,
        }[mission_id],
        _ready,
    )
