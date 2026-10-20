"""M02 (find and locate) as a pack lesson.

Questions, sections, grading and corrections are dev's existing M02 builders
(`a0_lesson_task`, `m02_lesson_task`, `m02_a2_task`); only the target-language text
comes from validated, model-generated sentences instead of per-language tables.
"""

from __future__ import annotations

import random

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0 import (
    INSTRUCTIONS,
    A0LessonResult,
    _choice_question,
    _marker_question,
)
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.ai.features.learning_tasks.mission_m02 import (
    ASK_SECTION,
    FIND_SECTION,
    M02LessonResult,
)
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m02_a2_task
from app.services.mission_lessons_m02 import m02_lesson_task

from .base import PackMission, for_level
from .common import LessonContext, SpecBuilder, check_questions, latin_of, usable_objects

MISSION_ID = "M02"
PURPOSES = {
    "A0": ["findNamed", "chooseName", "listenSelect"] * 2,
    "A1": ["findObject", "chooseLocation", "askWhere", "answerWhere"],
    "A2": [
        "readAttributeClue", "buildLocationClue", "chooseUniqueTarget",
        "clarifyDistractor", "buildTargetSentence",
    ],
}
A2_SECTIONS = (
    "Task 1 · Understand the clues", "Task 2 · Find the object", "Task 3 · Name the target",
)
ROLEPLAY_PREMISE = "Role-play: a friend is looking for an object in the photo."
MAX_MARKERS = 4
MAX_PLACES = 4
# A confirmed relation also rules out its inverse on the same pair.
_INVERSE = {
    "on": "under", "under": "on", "next_to": "next_to",
    "in_front_of": "behind", "behind": "in_front_of",
}


def relation_kind(text) -> str:
    """A relation's kind (``next_to``) from a fact or a proposed English meaning."""
    return "_".join(str(text).strip().casefold().replace("-", " ").split())


# ---------------------------------------------------------------- facts and selection


def _true_positions(subject, reference, relations):
    found = set()
    for relation in relations:
        kind = relation_kind(relation.relation)
        pair = (relation.subject_fact_id, relation.reference_fact_id)
        if pair == (subject, reference):
            found.add(kind)
        elif pair == (reference, subject) and kind in _INVERSE:
            found.add(_INVERSE[kind])
    return found


def _relation_alternatives(relation, facts, vocabulary):
    """Model-proposed positions that are false for this pair, most contrastive first."""
    true = _true_positions(relation.subject_fact_id, relation.reference_fact_id,
                           facts.scene_facts.relations)
    rows = []
    for term in vocabulary.terms:
        if term.linguistic.get("contrast-for") != relation.fact_id:
            continue
        kind = relation_kind(term.linguistic.get("relation-kind", term.source_text))
        if kind in true or any(row[0] == kind for row in rows):
            continue
        rows.append((kind, term))
    opposite = _INVERSE.get(relation_kind(relation.relation))
    rows.sort(key=lambda row: row[0] != opposite)
    return rows[: MAX_PLACES - 1]


def _a0_focus(objects, seed):
    """Two focus objects with differently named partners for the name choice."""
    ordered = list(objects)
    random.Random(f"{seed}:M02-A0").shuffle(ordered)
    pairs = []
    for target in ordered[:2]:
        other = next(
            (obj for obj in ordered
             if obj.fact_id != target.fact_id
             and obj.label.strip().casefold() != target.label.strip().casefold()),
            None,
        )
        if other is None:
            raise ValueError("M02 A0 needs two differently named objects")
        pairs.append((target, other))
    return pairs


def _a1_relation(facts, vocabulary, seed):
    objects = {obj.fact_id: obj for obj in usable_objects(facts, vocabulary)}
    labels = {fid: obj.label.strip().casefold() for fid, obj in objects.items()}
    terms = {term.fact_id for term in vocabulary.terms}
    candidates = [
        relation for relation in facts.scene_facts.relations
        if relation.subject_fact_id in objects and relation.reference_fact_id in objects
        and labels[relation.subject_fact_id] != labels[relation.reference_fact_id]
        and relation.fact_id in terms
    ]
    if not candidates:
        raise ValueError("M02 A1 needs a confirmed relation between two different objects")
    return random.Random(f"{seed}:M02-A1").choice(sorted(candidates, key=lambda r: r.fact_id))


