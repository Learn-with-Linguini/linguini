"""M04 (whose is it?) as a pack lesson.

Possessive words and the role-play cast are reviewed pack data (``possessives.toml``);
the sentences that use them are generated. Who owns what is a lesson fact: the object
the learner says is theirs (A0), the saved role-play (A1), or a role-play assigned from
the photo (A2). Questions reuse dev's M04 models, validators and task builders.
"""

from __future__ import annotations

import re

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0_situations import (
    A0SituationLesson,
    validate_a0_situation_lesson,
)
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.ai.features.learning_tasks.mission_m04 import assemble_m04_lesson
from app.schemas.roleplay import parse_roleplay_facts
from app.services.lesson_tasks.a0_situations import (
    choice_question,
    marker_question,
    object_reference,
    prep_add,
    situation_lesson_task,
    target_texts,
)
from app.services.lesson_tasks.a2 import m04_a2_task
from app.services.lesson_tasks.m04 import m04_lesson_task, premise

from ..generation import ApprovedTerm, ApprovedVocabulary, ConfirmedOwner
from .base import PackMission, for_level
from .common import (
    LessonContext,
    SpecBuilder,
    check_questions,
    differently_named,
    latin_of,
    object_name,
    usable_objects,
)

MISSION_ID = "M04"
PURPOSES = {
    "A1": ["chooseOwner", "buildMine", "buildTheirs"],
    "A2": [
        "chooseAssignedObject", "choosePossessive", "buildBelonging", "clarifyOwnership",
        "buildOwnershipDescription",
    ],
}
LEARNER = "first"
A2_SECTIONS = (
    "Task 1 · Meet the role-play", "Task 2 · Clarify ownership", "Task 3 · Describe your belonging",
)
_FINAL = ".?!。？！"


# ---------------------------------------------------------------- vocabulary


def _possessor_term(term_id, fact_id, source, forms_by_key, romanization, owner):
    texts = list(dict.fromkeys(forms_by_key.values()))
    return ApprovedTerm(
        term_id=term_id, fact_id=fact_id, source_text=source, target_text=texts[0],
        forms=texts, forms_by_key=forms_by_key, part_of_speech="determiner",
        provenance="packData", romanization=romanization,
        linguistic={"possessor": owner},
    )


def _possessor_forms(pack, owner):
    """(English meaning, {key: text}, romanization) for ``first``, ``second`` or a cast ID."""
    possessives = pack.possessives
    if owner in {"first", "second"}:
        entry = possessives.get(owner)
        if entry is None or not entry.forms:
            return None
        return (entry.meaning, {form.key: form.text for form in entry.forms},
                entry.forms[0].romanization)
    member = possessives.member(owner)
    if member is None:
        return None
    third = possessives.get(f"third-{member.gender}")
    forms = {"name": member.name,
             **{form.key: form.text for form in (third.forms if third else [])}}
    return f"{member.english_name}'s", forms, member.romanization


def possessive_vocabulary(pack, facts, vocabulary):
    """The pack's possessors as alternatives, and one term per owner in the lesson.

    ``possessor-<who>`` terms (``first``, ``second`` and each cast owner) are what a
    lesson may name instead (your, Ana's); an owner term is the bound owner of one
    object, written with the possessor's forms.
    """
    if pack.possessives is None:
        return vocabulary
    terms = list(vocabulary.terms)
    owners = ["first", "second", *(member.owner_id for member in pack.possessives.cast)]
    for owner in owners:
        found = _possessor_forms(pack, owner)
        if found:
            meaning, forms, romanization = found
            terms.append(_possessor_term(f"possessor-{owner}", f"possessor:{owner}", meaning,
                                         forms, romanization, owner))
    for fact in facts.scene_facts.owners:
        found = _possessor_forms(pack, fact.owner)
        if found:
            meaning, forms, romanization = found
            terms.append(_possessor_term(fact.fact_id.replace(":", "-"), fact.fact_id, meaning,
                                         forms, romanization, fact.owner))
    return ApprovedVocabulary(terms=terms)


# ---------------------------------------------------------------- owners


def _owner_fact(obj, owner, fictional=True):
    return ConfirmedOwner(fact_id=f"owner:{obj.fact_id}", object_fact_id=obj.fact_id,
                          owner=owner, fictional=fictional)


