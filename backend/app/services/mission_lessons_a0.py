"""Closed-content payloads and lesson tasks for the A0 scene missions.

Only confirmed objects whose English label has a reviewed noun, and whose
session word teaches that same noun, are approved. Every target-language string
a lesson may show is listed in the payload's ``approvedSentenceChunks``.
"""

from __future__ import annotations

import random
import re

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0 import SLOT
from app.services import a0_lexicon as lex
from app.services.mission_eligibility import countable_groups
from app.services.mission_lessons import build_mission_task
from app.services.mission_lessons_m02 import scene_markers
from app.services.quantities import english_plural

_ARTICLE = re.compile(
    r"^(?:el|la|los|las|un|una|le|les|l'|l’|une|der|die|das|ein|eine)\s*", re.IGNORECASE,
)
_ENGLISH_ARTICLE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)
_EXPLANATIONS = {
    "M01": "Learn each object's name, then say what it is.",
    "M02": "Learn the names, then find each object in your photo.",
    "M03": "Learn one, two and three, then say how many.",
}
_M13_EXPLANATIONS = {
    "es": "In Spanish, each noun goes with el or la. Learn them as a pair.",
    "fr": "In French, each noun goes with le, la or l'. Learn them as a pair.",
    "de": "In German, each noun goes with der, die or das. Learn them as a pair.",
    "ko": "In Korean, a noun ending in a consonant takes 이에요; "
          "one ending in a vowel takes 예요.",
}
_EVALUATIONS = {
    "matchName": (["recognise-name"], "recognition", ["name-matches-object"]),
    "confirmName": (["identify-object"], "recognition", ["identifies-object"]),
    "buildIdentify": (["identify-object"], "construction", ["identifies-object"]),
    "findNamed": (["find-object"], "recognition", ["finds-named-object"]),
    "chooseName": (["recognise-name"], "recognition", ["distinguishes-names"]),
    "listenSelect": (["find-object"], "recognition", ["finds-named-object"]),
    "countGroup": (["count-small-group"], "recognition", ["count-matches-photo"]),
    "matchChunk": (["number-noun-chunk"], "recognition", ["chunk-matches-count"]),
    "buildChunk": (["number-noun-chunk"], "construction", ["chunk-matches-count"]),
    "chooseChunk": (["noun-word-pair"], "recognition", ["chooses-paired-word"]),
    "matchSpoken": (["noun-word-pair"], "recognition", ["matches-spoken-chunk"]),
    "fillSlot": (["noun-word-pair"], "recognition", ["chooses-paired-word"]),
}
_NAME_PURPOSES = {"matchName", "findNamed", "chooseName", "listenSelect", "matchSpoken"}
_MARKER_PURPOSES = {"matchName", "findNamed", "listenSelect", "matchSpoken"}


def taught_noun(word) -> str:
    """The session word's noun without a leading article."""
    return fold(_ARTICLE.sub("", word.display_text.strip()))


def _english(label):
    return _ENGLISH_ARTICLE.sub("", label.strip()).casefold()


def _a(noun):
    return f"an {noun}" if noun[:1] in "aeiou" else f"a {noun}"


def _object_row(language, obj, noun, marker, plurals_taught):
    english = _english(obj.label)
    forms = lex.form_options(language, noun, plurals_taught)
    form = lex.form(language, noun)
    return dict(
        key=str(obj.id), marker=marker, source=english, label=english.capitalize(),
        noun=noun.noun, gender=noun.gender, plural=noun.plural,
        elides=noun.elides, batchim=noun.batchim,
        name=lex.name_chunk(language, noun),
        identify=lex.identify_sentence(language, noun),
        isIt=lex.is_it_question(language, noun),
        find=lex.find_prompt(language, noun),
        chunk=lex.chunk(language, noun),
        form=form,
        slotTemplate=lex.join(language, SLOT, noun.noun),
        formChoices=[
            dict(form=item, chunk=lex.join(language, item, noun.noun),
                 plural=lex.plural_only(language, item))
            for item in forms
        ],
    )


def _translations(language, row):
    english = row["source"]
    return {
        row["name"]: english if language == "ko" else f"the {english}",
        row["identify"]: f"This is {_a(english)}.",
        row["isIt"]: f"Is this {_a(english)}?",
        row["find"]: f"Find the {english}.",
        row["chunk"]: f"It's {_a(english)}." if language == "ko" else f"the {english}",
        row["slotTemplate"]: f"the {english}" if language != "ko" else f"It's {_a(english)}.",
    }


def _approved(mission, language, objects, words, review_markers, plurals_taught):
    """Confirmed objects with a reviewed noun the session taught, one per label."""
    _ordered, markers = scene_markers(objects, review_markers)
    numbers = {row["key"]: row["marker"] for row in markers}
    rows, labels = [], set()
    for obj, word in zip(objects, words, strict=True):
        noun = lex.reviewed_noun(_english(obj.label), language)
        label = _english(obj.label)
        if noun is None or label in labels or taught_noun(word) != fold(noun.noun):
            continue
        labels.add(label)
        rows.append(_object_row(language, obj, noun, numbers[str(obj.id)], plurals_taught))
    return sorted(rows, key=lambda row: row["marker"])