def find_target(facts, vocabulary=None):
    """The A2 target, its clues and a distractor that matches at most one clue.

    Port of dev's ``_roleplay_selection`` for M02 over confirmed scene facts: exactly
    one object matches both the attribute clue and the location clue.
    """
    usable = (usable_objects(facts, vocabulary) if vocabulary is not None
              else list(facts.scene_facts.objects))
    by_id = {obj.fact_id: obj for obj in usable}
    attributes = [a for a in facts.scene_facts.attributes if a.object_fact_id in by_id]
    relations = [
        r for r in facts.scene_facts.relations
        if r.subject_fact_id in by_id and r.reference_fact_id in by_id
    ]
    if vocabulary is not None:
        terms = {term.fact_id for term in vocabulary.terms}
        attributes = [a for a in attributes if a.fact_id in terms]
        relations = [r for r in relations if r.fact_id in terms]

    def has_attribute(fid, attribute):
        return any(
            a.object_fact_id == fid and (a.kind, a.value) == (attribute.kind, attribute.value)
            for a in attributes
        )

    def has_relation(fid, relation):
        return any(
            r.subject_fact_id == fid
            and relation_kind(r.relation) == relation_kind(relation.relation)
            and r.reference_fact_id == relation.reference_fact_id
            for r in relations
        )

    for relation in sorted(relations, key=lambda r: r.fact_id):
        for attribute in attributes:
            if attribute.object_fact_id != relation.subject_fact_id:
                continue
            matching = [
                fid for fid in by_id
                if has_attribute(fid, attribute) and has_relation(fid, relation)
            ]
            if matching != [relation.subject_fact_id]:
                continue
            target = by_id[relation.subject_fact_id]
            distractors = [
                obj for fid, obj in by_id.items()
                if fid not in {target.fact_id, relation.reference_fact_id}
                and has_attribute(fid, attribute) + has_relation(fid, relation) <= 1
            ]
            if not distractors:
                continue
            same_label = [
                obj for obj in distractors
                if obj.label.strip().casefold() == target.label.strip().casefold()
            ]
            sharing = [
                obj for obj in distractors
                if has_attribute(obj.fact_id, attribute) or has_relation(obj.fact_id, relation)
            ]
            distractor = (same_label or sharing or distractors)[0]
            return dict(
                target=target, attribute=attribute, relation=relation, distractor=distractor,
                shares_attribute=has_attribute(distractor.fact_id, attribute),
                shares_relation=has_relation(distractor.fact_id, relation),
            )
    return None


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed=""):
    """Bind M02's slots to confirmed facts; every sentence is planned before generation."""
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, facts, vocabulary, seed)
    return specs.build()


def _plan_a0(specs, facts, vocabulary, seed):
    objects = usable_objects(facts, vocabulary)
    if len(objects) < 2:
        raise ValueError("M02 A0 needs two confirmed translated objects")
    for index, (target, other) in enumerate(_a0_focus(objects, seed), 1):
        specs.add(f"findNamed-{index}", "answer", "find-object", {"object": target.fact_id})
        specs.add(f"chooseName-{index}", "name", "identify-object",
                  {"object": target.fact_id}, suffix="target")
        specs.add(f"chooseName-{index}", "name", "identify-object",
                  {"object": other.fact_id}, suffix="other")
        # The listening question replays the target's generated name.
        specs.skip(f"listenSelect-{index}")