def ownership_facts(pack, level, facts, vocabulary, context):
    """Owners from the learner's choice (A0), the saved role-play (A1) or the photo (A2)."""
    if facts.scene_facts.owners or pack.possessives is None:
        return facts
    objects = {str(obj.scene_object_id): obj for obj in usable_objects(facts, vocabulary)}
    owners = []
    if level == "A0":
        learner = context.get("learner_facts") or {}
        obj = objects.get(str(learner.get("ownedObjectId") or ""))
        if obj is not None:
            owners.append(_owner_fact(obj, LEARNER, bool(learner.get("pretend", False))))
    elif level == "A1":
        assigned = parse_roleplay_facts(context.get("roleplay_facts"), list(objects)) or []
        cast = {member.english_name: member.owner_id for member in pack.possessives.cast}
        for fact in assigned:
            obj = objects.get(str(fact.scene_object_id))
            owner = (LEARNER if fact.owner_type == "learner"
                     else cast.get((fact.owner_names or [None])[0]))
            if obj is not None and owner is not None and fact.fact_type == "ownership":
                owners.append(_owner_fact(obj, owner))
    elif level == "A2" and pack.possessives.cast:
        selection = a2_selection(facts, vocabulary)
        if selection is not None:
            assigned, alternative, _detail = selection
            owners += [_owner_fact(assigned, LEARNER),
                       _owner_fact(alternative, pack.possessives.cast[0].owner_id)]
    if not owners:
        return facts
    scene = facts.scene_facts.model_copy(update={"owners": owners})
    return facts.model_copy(update={"scene_facts": scene})


def a2_selection(facts, vocabulary):
    """(assigned, alternative, detail): an object with a translated detail the other lacks.

    As in dev's A2 selection, a same-named alternative is preferred, so the detail is
    what tells the learner's object apart.
    """
    objects = usable_objects(facts, vocabulary)
    terms = {term.fact_id for term in vocabulary.terms}
    attributes = [a for a in facts.scene_facts.attributes if a.fact_id in terms]
    relations = [r for r in facts.scene_facts.relations if r.fact_id in terms]

    def shares(other, detail):
        if detail in attributes:
            return any(a.object_fact_id == other.fact_id
                       and (a.kind, fold(a.value)) == (detail.kind, fold(detail.value))
                       for a in attributes)
        return any(r.subject_fact_id == other.fact_id and r.relation == detail.relation
                   and r.reference_fact_id == detail.reference_fact_id for r in relations)

    for assigned in objects:
        details = [a for a in attributes if a.object_fact_id == assigned.fact_id]
        details += [r for r in relations if r.subject_fact_id == assigned.fact_id]
        others = [o for o in objects if o.fact_id != assigned.fact_id]
        same = [o for o in others if fold(o.label) == fold(assigned.label)]
        others = same + [o for o in others if o not in same]
        for detail in details:
            for alternative in others:
                if alternative.fact_id != getattr(detail, "reference_fact_id", None) and not shares(
                    alternative, detail
                ):
                    return assigned, alternative, detail
    return None


def _owners(facts):
    return {fact.owner: fact for fact in facts.scene_facts.owners}


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed):
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, pack, facts, vocabulary, seed)
    return specs.build()


def _plan_a0(specs, pack, facts, vocabulary, _seed):
    owned = _owners(facts).get(LEARNER)
    if owned is None:
        raise ValueError("M04 A0 needs the object the learner says is theirs")
    objects = usable_objects(facts, vocabulary)
    target = next(obj for obj in objects if obj.fact_id == owned.object_fact_id)
    other = next((obj for obj in differently_named(objects, vocabulary)
                  if object_name(vocabulary, obj) != object_name(vocabulary, target)), None)
    if other is None:
        raise ValueError("M04 A0 needs another, differently named object")
    mine = {"object": target.fact_id, "owner": owned.fact_id}
    specs.add("askOwnership", "question", "ownership-question", {"object": target.fact_id},
              counterfactual={"owner": "possessor-second"})
    specs.add("answerOwnership", "answer", "ownership-statement", mine, suffix="mine")
    specs.add("answerOwnership", "option", "ownership-statement", mine, truth=False,
              suffix="not-mine")
    specs.add("sayOwnedObject", "answer", "owned-object", mine, suffix="mine")
    specs.add("sayOwnedObject", "option", "owned-object", {"object": target.fact_id},
              counterfactual={"owner": "possessor-second"}, suffix="yours")
    specs.add("sayOwnedObject", "option", "owned-object", {"object": other.fact_id},
              truth=False, counterfactual={"owner": "possessor-first"}, suffix="other")