def a0_payload(
    mission, language, objects, _relations, words, _translated_scene, counts, progress,
    session_id, review_markers=None, context=None,
):
    language = language.lower()
    plurals_taught = bool((progress or {}).get("plurals_taught"))
    rows = _approved(mission, language, objects, words, review_markers, plurals_taught)
    payload = dict(
        targetLanguage=language, missionId=mission.mission_id,
        practiceLevel=str(mission.practice_level), contentVersion=mission.content_version,
        seed=f"{session_id}:{mission.mission_id}-A0", title=mission.title,
        pluralsTaught=plurals_taught, yesNo=list(lex.YES_NO[language]),
        whatIsThis=lex.WHAT_IS_THIS[language], group=None, focus=[],
        approvedNumberWords={}, quantityChunks={}, howMany=None,
    )
    context = context or {}
    translations = {lex.WHAT_IS_THIS[language]: "What is this?"}
    if mission.mission_id == "M03":
        rows = _m03_group(payload, mission, language, rows, counts, translations)
    else:
        learner_facts = context.get("learner_facts") or {}
        if mission.mission_id == "M04":
            preferred = [str(learner_facts.get("ownedObjectId") or "")]
        elif mission.mission_id == "M05":
            preference = learner_facts.get("preference") or learner_facts
            preferred = [
                str(item) for item in preference.get("sceneObjectIds", [])
            ] + [str(preference.get("chosenObjectId") or "")]
        else:
            preferred = []
        rank = {key: index for index, key in enumerate(dict.fromkeys(preferred))}
        rows.sort(key=lambda row: (
            rank.get(row["key"], len(rank)),
            row["marker"],
        ))
        rows = rows[:3]
        if len(rows) >= 2:
            payload["focus"] = _focus(payload, rows)
    if mission.mission_id in {"M04", "M05"}:
        payload["learnerFacts"] = context.get("learner_facts") or {}
    for row in rows:
        translations.update(_translations(language, row))
    chunks = [*translations, *(row["chunk"] for row in rows)]
    if mission.mission_id == "M13":
        chunks += [item["chunk"] for row in rows for item in row["formChoices"]]
    payload.update(
        approvedObjects=rows,
        approvedTranslations=translations,
        approvedNounForms={row["key"]: dict(singular=row["noun"], plural=row["plural"])
                           for row in rows},
        approvedArticlesOrEndings=sorted({
            item["form"] for row in rows for item in row["formChoices"]
        }) if mission.mission_id == "M13" else [],
        approvedSentenceChunks=list(dict.fromkeys(chunks)),
    )
    return payload


def _focus(payload, rows):
    """Two focus objects; M13 prefers two that take different words."""
    ordered = list(rows)
    random.Random(f"{payload['seed']}:focus").shuffle(ordered)
    first = ordered[0]
    if payload["missionId"] == "M13":
        second = next((row for row in ordered[1:] if row["form"] != first["form"]), ordered[1])
    else:
        second = ordered[1]
    return [first["key"], second["key"]]


def _m03_group(payload, mission, language, rows, counts, translations):
    """The one learner-counted group of 2 or 3 with an approved noun."""
    by_key = {row["key"]: row for row in rows}
    usable = [group for group in countable_groups(mission, counts) if group["quantity"] in (2, 3)]
    if len(usable) != 1:
        return []
    counted = usable[0]
    object_ids = [str(item) for item in counted["sceneObjectIds"]]
    key = next((item for item in object_ids if item in by_key), None)
    if key is None:
        return []
    row = by_key[key]
    noun = lex.reviewed_noun(row["source"], language)
    english = row["source"]
    words, chunks = {}, {}
    for number in (1, 2, 3):
        words[str(number)] = lex.number_word(language, noun, number)
        chunks[str(number)] = lex.quantity_chunk(language, noun, number)
        translations[words[str(number)]] = lex.ENGLISH_NUMBERS[number]
        translations[chunks[str(number)]] = (
            f"one {english}" if number == 1
            else f"{lex.ENGLISH_NUMBERS[number]} {english_plural(english)}"
        )
    how_many = lex.how_many(language, noun)
    translations[how_many] = f"How many {english_plural(english)}?"
    payload.update(
        approvedNumberWords=words, quantityChunks=chunks, howMany=how_many,
        group=dict(
            key=key, objectIds=object_ids, boardObjectId=key,
            quantity=counted["quantity"], confirmedQuantity=counted["quantity"],
        ),
    )
    return [row]


def a0_ready(payload):
    if payload["missionId"] == "M03":
        return payload["group"] is not None
    return len(payload["focus"]) == 2


