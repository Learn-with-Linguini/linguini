"""M01 (name, identify and describe) as a pack lesson.

Questions, sections, grading and corrections are dev's existing M01 builders
(`a0_lesson_task`, `m01_lesson_task`, `m01_a2_task`); only the target-language text
comes from validated, model-generated sentences instead of per-language tables.
"""

from __future__ import annotations

import random
from collections import Counter

from app.ai.features.learning_tasks.mission_a0 import (
    A0LessonResult,
    _build_question,
    _choice_question,
    _marker_question,
    _other,
    _sections,
)
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.ai.features.learning_tasks.mission_m01 import (
    CONFIRM_IDS,
    DESCRIBE_SECTION,
    IDENTIFY_SECTION,
    M01LessonResult,
    M01Question,
)
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m01_a2_task
from app.services.mission_lessons_m01 import m01_lesson_task

from ..schema import join_pack_chunks
from .base import PackMission, for_level
from .common import LessonContext, SpecBuilder, usable_objects

MISSION_ID = "M01"
PURPOSES = {
    "A0": ["matchName", "confirmName", "buildIdentify"] * 2,
    "A1": ["confirmObject", "confirmObject", "chooseAttribute", "describeObject"],
    "A2": [
        "chooseSceneMarker", "buildSceneFact", "chooseSceneDescription",
        "buildSceneDescription", "followUpSceneFact",
    ],
}
_SECTION_SIZES = {"A0": [3, 3], "A1": [2, 2], "A2": [2, 2, 1]}
_BUILDING = {"buildIdentify", "describeObject", "buildSceneFact", "buildSceneDescription"}
A2_SECTIONS = (
    "Task 1 · Notice the facts", "Task 2 · Describe the scene", "Task 3 · Check a detail",
)
# Keys of in-sentence gender agreement forms; other keys (modifier, predicative,
# case forms) are not wrong-agreement alternatives.
AGREEMENT_KEYS = frozenset({"masculine", "feminine", "neuter"})


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed=""):
    """Preserve the M01 slot sequence, binding every sentence before generation."""
    objects = usable_objects(facts, vocabulary)
    if len(objects) < 2:
        raise ValueError("M01 needs two confirmed translated objects")
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, facts, vocabulary, objects, seed)
    return specs.build()


def _plan_a0(specs, facts, vocabulary, objects, seed):
    truths = [True, False]
    random.Random(f"{seed}:truth").shuffle(truths)
    for index, obj in enumerate(objects[:2], 1):
        other = objects[1 if index == 1 else 0]
        truth = truths[index - 1]
        specs.add(f"matchName-{index}", "name", "identify-object", {"object": obj.fact_id})
        specs.add(
            f"confirmName-{index}", "question", "yes-no-identification",
            {"object": (obj if truth else other).fact_id, "shown": obj.fact_id}, truth=truth,
        )
        specs.add(f"buildIdentify-{index}", "answer", "identify-object", {"object": obj.fact_id})


def _plan_a1(specs, facts, vocabulary, objects, seed):
    rng = random.Random(seed)
    terms = {term.fact_id for term in vocabulary.terms}
    attrs = [a for a in facts.scene_facts.attributes if a.fact_id in terms]
    selected = []
    for obj in objects:
        details = [a for a in attrs if a.object_fact_id == obj.fact_id]
        if details:
            # The second description prefers a non-colour detail as before.
            detail = (
                next((a for a in details if a.kind != "colour"), details[0])
                if selected
                else next((a for a in details if a.kind == "colour"), details[0])
            )
            selected.append((obj, detail))
        if len(selected) == 2:
            break
    if len(selected) != 2:
        raise ValueError("A1 needs two translated object-detail pairs")
    for index, (obj, detail) in enumerate(selected, 1):
        other = selected[1 if index == 1 else 0][0]
        truth = rng.random() < 0.5
        for use, named, value in (
            ("prompt", obj if truth else other, truth),
            ("answer", obj, truth),
            ("option", other, not truth),
        ):
            specs.add(
                f"confirmObject-{index}", use, "yes-no-identification",
                {"object": named.fact_id, "shown": obj.fact_id},
                truth=value, labels=[] if use == "prompt" else ["yes" if value else "no"],
            )
        specs.add(
            "chooseAttribute" if index == 1 else "describeObject", "answer",
            "describe-attribute", {"object": obj.fact_id, "attribute": detail.fact_id},
        )