def _plan_a1(specs, pack, facts, vocabulary, _seed):
    owners = _owners(facts)
    cast = [member.owner_id for member in pack.possessives.cast[:2]]
    if len(cast) < 2 or not {LEARNER, *cast} <= set(owners):
        raise ValueError("M04 A1 needs the role-play's three assigned owners")
    learner, ana, leo = owners[LEARNER], owners[cast[0]], owners[cast[1]]

    def owned_by(owned):
        return {"object": owned.object_fact_id, "owner": owned.fact_id}

    def owned_by_other(slot, owned, possessor, suffix):
        """The same object said to be someone else's: a contrast for options and tiles."""
        specs.add(slot, "option", "possessive-statement", {"object": owned.object_fact_id},
                  truth=False, counterfactual={"owner": possessor}, suffix=suffix)

    specs.add("chooseOwner", "answer", "possessive-statement", owned_by(leo), suffix="correct")
    owned_by_other("chooseOwner", leo, "possessor-first", "first")
    for slot, owned, contrast in (("buildMine", learner, f"possessor-{cast[0]}"),
                                  ("buildTheirs", ana, "possessor-first")):
        specs.add(slot, "question", "whose-question", {"object": owned.object_fact_id},
                  suffix="question")
        specs.add(slot, "answer", "possessive-statement", owned_by(owned), suffix="answer")
        owned_by_other(slot, owned, contrast, "contrast")


def _plan_a2(specs, pack, facts, vocabulary, _seed):
    owners = _owners(facts)
    cast_owner = pack.possessives.cast[0].owner_id if pack.possessives.cast else None
    if LEARNER not in owners or cast_owner not in owners:
        raise ValueError("M04 A2 needs an object with a detail another object lacks")
    mine, theirs = owners[LEARNER], owners[cast_owner]
    assigned = {"object": mine.object_fact_id, "owner": mine.fact_id}
    detail = _detail(facts, vocabulary, mine.object_fact_id, theirs.object_fact_id)
    if detail is None:
        raise ValueError("M04 A2 needs a detail that tells the learner's object apart")
    if hasattr(detail, "kind"):
        clue = {"target": mine.object_fact_id, "attribute": detail.fact_id}
        use = "attribute"
    else:
        clue = {"target": mine.object_fact_id, "relation": detail.fact_id,
                "reference": detail.reference_fact_id}
        use = "location"
    described = {"object": mine.object_fact_id, "owner": mine.fact_id,
                 **{key: value for key, value in clue.items() if key != "target"}}
    other = {"object": theirs.object_fact_id, "owner": theirs.fact_id}
    specs.add("chooseAssignedObject", use, "target-clue", clue)
    # The possessive is chosen in a sentence about the learner's own object: only "my" fits.
    specs.add("choosePossessive", "answer", "possessive-statement", assigned)
    specs.add("buildBelonging", "answer", "owned-description", described)
    specs.add("clarifyOwnership", "answer", "owned-object", other, labels=["no"], suffix="no")
    specs.add("clarifyOwnership", "option", "possessive-statement", assigned, labels=["yes"],
              suffix="yes")
    specs.add("clarifyOwnership", "option", "possessive-statement", assigned, labels=["no"],
              suffix="wrong")
    specs.add("buildOwnershipDescription", "answer", "owned-object", other, suffix="other")
    specs.add("buildOwnershipDescription", "option", "owned-object",
              {"object": mine.object_fact_id}, truth=False,
              counterfactual={"owner": f"possessor-{cast_owner}"}, suffix="wrong")


def _detail(facts, vocabulary, assigned_id, alternative_id):
    """The assigned object's detail that the alternative does not share."""
    selection = a2_selection(facts, vocabulary)
    if selection and (selection[0].fact_id, selection[1].fact_id) == (assigned_id, alternative_id):
        return selection[2]
    return None