def _prep(payload):
    rows = payload["approvedObjects"]
    translations = payload["approvedTranslations"]
    mission_id = payload["missionId"]

    def card(text, key=None):
        return dict(text=text, translation=translations.get(text), scene_object_id=key)

    if mission_id == "M03":
        row = rows[0]
        chunks = payload["quantityChunks"]
        return [
            *(card(payload["approvedNumberWords"][str(n)]) for n in (1, 2, 3)),
            *(card(chunks[str(n)], row["key"]) for n in (1, 2, 3)),
        ]
    focus = {key: row for row in rows for key in [row["key"]]}
    first = focus[payload["focus"][0]]
    names = [card(row["chunk"] if mission_id == "M13" else row["name"], row["key"])
             for row in rows]
    if mission_id == "M01":
        return [*names, card(payload["whatIsThis"]), card(first["identify"], first["key"])]
    if mission_id == "M02":
        return [*names, card(first["find"], first["key"])]
    return names


def _corrections(payload, question, label):
    rows = {row["key"]: row for row in payload["approvedObjects"]}
    target = rows[question.object_key]
    purpose = question.purpose
    wrong = [option for option in question.options
             if option.option_id != question.correct_option_id]
    if purpose in _MARKER_PURPOSES:
        return [
            dict(
                mistake="wrongObject", answers=[option.option_id], correction=label,
                explanation=(
                    f"Marker {option.label} is the "
                    f"{rows[question.marker_keys[option.option_id]]['source']}; "
                    f"{question.prompt} is marker {label}."
                ),
            )
            for option in wrong
        ], f"{question.prompt}: marker {label}."
    if purpose == "confirmName":
        meaning = f"This is {_a(target['source'])}: {target['identify']}"
        return [dict(mistake="wrongObject", answers=[option.option_id], correction=label,
                     explanation=meaning) for option in wrong], meaning
    if purpose in {"chooseName"}:
        return [dict(mistake="wrongWord", answers=[option.option_id], correction=label,
                     explanation=f"This is {target['name']}.") for option in wrong], None
    if purpose in {"countGroup", "matchChunk"}:
        note = f"{label} — {payload['approvedTranslations'].get(label, label)}."
        return [dict(mistake="wrongQuantity", answers=[option.option_id], correction=label,
                     explanation=note) for option in wrong], note
    if purpose in {"chooseChunk", "fillSlot"}:
        if payload["targetLanguage"] == "ko":
            ending = "a consonant" if target["batchim"] else "a vowel"
            note = (
                f"{target['noun']} ends in {ending}, so it takes {target['form']}: "
                f"{target['chunk']}."
            )
        else:
            note = f"{target['noun']} goes with {target['form']}: {target['chunk']}."
        return [dict(mistake="wrongWord", answers=[option.option_id], correction=label,
                     explanation=note) for option in wrong], (
            target["chunk"] if purpose == "fillSlot" else note
        )
    return [dict(mistake="wordOrder", correction=question.correct_text,
                 explanation=f"Build: {question.correct_text}")], None


def a0_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    statement_correct = {}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        corrections, correct_note = _corrections(payload, question, label)
        if question.statement_true is not None:
            statement_correct[question.question_id] = question.statement_true
        return dict(
            target_ids=target_ids, evidence_type=evidence_type, rubric_criterion_ids=criteria,
            vocabulary_item_ids=(
                [vocabulary_id]
                if vocabulary_id and question.purpose in _NAME_PURPOSES else []
            ),
            corrections=corrections, correct_note=correct_note,
        )

    def shown(question):
        fields = dict(
            section=question.section, instruction=question.instruction,
            prompt_translation=question.prompt_translation,
            audio_text=question.audio_text,
        )
        if question.interaction_type == "multipleChoice":
            fields["keep_option_order"] = True
        if question.listen_first:
            fields["listen_first"] = True
        if question.marker_keys is not None:
            fields["marker_object_ids"] = question.marker_keys
        elif question.display_count is not None:
            fields.update(display_count=question.display_count,
                          board_object_id=question.board_object_id)
        elif question.group_object_ids:
            fields.update(scene_object_id=question.object_key,
                          group_object_ids=question.group_object_ids)
        else:
            fields["scene_object_id"] = question.object_key
        if question.slot_template:
            fields.update(slot_template=question.slot_template,
                          complete_chunk=question.complete_chunk)
        return fields

    explanation = (
        _M13_EXPLANATIONS[payload["targetLanguage"]] if mission.mission_id == "M13"
        else _EXPLANATIONS[mission.mission_id]
    )
    task = build_mission_task(
        session_id, mission, f"a0{mission.mission_id}", result, evaluate, shown,
        content_fields=dict(prep=_prep(payload), explanation=explanation),
    )
    return task.model_copy(update={
        "answer_key": task.answer_key.model_copy(update={"statement_correct": statement_correct}),
    })