def _plan_a2(specs, facts, vocabulary, objects, seed):
    terms = {term.fact_id: term for term in vocabulary.terms}
    attrs = [a for a in facts.scene_facts.attributes if a.fact_id in terms]
    relations = [r for r in facts.scene_facts.relations if r.fact_id in terms]
    if len(objects) < 3 or not (attrs or relations):
        raise ValueError("A2 pack planning needs three objects and a translated detail or relation")
    attr = attrs[0] if attrs else None
    first_id = attr.object_fact_id if attr else relations[0].subject_fact_id
    first = next(o for o in objects if o.fact_id == first_id)
    rel = next(
        (r for r in facts.scene_facts.relations
         if r.subject_fact_id == first.fact_id and r.fact_id in terms),
        None,
    )
    second = (
        next(o for o in objects if o.fact_id == rel.reference_fact_id)
        if rel else next(o for o in objects if o != first)
    )
    third = next(o for o in objects if o not in (first, second))
    b1 = (
        {"object": first.fact_id, "attribute": attr.fact_id}
        if attr
        else {"subject": first.fact_id, "reference": second.fact_id, "relation": rel.fact_id}
    )
    b2 = (
        {"subject": first.fact_id, "reference": second.fact_id, "relation": rel.fact_id}
        if rel and attr else {"object": second.fact_id}
    )
    c1 = "scene-existence" if attr else "scene-location"
    c2 = "scene-location" if rel and attr else "scene-existence"
    specs.add("chooseSceneMarker", "fact1", c1, b1)
    specs.add("buildSceneFact", "fact2", c2, b2)
    connected = {**b1, "other-object": third.fact_id}
    specs.add("chooseSceneDescription", "connected", "connected-description", connected)
    role = "attribute" if attr else "relation"
    contrast = _a2_contrast(vocabulary, terms, attrs, attr, rel)
    specs.add("chooseSceneDescription", "wrongAttribute", "connected-description", connected,
              truth=False, counterfactual={role: contrast.term_id})
    specs.add("chooseSceneDescription", "falseFirst", c1, b1,
              truth=False, counterfactual={role: contrast.term_id})
    specs.add("chooseSceneDescription", "wrongExistence", "connected-description", b1,
              truth=False, counterfactual={"other-object": terms[third.fact_id].term_id})
    for use, construction, bindings in (
        ("fact1", c1, b1),
        ("fact2", c2, b2),
        ("fact3", "scene-existence", {"object": third.fact_id}),
    ):
        specs.add("buildSceneDescription", use, construction, bindings)
    specs.add("followUpSceneFact", "followup",
              "describe-attribute" if attr else "scene-location", b1)


def _a2_contrast(vocabulary, terms, attrs, attr, rel):
    """A contrasting detail or relation term for the false scene descriptions."""
    contrast = next(
        (
            term
            for term in sorted(vocabulary.terms, key=lambda t: t.provenance != "modelProposal")
            if term.provenance in {"packData", "modelProposal"}
            and term.fact_id.startswith(("contrast:", "alternative:"))
            and term.linguistic.get("contrast-for") in {
                None, attr.fact_id if attr else rel.fact_id,
            }
            and (
                term.linguistic.get("attribute-kind") == attr.kind
                and term.source_text != attr.value
                if attr
                else "relation-kind" in term.linguistic
                and term.linguistic["relation-kind"] != str(rel.relation)
            )
        ),
        None,
    )
    if contrast is None and attr:
        alternative = next(
            (a for a in attrs if a.kind == attr.kind and a.value != attr.value), None
        )
        contrast = terms[alternative.fact_id] if alternative else None
    if contrast is None:
        raise ValueError("A2 needs an approved contrasting detail for its false option")
    return contrast


_PLANNERS = {"A0": _plan_a0, "A1": _plan_a1, "A2": _plan_a2}


# ---------------------------------------------------------------- detail forms


def _form(term, gender):
    return term.forms_by_key.get(gender) or term.forms_by_key.get("default", term.target_text)