_PLANNERS = {"A0": _plan_a0, "A1": _plan_a1, "A2": _plan_a2}


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    _spell_possessives(ctx)
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _spell_possessives(ctx):
    """Possessive words appear as options and tiles; record their spellings."""
    for entry in ctx.pack.possessives.possessors:
        for form in entry.forms:
            if form.romanization:
                ctx.extra_spellings[form.text] = form.romanization
    for member in ctx.pack.possessives.cast:
        if member.romanization:
            ctx.extra_spellings[member.name] = member.romanization


def _owner_of(ctx, owner):
    return next(fact for fact in ctx.facts.scene_facts.owners if fact.owner == owner)


def _row(ctx, object_fact_id):
    return ctx.by_fact[object_fact_id]


def _word(text, forms):
    """The longest of ``forms`` written as a whole word in ``text``, as written there."""
    for form in sorted(set(forms), key=len, reverse=True):
        match = re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _split_subject(text, row):
    """(subject, predicate) of an owned-object sentence: La taza | es mía, 컵은 | 제 거예요.

    The subject ends with the phrase holding the owned noun (with any particle or elided
    article attached); the predicate is the rest without final punctuation.
    """
    words = text.rstrip(_FINAL).rstrip().split()
    noun_words = fold(row["noun"]).split()
    if noun_words:
        for start in range(len(words) - len(noun_words)):
            end = start + len(noun_words)
            phrase = [fold(word).replace("\u2019", "'").split("'")[-1]
                      for word in words[start:end]]
            if phrase[:-1] == noun_words[:-1] and phrase[-1].startswith(noun_words[-1]):
                return " ".join(words[:end]), " ".join(words[end:])
    raise ValueError(f"M04 cannot find the owned noun in {text!r}")


def _final(text):
    return text[-1] if text and text[-1] in _FINAL else ""