def _plan_a1(specs, facts, vocabulary, seed):
    relation = _a1_relation(facts, vocabulary, seed)
    located = {"relation": relation.fact_id, "reference": relation.reference_fact_id}
    statement = {"subject": relation.subject_fact_id, **located}
    # A position phrase omits its object; ``target`` keeps the relation's subject bound.
    place = {"target": relation.subject_fact_id, **located}
    alternatives = _relation_alternatives(relation, facts, vocabulary)
    specs.add("findObject", "answer", "scene-location", statement, suffix="statement")
    specs.add("chooseLocation", "answer", "location-phrase", place, suffix="correct")
    for index, (_kind, term) in enumerate(alternatives, 1):
        specs.add("chooseLocation", "option", "location-phrase", place, truth=False,
                  counterfactual={"relation": term.term_id}, suffix=f"alternative-{index}")
    specs.add("askWhere", "question", "where-question", {"subject": relation.subject_fact_id})
    if alternatives:
        # The contradicting statement supplies the correction and one extra tile.
        specs.add("answerWhere", "contradiction", "scene-location", statement, truth=False,
                  counterfactual={"relation": alternatives[0][1].term_id})
    else:
        specs.skip("answerWhere")


def _plan_a2(specs, facts, vocabulary, seed):
    selection = find_target(facts, vocabulary)
    if selection is None:
        raise ValueError("M02 A2 needs one object matching a detail and a location clue")
    target, attribute, relation = (
        selection["target"], selection["attribute"], selection["relation"],
    )
    attribute_clue = {"target": target.fact_id, "attribute": attribute.fact_id}
    location_clue = {
        "target": target.fact_id, "relation": relation.fact_id,
        "reference": relation.reference_fact_id,
    }
    specs.add("readAttributeClue", "attribute", "target-clue", attribute_clue)
    specs.add("buildLocationClue", "location", "target-clue", location_clue)
    # Finding the target reuses both clues.
    specs.skip("chooseUniqueTarget")
    corrected, shared = (
        (location_clue, attribute_clue) if selection["shares_attribute"]
        else (attribute_clue, location_clue)
    )
    specs.add("clarifyDistractor", "clarify", "target-clue", corrected, labels=["no"],
              suffix="correct")
    if selection["shares_attribute"] or selection["shares_relation"]:
        specs.add("clarifyDistractor", "clarify", "target-clue", shared, labels=["no"],
                  suffix="shared")
    specs.add("buildTargetSentence", "answer", "target-location", {
        "subject": target.fact_id, "attribute": attribute.fact_id,
        "relation": relation.fact_id, "reference": relation.reference_fact_id,
    })