def _standalone_form(term, gender):
    """A detail named on its own (a choice), e.g. German rot rather than attributive rote."""
    return term.forms_by_key.get("predicative") or _form(term, gender)


def _detail_options(facts, vocabulary, attribute, gender, *, include_pack=False, pack=None):
    terms = {term.fact_id: term for term in vocabulary.terms}
    selected = terms[attribute.fact_id]
    options = [_standalone_form(selected, gender)]
    meanings = {options[0].casefold(): attribute.value}
    # Distractors are approved translations, never an implicit per-language lexicon.
    for other in facts.scene_facts.attributes:
        if (
            other.kind != attribute.kind
            or other.value == attribute.value
            or other.fact_id not in terms
        ):
            continue
        if pack is not None:
            if attribute.kind == "colour" and other.value in pack.lexical.get(
                "confusable_colours", {}
            ).get(attribute.value, "").split("|"):
                continue
            if attribute.kind != "colour" and other.value not in pack.lexical.get(
                "attribute_contrasts", {}
            ).get(f"{attribute.kind}:{attribute.value}", "").split("|"):
                continue
        form = _standalone_form(terms[other.fact_id], gender)
        if form.casefold() not in {value.casefold() for value in options}:
            options.append(form)
            meanings[form.casefold()] = other.value
        if len(options) == 3:
            break
    # Preserve existing scene-colour choices; use pack colours when no distinct
    # scene colour is available. Other detail kinds keep their existing fill rule.
    if include_pack and len(options) < (2 if attribute.kind == "colour" else 3):
        for term in sorted(vocabulary.terms, key=lambda t: t.provenance != "modelProposal"):
            if term.linguistic.get("attribute-kind") != attribute.kind:
                continue
            proposed = term.provenance == "modelProposal"
            if proposed and term.linguistic.get("contrast-for") != attribute.fact_id:
                continue
            if (
                attribute.kind == "colour"
                and pack is not None
                and term.source_text
                in (pack.lexical.get("confusable_colours", {}).get(attribute.value, "").split("|"))
            ):
                continue
            if (
                attribute.kind != "colour"
                and not proposed
                and pack is not None
                and term.source_text
                not in (
                    pack.lexical.get("attribute_contrasts", {})
                    .get(f"{attribute.kind}:{attribute.value}", "")
                    .split("|")
                )
            ):
                continue
            form = _standalone_form(term, gender)
            if form.casefold() not in {value.casefold() for value in options}:
                options.append(form)
                meanings[form.casefold()] = term.source_text
            if len(options) == 3:
                break
    if len(options) < 2:
        raise ValueError(
            f"M01 needs a contrasting approved detail option for {attribute.kind}:"
            f"{attribute.value} (agreement={gender!r}). Supply a distinct validated "
            "scene translation or model-proposed alternative. Pack reference "
            "vocabulary is optional; missing or unsuitable candidates must be retried."
        )
    return options, meanings


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _build_a0(ctx):
    focus = [ctx.by_fact[ctx.spec(f"matchName-{i}").bindings["object"]] for i in (1, 2)]
    translations = {ctx.label("what-is-this"): ctx.labels["what-is-this"].meaning}
    templates = next(
        c.templates for c in ctx.pack.constructions if c.construction_id == "identify-object"
    )
    taught = []
    for row in ctx.rows:
        english = row["source"]
        indefinite = f"{'an' if english[:1].lower() in 'aeiou' else 'a'} {english}"
        for name, meaning in (
            (row["name"], f"the {english}"),
            (templates.get("identify", "").format(**row), f"This is {indefinite}."),
            (templates.get("question", "").format(**row), f"Is this {indefinite}?"),
            (templates.get("find", "").format(**row), f"Find the {english}."),
            (templates.get("slot", "").format(**row), f"the {english}"),
        ):
            if name:
                taught.append(name)
                translations[name] = meaning
    for row, index in zip(focus, (1, 2), strict=True):
        for field, slot in (("name", "matchName"), ("isIt", "confirmName"),
                            ("identify", "buildIdentify")):
            sentence = ctx.sentence(f"{slot}-{index}")
            row[field] = sentence.text
            translations[sentence.text] = sentence.translation
    payload = ctx.payload(
        focus=[row["key"] for row in focus],
        approvedObjects=ctx.rows,
        approvedTranslations=translations,
        whatIsThis=ctx.label("what-is-this"),
        yesNo=[ctx.label("yes-answer"), ctx.label("no-answer")],
        approvedSentenceChunks=list(dict.fromkeys([*translations, *taught])),
        approvedArticlesOrEndings=[],
        approvedNumberWords={},
    )
    questions = []
    for index, (section, target) in enumerate(_sections(payload), 1):
        spec = ctx.spec(f"confirmName-{index}")
        other = _other(payload, target, f"tile-{index}")
        extra_noun = next((
            term.forms_by_key.get("bare", term.target_text)
            for term in ctx.vocabulary.terms
            if term.provenance == "modelProposal"
            and term.linguistic.get("alternative-kind") == "noun"
            and term.linguistic.get("contrast-for") == target["fact_id"]
        ), other["noun"])
        marker = _marker_question(payload, "matchName", section, target, target["name"],
                                  index=index)
        confirm = _choice_question(
            payload, "confirmName", section, target, target["isIt"], payload["yesNo"],
            payload["yesNo"][0 if spec.truth else 1], index=index, shuffle=False,
            statement_true=spec.truth, stated_key=ctx.by_fact[spec.bindings["object"]]["key"],
            audio_text=target["isIt"],
        )
        built = _build_question(payload, "buildIdentify", section, target, payload["whatIsThis"],
                                target["identify"], extra_noun, index=index)
        # Use only chunks derived after complete-sentence validation.
        built["token_bank"] = ctx.chunks(
            ctx.sentence(f"buildIdentify-{index}"), [extra_noun],
        )["token_bank"]
        questions.extend((marker, confirm, built))
    result = A0LessonResult(title="Name the objects", questions=questions)
    task = a0_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _build_a1(ctx):
    pairs = []
    for slot in ("chooseAttribute", "describeObject"):
        spec = ctx.spec(slot)
        obj = ctx.by_fact[spec.bindings["object"]]
        detail = ctx.attributes[spec.bindings["attribute"]]
        if detail.object_fact_id != obj["fact_id"]:
            raise ValueError("attribute is bound to another object instance")
        term = ctx.terms[detail.fact_id]
        pairs.append(dict(
            **obj,
            attributeKey=detail.fact_id,
            attributeType=detail.kind,
            attributeSource=detail.value,
            agreedForm=_form(term, obj["gender"]),
            before=term.position == "before",
        ))
    first, second = pairs
    # The chosen detail stands alone; the described one agrees inside the sentence.
    first["agreedForm"] = _standalone_form(ctx.terms[first["attributeKey"]], first["gender"])
    options, meanings = _detail_options(
        ctx.facts, ctx.vocabulary, ctx.attributes[first["attributeKey"]], first["gender"],
        include_pack=True, pack=ctx.pack,
    )
    prompt_label = (ctx.labels.get(f"attribute-prompt-{first['attributeType']}")
                    or ctx.labels.get("attribute-prompt"))
    if prompt_label is None:
        raise ValueError("pack needs a prompt for the selected attribute construction")
    canonical = ctx.sentence("describeObject").text
    extras = _wrong_agreement_tiles(ctx, second, canonical)
    construction = next(
        c for c in ctx.pack.constructions if c.construction_id == "describe-attribute"
    )
    confirm_templates = next(
        c.templates for c in ctx.pack.constructions
        if c.construction_id == "yes-no-identification"
    )
    payload = ctx.payload(
        pairs=pairs,
        attributeOptions=options,
        attributeMeanings=meanings,
        describeExtras=extras,
        attributePromptTranslation=prompt_label.meaning,
        packCorrections=[
            dict(
                mistake="wrongGender",
                answers=[canonical.replace(second["agreedForm"], form)],
                correction=canonical,
                explanation=f"The word agrees with {second['nounPhrase']}: {second['agreedForm']}.",
            )
            for form in extras
        ] + [dict(
            mistake="wordOrder",
            correction=canonical,
            explanation=construction.templates.get("word_order_feedback", construction.summary),
        )],
        yes=ctx.label("yes"),
        no=ctx.label("no"),
        confirmPrompt=confirm_templates.get("question", "{noun}"),
        sentenceStart=confirm_templates.get("sentence_start", ""),
    )
    layout = ctx.selection.get("layout", {})
    questions = []
    for index, shown in enumerate(pairs, 1):
        slot = f"confirmObject-{index}"
        prompt, answer, contrast = (
            ctx.sentence(slot, use) for use in ("prompt", "answer", "option")
        )
        labels = [answer.text, contrast.text]
        orders = layout.get("confirmOrders")
        order = orders[index - 1] if orders is not None else ctx.shuffle(
            range(2), f"confirm-order-{index}",
        )
        choices = [dict(option_id=f"confirm-{i + 1}", label=labels[value])
                   for i, value in enumerate(order)]
        questions.append(M01Question(
            question_id=CONFIRM_IDS[index - 1],
            purpose="confirmObject",
            section=IDENTIFY_SECTION,
            prompt=prompt.text,
            interaction_type="multipleChoice",
            options=choices,
            correct_option_id=next(o["option_id"] for o in choices if o["label"] == answer.text),
            correct_text=None,
            token_bank=[],
            translation=None,
            object_key=shown["key"],
            attribute_keys=[],
            statement_correct=ctx.spec(slot, "prompt").truth,
        ))
    attribute_order = layout.get("attributeOrder")
    if attribute_order is None:
        attribute_order = ctx.shuffle(range(len(options)), "attribute-order")
    detail_options = [
        {"option_id": f"attribute-{i}", "label": value[:1].upper() + value[1:]}
        for i, value in enumerate([options[j] for j in attribute_order if j < len(options)], 1)
    ]
    questions.append(M01Question(
        question_id="choose-attribute",
        purpose="chooseAttribute",
        section=DESCRIBE_SECTION,
        prompt=prompt_label.text,
        interaction_type="multipleChoice",
        options=detail_options,
        correct_option_id=next(
            o["option_id"] for o in detail_options
            if o["label"].casefold() == first["agreedForm"].casefold()
        ),
        correct_text=None,
        token_bank=[],
        translation=None,
        object_key=first["key"],
        attribute_keys=[first["attributeKey"]],
    ))
    sentence = ctx.sentence("describeObject")
    questions.append(M01Question(
        question_id="describe-object",
        purpose="describeObject",
        section=DESCRIBE_SECTION,
        prompt=ctx.label("describe-object"),
        interaction_type="sentenceBuilding",
        options=[],
        correct_option_id=None,
        correct_text=sentence.text,
        token_bank=ctx.chunks(sentence, extras)["token_bank"],
        translation=sentence.translation,
        object_key=second["key"],
        attribute_keys=[second["attributeKey"]],
    ))
    result = M01LessonResult(
        title="Name it and describe it",
        explanation="Use the details shown in the scene.",
        questions=questions,
    )
    task = m01_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _wrong_agreement_tiles(ctx, described, canonical):
    """Other gender forms of the described detail, only where they change the sentence."""
    if ctx.pack.language.grammatical_gender == "none":
        return []
    term = ctx.terms[described["attributeKey"]]
    return list(dict.fromkeys(
        form
        for key, form in term.forms_by_key.items()
        if key in AGREEMENT_KEYS
        and form != described["agreedForm"]
        and described["agreedForm"] in canonical
    ))