def _build_a0(ctx):
    owned = _owner_of(ctx, LEARNER)
    x = _row(ctx, owned.object_fact_id)
    y = _row(ctx, next(spec.bindings["object"] for spec in ctx.specs("sayOwnedObject")
                        if spec.spec_id.endswith("-other")))
    is_yours = ctx.sentence_by_id("askOwnership", "question")
    mine = ctx.sentence_by_id("answerOwnership", "mine")
    not_mine = ctx.sentence_by_id("answerOwnership", "not-mine")
    x_mine = ctx.sentence_by_id("sayOwnedObject", "mine")
    x_yours = ctx.sentence_by_id("sayOwnedObject", "yours")
    y_mine = ctx.sentence_by_id("sayOwnedObject", "other")
    yes = ctx.label("yes-answer")
    terms = ctx.terms
    mine_word = _word(x_mine.text, terms[owned.fact_id].forms)
    yours_word = _word(x_yours.text, ctx.terms_by_id["possessor-second"].forms)
    if not mine_word or not yours_word:
        raise ValueError("M04 A0 sentences must use the taught possessives")
    subject, mine_predicate = _split_subject(x_mine.text, x)
    _yours_subject, yours_predicate = _split_subject(x_yours.text, x)
    q3 = f"{yes} {mine.text}"
    q6 = f"{yes} {x_mine.text}"
    yes_spelling = ctx.labels["yes-answer"].romanization
    for composed, sentence in ((q3, mine), (q6, x_mine)):
        if yes_spelling and sentence.romanization:
            ctx.extra_spellings[composed] = f"{yes_spelling} {latin_of(sentence)}"
    prep = []
    for sentence in (mine, not_mine, is_yours, x_mine, x_yours, y_mine):
        prep_add(prep, sentence.text, sentence.translation)
    prep_add(prep, q3, f"Yes. {mine.translation}")
    prep_add(prep, q6, f"Yes. {x_mine.translation}")
    rows = [x, y, *(row for row in ctx.rows if row["key"] not in {x["key"], y["key"]})][:3]
    payload = ctx.payload(
        title=ctx.mission.title, approvedObjects=rows, focusObjectId=x["key"],
        learnerFacts={"ownedObjectId": x["key"], "pretend": owned.fictional}, prep=prep,
    )
    section = "Lost and found"
    typed = not ctx.pack.language.romanization_required
    questions = [
        marker_question(payload, rows, x, section,
                         "Linguini found something. Which one is yours?", "recognise-ownership"),
        choice_question(
            "M04-Q2", "Listen to Linguini. What does Linguini ask?",
            "Listen to Linguini. What does Linguini ask?", section, x["key"],
            ["Is this yours?", "Do you like it?"], "Is this yours?", "recognise-ownership",
            payload, salt="q2", audio_text=is_yours.text, listen_first=True,
        ),
        choice_question(
            "M04-Q3", "Say that it is yours.", "Complete the answer to say it is yours.",
            section, x["key"], [mine.text, not_mine.text], mine.text, "say-mine", payload,
            salt="q3", gap_type="chunkChoice", slot_template=f"{yes} ___", complete_chunk=q3,
            complete_translation=f"Yes. {mine.translation}", typed_allowed=typed,
            accepted_text_answers=[mine.text, q3],
        ),
        choice_question(
            "M04-Q4", "Say that this object is yours.",
            "Complete the sentence to say this object is yours.",
            section, x["key"], [mine_predicate, yours_predicate], mine_predicate, "say-mine",
            payload, salt="q4", gap_type="chunkChoice",
            slot_template=f"{subject} ___{_final(x_mine.text)}", complete_chunk=x_mine.text,
            complete_translation=x_mine.translation, typed_allowed=typed,
            accepted_text_answers=[mine_predicate, x_mine.text],
        ),
        choice_question(
            "M04-Q5", "Listen, then complete the sentence.", "Listen, then complete the sentence.",
            section, x["key"], [mine_word, yours_word], mine_word, "say-mine", payload,
            salt="q5", gap_type="audioGap",
            slot_template=re.sub(rf"(?<!\w){re.escape(mine_word)}(?!\w)", "___", x_mine.text,
                                 count=1),
            complete_chunk=x_mine.text, complete_translation=x_mine.translation,
            audio_text=x_mine.text, listen_first=True,
        ),
        choice_question(
            "M04-Q6", "Tell Linguini this object is yours.",
            "Choose the answer that says this object is yours.",
            section, x["key"], [x_mine.text, y_mine.text], x_mine.text, "say-mine", payload,
            salt="q6", gap_type="dialogueGap", slot_template=f"{yes} ___", complete_chunk=q6,
            complete_translation=f"Yes. {x_mine.translation}",
            dialogue=[
                {"speaker": "linguini", "text": is_yours.text,
                 "translation": is_yours.translation},
                {"speaker": "learner", "text": f"{yes} ___",
                 "translation": f"Yes. {x_mine.translation}"},
            ],
            correct_note=f"Yes—Linguini knows the {x['source']} is yours.",
            outcome={"text": "Great—Linguini knows it is yours.", "kind": "returned",
                     "scene_object_id": x["key"]},
        ),
    ]
    questions[1].option_icons = {
        option.option_id: "belongs" if option.label == "Is this yours?" else "likes"
        for option in questions[1].options
    }
    # An assigned (pretend) owner is stated as the scenario on every question.
    scenario = f"Let's pretend the {object_reference(x)} is yours." if owned.fictional else None
    if not owned.fictional:
        questions[0].prompt = questions[0].instruction = (
            f"You said the {object_reference(x)} is yours. Tap it in your photo."
        )
    for item in questions:
        item.roleplay_premise = scenario
    payload["approvedTargetTexts"] = target_texts(prep, questions)
    result = A0SituationLesson(title=ctx.mission.title, questions=questions)
    validate_a0_situation_lesson(payload, result)
    task = situation_lesson_task(ctx.session_id, ctx.mission, payload, result,
                                 ctx.vocabulary_ids)
    return result, task, payload