_PLANNERS = {"A0": _plan_a0, "A1": _plan_a1, "A2": _plan_a2}


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _build_a0(ctx):
    translations, focus = {}, []
    for index in (1, 2):
        find = ctx.sentence_by_id(f"findNamed-{index}", "answer")
        name = ctx.sentence_by_id(f"chooseName-{index}", "target")
        other = ctx.sentence_by_id(f"chooseName-{index}", "other")
        row = ctx.by_fact[ctx.spec(f"findNamed-{index}").bindings["object"]]
        row.update(find=find.text, name=name.text)
        translations.update({find.text: find.translation, name.text: name.translation,
                             other.text: other.translation})
        focus.append((row, other))
    payload = ctx.payload(
        focus=[row["key"] for row, _ in focus],
        approvedObjects=ctx.rows,
        approvedTranslations=translations,
        approvedSentenceChunks=list(translations),
        approvedArticlesOrEndings=[],
        approvedNumberWords={},
        whatIsThis=ctx.label("what-is-this"),
        yesNo=[ctx.label("yes-answer"), ctx.label("no-answer")],
    )
    questions = []
    for index, (row, other) in enumerate(focus, 1):
        section = f"Task {index} · {row['label']}"
        questions += [
            _marker_question(payload, "findNamed", section, row, row["find"], index=index),
            _choice_question(payload, "chooseName", section, row, INSTRUCTIONS["chooseName"],
                             [row["name"], other.text], row["name"], index=index),
            _marker_question(payload, "listenSelect", section, row, row["name"],
                             index=index, listen_first=True),
        ]
    result = A0LessonResult(title="Find the named objects", questions=questions)
    task = a0_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _build_a1(ctx):
    statement = ctx.sentence_by_id("findObject", "statement")
    question = ctx.sentence_by_id("askWhere", "question")
    spec = ctx.spec("findObject")
    subject = ctx.by_fact[spec.bindings["subject"]]
    reference = ctx.by_fact[spec.bindings["reference"]]
    relation = ctx.relations[spec.bindings["relation"]]
    kind = relation_kind(relation.relation)
    places = [dict(position=kind, label=ctx.sentence_by_id("chooseLocation", "correct").text)]
    meanings = {kind: kind.replace("_", " ")}
    for place_spec in ctx.specs("chooseLocation")[1:]:
        alternative = ctx.terms_by_id[place_spec.counterfactual["relation"]]
        alt_kind = relation_kind(alternative.linguistic.get("relation-kind",
                                                            alternative.source_text))
        meanings[alt_kind] = alt_kind.replace("_", " ")
        places.append(dict(position=alt_kind,
                           label=ctx.sentence_for("chooseLocation", place_spec).text))
    if ctx.specs("answerWhere"):
        contradiction = ctx.sentence_by_id("answerWhere", "contradiction")
        answer_tiles = ctx.chunks(statement)["answer_chunks"]
        wrong_tiles = ctx.chunks(contradiction)["answer_chunks"]
        extras = [chunk for chunk in wrong_tiles if chunk not in answer_tiles][:1]
        contradiction_text = contradiction.text
    else:
        extras, contradiction_text = [], statement.text
    order = ctx.shuffle(range(len(places)), f"M02:{relation.fact_id}")
    markers = sorted(ctx.rows, key=lambda row: row["marker"])
    marker_of = {row["key"]: row["marker"] for row in ctx.rows}
    same = fold(subject["source"])
    shown = [subject["key"], reference["key"], *(
        row["key"] for row in markers
        if row["key"] not in {subject["key"], reference["key"]} and fold(row["source"]) != same
    )][:MAX_MARKERS]
    shown.sort(key=marker_of.get)
    payload = ctx.payload(
        positions=[dict(position=k, meaning=m) for k, m in meanings.items()],
        markers=[dict(key=row["key"], marker=row["marker"], source=row["source"])
                 for row in markers],
        relations=[dict(
            key=relation.fact_id, subjectKey=subject["key"], subjectSource=subject["source"],
            referenceKey=reference["key"], referenceSource=reference["source"],
            position=kind, meaning=meanings[kind], contradiction=contradiction_text,
            placeOptions=places, statement=statement.text, whereQuestion=question.text,
        )],
        selected=[relation.fact_id],
    )
    common = dict(object_key=subject["key"], relation_key=relation.fact_id)
    find_options = [dict(option_id=f"marker-{marker_of[key]}", label=str(marker_of[key]))
                    for key in shown]
    place_options = [dict(option_id=f"place-{n}", label=places[i]["label"])
                     for n, i in enumerate(order, 1)]
    questions = [
        dict(question_id="find-object", purpose="findObject", section=FIND_SECTION,
             prompt=statement.text, interaction_type="multipleChoice", options=find_options,
             correct_option_id=f"marker-{marker_of[subject['key']]}",
             correct_text=None, token_bank=[], translation=None,
             marker_keys={o["option_id"]: key for o, key in zip(find_options, shown, strict=True)},
             **common),
        dict(question_id="choose-location", purpose="chooseLocation", section=FIND_SECTION,
             prompt=question.text, interaction_type="multipleChoice", options=place_options,
             correct_option_id=next(
                 o["option_id"] for o, i in zip(place_options, order, strict=True) if i == 0
             ),
             correct_text=None, token_bank=[], translation=None, **common),
        dict(question_id="ask-where", purpose="askWhere", section=ASK_SECTION,
             prompt=ctx.label("ask-where"), interaction_type="sentenceBuilding",
             options=[], correct_option_id=None, correct_text=question.text,
             token_bank=ctx.chunks(question, salt="ask-where")["token_bank"],
             translation=question.translation, **common),
        dict(question_id="answer-where", purpose="answerWhere", section=ASK_SECTION,
             prompt=ctx.label("answer-where"), interaction_type="sentenceBuilding",
             options=[], correct_option_id=None, correct_text=statement.text,
             token_bank=ctx.chunks(statement, extras, salt="answer-where")["token_bank"],
             translation=statement.translation, **common),
    ]
    result = M02LessonResult(title="Find and locate", questions=questions)
    task = m02_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _build_a2(ctx):
    attribute_clue = ctx.sentence_by_id("readAttributeClue", "attribute")
    location_clue = ctx.sentence_by_id("buildLocationClue", "location")
    target_sentence = ctx.sentence_by_id("buildTargetSentence", "answer")
    clarify = ctx.specs("clarifyDistractor")
    correct = ctx.sentence_for("clarifyDistractor", clarify[0])
    shared = ctx.sentence_for("clarifyDistractor", clarify[1]) if len(clarify) > 1 else None
    target_spec = ctx.spec("buildTargetSentence")
    target = ctx.by_fact[target_spec.bindings["subject"]]
    attribute = ctx.attributes[target_spec.bindings["attribute"]]
    distractor = ctx.by_fact[find_target(ctx.facts, ctx.vocabulary)["distractor"].fact_id]
    s1, s2, s3 = A2_SECTIONS
    meaning_prompt, marker_prompt = _a2_composed_prompts(ctx, attribute_clue, location_clue)
    meanings = _a2_meanings(ctx, attribute)
    location = ctx.chunks(location_clue, _a2_position_extra(ctx, location_clue), salt="m02-q2")
    described = ctx.chunks(target_sentence, [ctx.label("connector-distractor")], salt="m02-q5")
    marker_rows = sorted(
        [target, distractor,
         *[row for row in ctx.rows if row["key"] not in {target["key"], distractor["key"]}][:1]],
        key=lambda row: row["marker"],
    )
    clarifications = [("clarify-correct", correct.text)]
    if shared is not None:
        clarifications.append(("clarify-shared", shared.text))
    clarifications.append(("clarify-yes", ctx.label("yes-answer")))

    def choice(qid, purpose, prompt, options, correct_id, section, **fields):
        rows = ctx.shuffle([dict(option_id=key, label=text) for key, text in options], qid)
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="multipleChoice",
            options=rows, correct_option_id=correct_id, object_key=target["key"],
            section=section, target_language_text=[prompt], **fields,
        )

    def building(qid, purpose, prompt, candidate, tiles, section):
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="sentenceBuilding",
            correct_text=candidate.text, token_bank=tiles["token_bank"],
            answer_chunks=tiles["answer_chunks"], distractor_chunks=tiles["distractor_chunks"],
            translation=candidate.translation, object_key=target["key"], section=section,
            target_language_text=[prompt],
        )

    questions = [
        choice("m02-q1", "readAttributeClue", meaning_prompt,
               [("meaning-correct", meanings[0]),
                *((f"meaning-{n}", text) for n, text in enumerate(meanings[1:], 1))],
               "meaning-correct", s1, roleplay_premise=ROLEPLAY_PREMISE, option_language="en",
               translation="Choose the English meaning of the clue."),
        building("m02-q2", "buildLocationClue", ctx.label("build-location-clue"),
                 location_clue, location, s1),
        choice("m02-q3", "chooseUniqueTarget", marker_prompt,
               [(row["key"], str(row["marker"])) for row in marker_rows], target["key"], s2,
               marker_object_ids={row["key"]: row["key"] for row in marker_rows}),
        choice("m02-q4", "clarifyDistractor",
               ctx.label("friend-points", marker=str(distractor["marker"])),
               clarifications, "clarify-correct", s2,
               roleplay_premise=ROLEPLAY_PREMISE, group_object_ids=[distractor["key"]]),
        building("m02-q5", "buildTargetSentence", ctx.label("name-and-locate"),
                 target_sentence, described, s3),
    ]
    payload = ctx.payload(
        approvedFacts=dict(approvedObjects=ctx.rows,
                           sceneFacts=ctx.facts.model_dump(mode="json"),
                           approvedVocabulary=ctx.vocabulary.model_dump(mode="json")),
        selection=dict(targetObjectKey=target["key"], distractorObjectKey=distractor["key"],
                       attributeKey=attribute.fact_id,
                       relationshipKey=target_spec.bindings["relation"]),
    )
    result = MissionA2Result(title="Help someone find it", questions=questions)
    task = m02_a2_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _a2_composed_prompts(ctx, attribute_clue, location_clue):
    """Prompts made of generated clues and fixed labels, with their spellings."""
    full_clue = f"{attribute_clue.text} {location_clue.text}"
    meaning_prompt = f"{attribute_clue.text} {ctx.label('clue-meaning')}"
    marker_prompt = f"{full_clue} {ctx.label('find-both-clues')}"
    if attribute_clue.romanization and location_clue.romanization:
        clue_latin = f"{latin_of(attribute_clue)} {latin_of(location_clue)}"
        ctx.extra_spellings[full_clue] = clue_latin
        for composed, first, semantic in (
            (meaning_prompt, latin_of(attribute_clue), "clue-meaning"),
            (marker_prompt, clue_latin, "find-both-clues"),
        ):
            if ctx.labels[semantic].romanization:
                ctx.extra_spellings[composed] = f"{first} {ctx.labels[semantic].romanization}"
    return meaning_prompt, marker_prompt