def _build_a2(ctx):
    first_spec = ctx.spec("chooseSceneMarker", "fact1")
    first = ctx.by_fact[first_spec.bindings.get("object") or first_spec.bindings["subject"]]
    detail = ctx.attributes.get(first_spec.bindings.get("attribute"))
    third = ctx.by_fact[ctx.spec("chooseSceneDescription", "connected").bindings["other-object"]]
    fact1 = ctx.sentence("chooseSceneMarker", "fact1")
    fact2 = ctx.sentence("buildSceneFact", "fact2")
    descriptions = [
        ctx.sentence("buildSceneDescription", use) for use in ("fact1", "fact2", "fact3")
    ]
    relation_id = (first_spec.bindings.get("relation")
                   or ctx.spec("buildSceneFact", "fact2").bindings.get("relation"))
    detail_rows = _a2_detail_rows(ctx, detail, first, first_spec, relation_id)
    payload = ctx.payload(
        approvedFacts=dict(
            approvedObjects=ctx.rows,
            sceneFacts=ctx.facts.model_dump(mode="json"),
            approvedVocabulary=ctx.vocabulary.model_dump(mode="json"),
        ),
        selection=dict(
            attributeKey=detail.fact_id if detail else None,
            relationKey=relation_id,
            firstFactKind="attribute" if detail else "relation",
            secondObjectKey=None,
            thirdObjectKey=third["key"],
        ),
    )
    planning = [
        f"The {first['source']} is {detail.value}." if detail else fact1.translation or fact1.text,
        fact2.translation or fact2.text,
        descriptions[2].translation or descriptions[2].text,
    ]
    section1, section2, section3 = A2_SECTIONS
    marker_options = [
        {"option_id": row["key"], "label": str(row["marker"])} for row in (first, third)
    ]
    connected, wrong_attribute, wrong_existence = (
        ctx.sentence("chooseSceneDescription", use)
        for use in ("connected", "wrongAttribute", "wrongExistence")
    )
    description_options = [
        dict(option_id=key, label=sentence.text)
        for key, sentence in (
            ("description-correct", connected),
            ("description-attribute", wrong_attribute),
            ("description-existence", wrong_existence),
        )
    ]
    # A full false clause is a distractor; it has already passed sentence validation.
    false_clause = (
        ctx.sentence("chooseSceneDescription", "falseFirst").text
        if ctx.has_use("chooseSceneDescription", "falseFirst")
        else wrong_attribute.text
    )
    full = " ".join(sentence.text for sentence in descriptions)
    full_candidate = descriptions[0].model_copy(update={"text": full, "chunks": []})
    questions = [
        MissionA2Question(
            question_id="m01-q1",
            purpose="chooseSceneMarker",
            prompt=ctx.label("touch-object").replace("{f['first']}", fact1.text),
            interaction_type="multipleChoice",
            options=ctx.shuffle(marker_options, "m01-q1"),
            correct_option_id=first["key"],
            object_key=first["key"],
            section=section1,
            marker_object_ids={row["key"]: row["key"] for row in (first, third)},
        ),
        MissionA2Question(
            question_id="m01-q2",
            purpose="buildSceneFact",
            prompt=ctx.label("build-second-fact"),
            interaction_type="sentenceBuilding",
            object_key=first["key"],
            section=section1,
            **ctx.chunks(fact2, [ctx.label("connector-distractor")]),
        ),
        MissionA2Question(
            question_id="m01-q3",
            purpose="chooseSceneDescription",
            prompt=ctx.label("choose-description"),
            interaction_type="multipleChoice",
            options=ctx.shuffle(description_options, "m01-q3"),
            correct_option_id="description-correct",
            object_key=first["key"],
            section=section2,
        ),
        MissionA2Question(
            question_id="m01-q4",
            purpose="buildSceneDescription",
            prompt=ctx.label("describe-scene"),
            interaction_type="sentenceBuilding",
            object_key=first["key"],
            section=section2,
            planning_facts=planning,
            **ctx.chunks(full_candidate, [false_clause], phrase=True),
        ),
        MissionA2Question(
            question_id="m01-q5",
            purpose="followUpSceneFact",
            prompt=ctx.sentence("followUpSceneFact", "followup").text,
            interaction_type="multipleChoice",
            options=ctx.shuffle(detail_rows, "m01-q5"),
            correct_option_id="detail-correct",
            object_key=first["key"],
            section=section3,
        ),
    ]
    result = MissionA2Result(title="Describe the scene", questions=questions)
    task = m01_a2_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _a2_detail_rows(ctx, detail, first, first_spec, relation_id):
    """Follow-up choices: the confirmed detail (or position) and contrasting ones."""
    pack, vocabulary = ctx.pack, ctx.vocabulary
    if detail:
        detail_options, _ = _detail_options(
            ctx.facts, vocabulary, detail, first["gender"], include_pack=True, pack=pack
        )
        order = pack.lexical.get("choice_order", {}).get(detail.kind) or pack.lexical.get(
            "attribute_contrasts", {}
        ).get(f"{detail.kind}:{detail.value}")
        if order and not any(t.provenance == "modelProposal" for t in vocabulary.terms):
            detail_options = [_standalone_form(ctx.terms[detail.fact_id], first["gender"])]
            rows = [dict(option_id="detail-correct", label=detail_options[0])]
            for index, value in enumerate(order.split("|")):
                term = next(
                    (t for t in vocabulary.terms
                     if t.source_text == value
                     and t.linguistic.get("attribute-kind") == detail.kind),
                    None,
                )
                if term:
                    form = _standalone_form(term, first["gender"])
                    if form.casefold() not in {v.casefold() for v in detail_options}:
                        detail_options.append(form)
                        rows.append(dict(option_id=f"detail-{index}", label=form))
                if len(detail_options) == 3:
                    break
            return rows
        return [
            dict(option_id="detail-correct" if i == 0 else f"detail-{i}", label=v)
            for i, v in enumerate(detail_options)
        ]
    relation = ctx.relations.get(relation_id)
    reference = ctx.by_fact[first_spec.bindings["reference"]]
    separator = " " if pack.language.word_separator == "space" else ""
    detail_options = [separator.join([ctx.terms[relation_id].target_text, reference["name"]])]
    for term in vocabulary.terms:
        if "relation-kind" in term.linguistic and term.linguistic["relation-kind"] != str(
            relation.relation
        ):
            value = separator.join([term.target_text, reference["name"]])
            if value not in detail_options:
                detail_options.append(value)
        if len(detail_options) == 3:
            break
    if len(detail_options) < 2:
        raise ValueError("A2 needs approved contrasting relation options")
    return [
        dict(option_id="detail-correct" if i == 0 else f"detail-{i}", label=v)
        for i, v in enumerate(detail_options)
    ]