def _build_a1(ctx):
    cast = ctx.pack.possessives.cast[:2]
    learner, ana, leo = (_owner_of(ctx, owner)
                         for owner in (LEARNER, cast[0].owner_id, cast[1].owner_id))
    names = {LEARNER: [], cast[0].owner_id: [cast[0].english_name],
             cast[1].owner_id: [cast[1].english_name]}
    objects = {obj.fact_id: obj for obj in ctx.facts.scene_facts.objects}
    answer_prompt = ctx.label("answer-in-sentence")

    def fact(owned):
        return dict(
            factType="ownership", sceneObjectId=str(objects[owned.object_fact_id].scene_object_id),
            ownerType="learner" if owned.owner == LEARNER else "namedCharacter",
            ownerNames=names[owned.owner],
            possessivePerson="first" if owned.owner == LEARNER else "third",
            possessiveNumber="singular", source="assignedRoleplay", isFictional=True,
        )

    facts = [fact(owned) for owned in (learner, ana, leo)]
    parsed = {str(item.scene_object_id): item
              for item in parse_roleplay_facts(facts, [item["sceneObjectId"] for item in facts])}

    def detail(owned, sentence, contrast, slot=None):
        row = _row(ctx, owned.object_fact_id)
        found = dict(
            objectKey=row["key"], marker=row["marker"], label=row["label"], noun=row["noun"],
            gender=row["gender"], sentence=sentence.text, contrast=contrast.text,
            nounPhrase=row["name"], premise=premise(parsed[row["key"]], row["label"]),
            ownerType=parsed[row["key"]].owner_type, ownerNames=parsed[row["key"]].owner_names,
        )
        if slot:
            question = ctx.sentence_by_id(slot, "question")
            found.update(build_prompt=f"{question.text} {answer_prompt}",
                         build_prompt_translation=f"{question.translation} Answer with a sentence.")
            if question.romanization:
                spelling = ctx.labels["answer-in-sentence"].romanization
                ctx.extra_spellings[found["build_prompt"]] = " ".join(
                    filter(None, ["".join(span.latin for span in question.romanization), spelling])
                )
        return found

    mine = detail(learner, ctx.sentence_by_id("buildMine", "answer"),
                  ctx.sentence_by_id("buildMine", "contrast"), "buildMine")
    theirs = detail(ana, ctx.sentence_by_id("buildTheirs", "answer"),
                    ctx.sentence_by_id("buildTheirs", "contrast"), "buildTheirs")
    choice = detail(leo, ctx.sentence_by_id("chooseOwner", "correct"),
                    ctx.sentence_by_id("chooseOwner", "first"))
    choice["other_object_sentence"] = theirs["sentence"]
    payload = ctx.payload(
        facts=facts, fact_details=[mine, theirs, choice],
        all_markers={item["objectKey"]: item["marker"] for item in (mine, theirs, choice)},
        learner=mine, ana=theirs, leo=choice, choice=choice,
        choose_prompt=ctx.label("choose-sentence"),
        choose_prompt_translation=ctx.labels["choose-sentence"].meaning,
        explanation=_explanation(ctx),
    )
    result = assemble_m04_lesson(payload)
    task = m04_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _explanation(ctx):
    """The pretend-owner note, with the pack's own possessive words."""
    def words(*possessors):
        entries = [ctx.pack.possessives.get(possessor) for possessor in possessors]
        return "/".join(dict.fromkeys(form.text for entry in entries if entry
                                      for form in entry.forms if form.use == "determiner"))

    third = words("third-masculine", "third-feminine")
    names = ", ".join(member.name for member in ctx.pack.possessives.cast[:2])
    parts = [f"{words('first')} = my",
             f"{third} = his/her" if third else f"other owners are named: {names}"]
    return f"For this practice, the owners are pretend. {' · '.join(parts)}."


def _determiner(ctx, possessor, row):
    """The possessive a learner picks for this noun (agreeing, before a vowel too)."""
    entry = ctx.pack.possessives.get(possessor)
    if entry is None:
        return None
    forms = [form for form in entry.forms if form.use == "determiner"]
    vowel = row["noun"][:1].casefold() in "aeiouyàâäéèêëîïôöùûüœh"
    for wanted in ((row["gender"], vowel), (row["gender"], False), (None, False)):
        found = next((form.text for form in forms
                      if form.agreement == wanted[0] and form.before_vowel == wanted[1]), None)
        if found:
            return found
    return None