def _a2_meanings(ctx, attribute):
    """English meanings for the detail clue: the confirmed detail first."""
    meanings = [f"It is {attribute.value}."]
    meanings += [
        f"It is {other.value}." for other in ctx.facts.scene_facts.attributes
        if other.kind == attribute.kind and other.value != attribute.value
    ]
    meanings += [
        f"It is {term.source_text}." for term in ctx.vocabulary.terms
        if term.linguistic.get("contrast-for") == attribute.fact_id
        and term.provenance == "modelProposal"
    ]
    meanings = list(dict.fromkeys(meanings))[:3]
    if len(meanings) < 2:
        raise ValueError("M02 A2 needs a contrasting detail meaning for the clue question")
    return meanings


def _a2_position_extra(ctx, location_clue):
    """One word of a false position, so the extra tile looks like the others."""
    relation = ctx.relations.get(ctx.spec("buildLocationClue").bindings.get("relation"))
    if relation is None:
        return []
    clue_words = ctx.chunks(location_clue)["answer_chunks"]
    return [
        word for _kind, term in _relation_alternatives(relation, ctx.facts, ctx.vocabulary)[:1]
        for word in term.target_text.split() if word not in clue_words
    ][:1]


_BUILDERS = {"A0": _build_a0, "A1": _build_a1, "A2": _build_a2}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """Reject missing choice data before any sentence generation."""
    if level != "A1":
        return
    if len(next(slot for slot in plan.slots if slot.slot_id == "chooseLocation").specs) < 2:
        raise ValueError(
            "M02 A1 needs at least one false position option for the confirmed relation. "
            "Retry so the model proposes contrasting positions."
        )