_BUILDERS = {"A0": _build_a0, "A1": _build_a1, "A2": _build_a2}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """Reject missing A1 choice data before any model generation or repair calls."""
    if level != "A1":
        return
    spec = next(slot for slot in plan.slots if slot.slot_id == "chooseAttribute").specs[0]
    attribute = next(
        attr for attr in facts.scene_facts.attributes if attr.fact_id == spec.bindings["attribute"]
    )
    subject = next(term for term in vocabulary.terms if term.fact_id == spec.bindings["object"])
    _detail_options(facts, vocabulary, attribute, subject.agreement, include_pack=True, pack=pack)


def check_lesson(level, result, approved, pack):
    """Keep the existing count, order, grouping and interaction contract."""
    questions = result.questions
    if [question.purpose for question in questions] != PURPOSES[level]:
        raise ValueError("assembled M01 questions do not preserve the mission sequence")
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError("assembled M01 question IDs must be unique")
    if list(Counter(question.section for question in questions).values()) != _SECTION_SIZES[level]:
        raise ValueError("assembled M01 task grouping has changed")
    for sentence in approved:
        if (
            join_pack_chunks(sentence.candidate.chunks, pack.language.word_separator)
            != sentence.candidate.text
        ):
            raise ValueError("approved chunks no longer reconstruct the validated sentence")
    for question in questions:
        building = question.purpose in _BUILDING
        if (question.interaction_type == "sentenceBuilding") != building:
            raise ValueError("assembled M01 changed a question's interaction type")
        if building:
            if not question.correct_text or not question.token_bank or question.options:
                raise ValueError("assembled building question needs a native answer and tiles")
        else:
            ids = [option.option_id for option in question.options]
            if len(ids) < 2 or len(ids) != len(set(ids)) or question.correct_option_id not in ids:
                raise ValueError("assembled choices need unique IDs and an offered answer")


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=()):
    from app.services.mission_eligibility import confirmed_relations

    if str(mission.practice_level) == "A2" and not (
        any(attributes_of(obj) for obj in objects)
        or confirmed_relations(mission, objects, relations)
    ):
        return ["Confirm an object detail or relation for the scene description."]
    return []


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    phrase_slots={"A2": frozenset({"buildSceneDescription"})},
    photo_reasons=photo_reasons,
)