def _build_a2(ctx):
    cast = ctx.pack.possessives.cast[0]
    mine, theirs = _owner_of(ctx, LEARNER), _owner_of(ctx, cast.owner_id)
    assigned, alternative = _row(ctx, mine.object_fact_id), _row(ctx, theirs.object_fact_id)
    s1, s2, s3 = A2_SECTIONS
    clue_spec = ctx.spec("chooseAssignedObject")
    clue = ctx.sentence("chooseAssignedObject")
    own = ctx.sentence("choosePossessive")
    belonging = ctx.sentence("buildBelonging")
    no, yes_answer, wrong = (ctx.sentence_by_id("clarifyOwnership", suffix)
                             for suffix in ("no", "yes", "wrong"))
    other = ctx.sentence_by_id("buildOwnershipDescription", "other")
    wrong_owner = ctx.sentence_by_id("buildOwnershipDescription", "wrong")
    roleplay = (f"Role-play: marker {assigned['marker']} is yours. "
               f"Marker {alternative['marker']} belongs to {cast.english_name}.")
    third = (_determiner(ctx, f"third-{cast.gender}", assigned) or cast.name)
    word = _word(own.text, ctx.terms[mine.fact_id].forms)
    if word is None:
        raise ValueError("M04 A2 needs the learner's possessive in its own sentence")
    possessives = [
        ("possessive-right", word),
        ("possessive-yours", _determiner(ctx, "second", assigned)),
        (f"possessive-{cast.owner_id}", third),
    ]
    if any(text is None for _key, text in possessives) or len(
        {fold(text) for _key, text in possessives}
    ) != 3:
        raise ValueError("M04 A2 needs three different possessive words for this noun")
    gap = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "___", own.text, count=1)
    choose_prompt = f"{ctx.label('which-is-yours')} {clue.text}"
    possessive_prompt = f"{ctx.label('choose-possessive')} {gap}"
    spellings = [_spelling(ctx.labels["which-is-yours"]), _spelling(clue)]
    if all(spellings):
        ctx.extra_spellings[choose_prompt] = " ".join(spellings)
    if own.romanization and ctx.labels["choose-possessive"].romanization:
        gap_spelling = "".join(
            (" ___" if span.native.startswith(" ") else "___")
            if span.native.strip() == word else span.latin
            for span in own.romanization
        )
        ctx.extra_spellings[possessive_prompt] = (
            f"{ctx.labels['choose-possessive'].romanization} {gap_spelling}"
        )
    final = _joined(ctx, belonging, other)

    def choice(qid, purpose, prompt, options, correct, section, key, **fields):
        rows = ctx.shuffle([dict(option_id=option_id, label=text) for option_id, text in options],
                           qid)
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="multipleChoice",
            options=rows, correct_option_id=correct, object_key=key, section=section,
            target_language_text=[prompt], **fields,
        )

    def building(qid, purpose, prompt, candidate, extras, section, key, *, phrase=False):
        tiles = ctx.chunks(candidate, extras, phrase=phrase, salt=qid)
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="sentenceBuilding",
            correct_text=tiles["correct_text"], token_bank=tiles["token_bank"],
            answer_chunks=tiles["answer_chunks"], distractor_chunks=tiles["distractor_chunks"],
            translation=candidate.translation, object_key=key, section=section,
            target_language_text=[prompt],
        )

    friend = ctx.label("friend-points", marker=str(alternative["marker"]))
    questions = [
        choice("m04-q1", "chooseAssignedObject", choose_prompt,
               [(assigned["key"], str(assigned["marker"])),
                (alternative["key"], str(alternative["marker"]))],
               assigned["key"], s1, assigned["key"], roleplay_premise=roleplay,
               marker_object_ids={assigned["key"]: assigned["key"],
                                  alternative["key"]: alternative["key"]}),
        choice("m04-q2", "choosePossessive", possessive_prompt, possessives, "possessive-right",
               s1, assigned["key"]),
        building("m04-q3", "buildBelonging", ctx.label("describe-your-object"), belonging,
                 [third], s1, assigned["key"]),
        choice("m04-q4", "clarifyOwnership", friend,
               [("owner-no", no.text), ("owner-yes", yes_answer.text), ("owner-wrong", wrong.text)],
               "owner-no", s2, alternative["key"], roleplay_premise=roleplay,
               group_object_ids=[alternative["key"]]),
        building("m04-q5", "buildOwnershipDescription", ctx.label("clarify-and-describe"), final,
                 [wrong_owner.text], s3, assigned["key"], phrase=True),
    ]
    detail_kind = "attribute" if "attribute" in clue_spec.bindings else "relationship"
    detail_key = clue_spec.bindings.get("attribute") or clue_spec.bindings.get("relation")
    payload = ctx.payload(
        approvedFacts=dict(
            approvedObjects=ctx.rows, sceneFacts=ctx.facts.model_dump(mode="json"),
            approvedVocabulary=ctx.vocabulary.model_dump(mode="json"),
            approvedRoleplayFacts=[
                {"kind": "ownership", "objectKey": assigned["key"], "owner": "learner",
                 "isFictional": True, "source": "assignedRoleplay"},
                {"kind": "ownership", "objectKey": alternative["key"], "owner": cast.english_name,
                 "isFictional": True, "source": "assignedRoleplay"},
            ],
        ),
        selection=dict(assignedObjectKey=assigned["key"], alternativeObjectKey=alternative["key"],
                       detailKind=detail_kind, detailKey=detail_key),
    )
    result = MissionA2Result(title="Identify your belonging clearly", questions=questions)
    task = m04_a2_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _spelling(part):
    """A label's or sentence's Latin spelling, when it has one."""
    if hasattr(part, "semantic"):
        return part.romanization
    return "".join(span.latin for span in part.romanization) or None