def check_lesson(level, result, approved, pack):
    """Keep dev's M02 question count, order, interactions and answer contract."""
    check_questions(result.questions, PURPOSES[level], MISSION_ID)


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=()):
    """A2 needs one object a detail clue and a location clue identify together."""
    if str(mission.practice_level) != "A2":
        return []
    from ..generation import BoundSceneFacts

    object_ids = {obj.id for obj in objects}
    facts = BoundSceneFacts(scene_facts=dict(
        objects=[dict(fact_id=f"object:{obj.id}", scene_object_id=obj.id, label=obj.label,
                      marker=index) for index, obj in enumerate(objects, 1)],
        attributes=[
            dict(fact_id=f"attribute:{obj.id}:{key}", object_fact_id=f"object:{obj.id}",
                 kind=kind, value=value.casefold())
            for obj in objects for key, kind, value in attributes_of(obj)
        ],
        relations=[
            dict(fact_id=f"relation:{rel.id}",
                 subject_fact_id=f"object:{rel.subject_scene_object_id}",
                 reference_fact_id=f"object:{rel.reference_scene_object_id}",
                 relation=relation_kind(rel.relation))
            for rel in relations
            if {rel.subject_scene_object_id, rel.reference_scene_object_id} <= object_ids
        ],
    ))
    if find_target(facts) is None:
        return ["Confirm one object that has a detail and a location no other object shares."]
    return []


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    photo_reasons=photo_reasons,
)