def _joined(ctx, first, second):
    """Two validated sentences as one answer, with aligned spellings when required."""
    separator = " " if ctx.pack.language.word_separator == "space" else ""
    spans = []
    if first.romanization and second.romanization:
        gap = first.romanization[0].model_copy(update={"native": separator, "latin": separator})
        spans = [*first.romanization, gap, *second.romanization]
    return first.model_copy(update={
        "text": f"{first.text}{separator}{second.text}",
        "translation": f"{first.translation} {second.translation}",
        "romanization": spans, "chunks": [],
    })


_BUILDERS = {"A0": _build_a0, "A1": _build_a1, "A2": _build_a2}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """Ownership needs the pack's possessive words and its role-play cast."""
    if pack.possessives is None:
        raise ValueError("M04 needs the pack's possessive words (possessives.toml)")
    if level != "A0" and len(pack.possessives.cast) < (2 if level == "A1" else 1):
        raise ValueError("M04 role-play needs the pack's cast owners")


def check_lesson(level, result, approved, pack):
    """Keep dev's M04 question count, order, interactions and answer contract."""
    if level in PURPOSES:
        check_questions(result.questions, PURPOSES[level], MISSION_ID)


CHOICE_REASON = "Tell Linguini which object is yours."


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=(),
                  mission_choices=None):
    """A0: a learner's own object, when they choose one, must be a photo object (without a
    choice the lesson assigns a pretend owner). A2: an object a confirmed detail tells apart."""
    level = str(mission.practice_level)
    by_id = {str(obj.id): obj for obj in objects}
    if level == "A0" and mission_choices is not None:
        choices = mission_choices.get("missionChoices", mission_choices)
        ownership = choices.get("ownership") or {}
        chosen = ownership.get("sceneObjectId", ownership.get("scene_object_id"))
        if ownership and str(chosen or "") not in by_id:
            return [CHOICE_REASON]
    if level == "A2" and not _distinguishable(objects, relations, attributes_of):
        return ["Confirm an object detail that distinguishes it from another photo object."]
    return []


def _distinguishable(objects, relations, attributes_of):
    """An object has an attribute or location that another object (not its reference) lacks."""
    details = {str(obj.id): {("attribute", kind, fold(value))
                             for _key, kind, value in attributes_of(obj)}
               for obj in objects}
    for relation in relations:
        subject = str(relation.subject_scene_object_id)
        if subject in details:
            details[subject].add(("relation", str(relation.relation),
                                  str(relation.reference_scene_object_id)))
    for key, found in details.items():
        for detail in found:
            for other in details:
                is_reference = detail[0] == "relation" and detail[2] == other
                if other != key and not is_reference and detail not in details[other]:
                    return True
    return False


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    photo_reasons=photo_reasons,
    vocabulary=possessive_vocabulary,
    facts=ownership_facts,
)
