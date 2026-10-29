"""M05 (say what you like) as a pack lesson.

Who likes what is a lesson fact: the learner's own choice (A0) or the saved role-play
(A1). The cast comes from the pack's ``possessives.toml``; the sentences are generated,
and a spec's use (``like`` or ``dislike``) sets the polarity its sentence must say.
Questions reuse dev's M05 models, validators and task builders.
"""

from __future__ import annotations

import re

from app.ai.features.learning_tasks.mission_a0_situations import (
    A0SituationLesson,
    validate_a0_situation_lesson,
)
from app.ai.features.learning_tasks.mission_m05 import assemble_m05_lesson
from app.schemas.roleplay import parse_roleplay_facts
from app.services.lesson_tasks.a0_situations import (
    choice_question,
    lower_first,
    marker_question,
    object_reference,
    prep_add,
    situation_lesson_task,
    target_texts,
)
from app.services.lesson_tasks.m05 import m05_lesson_task, premise

from ..generation import ApprovedTerm, ApprovedVocabulary, ConfirmedPreference
from .base import PackMission, for_level
from .common import (
    LessonContext,
    SpecBuilder,
    check_questions,
    differently_named,
    differing_parts,
    latin_of,
    object_name,
    usable_objects,
)

MISSION_ID = "M05"
PURPOSES = {"A1": ["choosePreference", "buildMyPreference", "buildTheirPreference"]}
LEARNER = "first"
CHOICE_REASON = "Tell Linguini what you would choose."
_FINAL = ".?!。？！"


# ---------------------------------------------------------------- vocabulary


def preference_vocabulary(pack, facts, vocabulary):
    """One term per cast member's preference: a sentence names them (A Ana le gusta…).

    The learner's own preferences need no term; first person is the construction's
    frame (Me gusta…, J'aime…).
    """
    if pack.possessives is None:
        return vocabulary
    terms = list(vocabulary.terms)
    for fact in facts.scene_facts.preferences:
        member = pack.possessives.member(fact.person)
        if member is None:
            continue
        terms.append(ApprovedTerm(
            term_id=fact.fact_id.replace(":", "-"), fact_id=fact.fact_id,
            source_text=member.english_name, target_text=member.name, forms=[member.name],
            forms_by_key={"name": member.name}, part_of_speech="other",
            provenance="packData", romanization=member.romanization,
            linguistic={"person": fact.person, "likes": fact.likes},
        ))
    return ApprovedVocabulary(terms=terms)


# ---------------------------------------------------------------- preferences


def _preference_fact(obj, person, likes, *, fictional=True, compared=None):
    return ConfirmedPreference(
        fact_id=f"preference:{obj.fact_id}", object_fact_id=obj.fact_id, person=person,
        likes=likes, fictional=fictional,
        compared_fact_id=compared.fact_id if compared is not None else None,
    )


def a0_choice(learner_facts):
    """(focus object ID, compared object IDs, reaction) of the learner's A0 choice."""
    preference = (learner_facts or {}).get("preference") or learner_facts or {}
    compared = [str(item) for item in preference.get(
        "sceneObjectIds", preference.get("scene_object_ids")) or []]
    chosen = preference.get("chosenObjectId", preference.get("chosen_object_id"))
    focus = str(chosen if len(compared) == 2 else compared[0] if compared else "")
    reaction = preference.get("reaction") or ("like" if len(compared) == 2 else None)
    return focus, compared, reaction


def preference_facts(pack, level, facts, vocabulary, context):
    """Likes from the learner's own choice (A0) or the saved role-play (A1)."""
    if facts.scene_facts.preferences:
        return facts
    objects = {str(obj.scene_object_id): obj for obj in usable_objects(facts, vocabulary)}
    preferences = []
    if level == "A0":
        focus, compared, reaction = a0_choice(context.get("learner_facts"))
        obj = objects.get(focus)
        other = next((objects[key] for key in compared if key != focus and key in objects), None)
        if obj is not None and reaction in {"like", "dislike"}:
            pretend = bool(((context.get("learner_facts") or {}).get("preference") or {})
                           .get("pretend", False))
            preferences.append(_preference_fact(obj, LEARNER, reaction == "like",
                                                fictional=pretend, compared=other))
    elif level == "A1" and pack.possessives is not None:
        assigned = parse_roleplay_facts(context.get("roleplay_facts"), list(objects)) or []
        cast = {member.english_name: member.owner_id for member in pack.possessives.cast}
        for fact in assigned:
            obj = objects.get(str(fact.scene_object_id))
            person = (LEARNER if fact.subject_type == "learner"
                      else cast.get((fact.subject_names or [None])[0]))
            if obj is not None and person is not None and fact.fact_type == "preference":
                preferences.append(_preference_fact(obj, person, fact.preference == "like"))
    if not preferences:
        return facts
    scene = facts.scene_facts.model_copy(update={"preferences": preferences})
    return facts.model_copy(update={"scene_facts": scene})


def _preferences(facts):
    return {fact.person: fact for fact in facts.scene_facts.preferences}


def _polarity(fact, truth):
    """The spec use that says ``fact`` (true) or its opposite (false)."""
    return "like" if fact.likes == truth else "dislike"


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed):
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, pack, facts, vocabulary, seed)
    return specs.build()


def _other_object(facts, vocabulary, target, preferred_id=None):
    """A differently named object to contrast with ``target``: the compared one first."""
    objects = differently_named(usable_objects(facts, vocabulary), vocabulary)
    others = [obj for obj in objects
              if object_name(vocabulary, obj) != object_name(vocabulary, target)]
    others.sort(key=lambda obj: obj.fact_id != preferred_id)
    return others[0] if others else None


def _plan_a0(specs, pack, facts, vocabulary, _seed):
    mine = _preferences(facts).get(LEARNER)
    if mine is None:
        raise ValueError("M05 A0 needs the object the learner chose and how they feel about it")
    objects = usable_objects(facts, vocabulary)
    target = next(obj for obj in objects if obj.fact_id == mine.object_fact_id)
    other = _other_object(facts, vocabulary, target, mine.compared_fact_id)
    if other is None:
        raise ValueError("M05 A0 needs another, differently named object")
    reaction = _polarity(mine, True)
    liked = {"object": target.fact_id, "preference": mine.fact_id}
    specs.add("askPreference", "question", "preference-question", {"object": target.fact_id})
    specs.add("sayPreference", "like", "my-preference", liked, truth=mine.likes, suffix="like")
    specs.add("sayPreference", "dislike", "my-preference", liked, truth=not mine.likes,
              suffix="dislike")
    # The same frame about the other object: the picture choices' second noun phrase.
    specs.add("sayPreference", reaction, "my-preference",
              {"object": other.fact_id, "preference": mine.fact_id}, truth=False,
              suffix="other")
    if mine.likes:
        specs.skip("sayChoice")
    else:
        # The learner takes the other object; the focus one in the same frame is the
        # wrong picture choice (a choice frame may mark the noun differently).
        specs.add("sayChoice", "answer", "choice-statement", {"object": other.fact_id},
                  suffix="other")
        specs.add("sayChoice", "option", "choice-statement", {"object": target.fact_id},
                  truth=False, suffix="focus")


def _plan_a1(specs, pack, facts, vocabulary, _seed):
    preferences = _preferences(facts)
    cast = [member.owner_id for member in pack.possessives.cast[:2]]
    if len(cast) < 2 or not {LEARNER, *cast} <= set(preferences):
        raise ValueError("M05 A1 needs the role-play's three assigned preferences")
    learner, ana, leo = preferences[LEARNER], preferences[cast[0]], preferences[cast[1]]
    if not learner.likes or ana.likes or not leo.likes:
        raise ValueError("M05 A1 needs the learner's and Leo's likes and Ana's dislike")

    def say(slot, construction, fact, truth, suffix):
        specs.add(slot, _polarity(fact, truth), construction,
                  {"object": fact.object_fact_id, "preference": fact.fact_id},
                  truth=truth, suffix=suffix)

    say("choosePreference", "their-preference", leo, True, "correct")
    say("choosePreference", "their-preference", leo, False, "flipped")
    # Leo's like said about the learner's object: right person and polarity, wrong object.
    specs.add("choosePreference", _polarity(leo, True), "their-preference",
              {"object": learner.object_fact_id, "preference": leo.fact_id}, truth=False,
              suffix="other")
    specs.add("buildMyPreference", "question", "preference-question",
              {"object": learner.object_fact_id}, suffix="question")
    say("buildMyPreference", "my-preference", learner, True, "answer")
    say("buildMyPreference", "my-preference", learner, False, "contrast")
    specs.add("buildTheirPreference", "question", "preference-question",
              {"object": ana.object_fact_id, "preference": ana.fact_id}, suffix="question")
    say("buildTheirPreference", "their-preference", ana, True, "answer")
    say("buildTheirPreference", "their-preference", ana, False, "contrast")


_PLANNERS = {"A0": _plan_a0, "A1": _plan_a1}


# ---------------------------------------------------------------- sentence parts


def _around(text, phrase):
    """(before, after) ``phrase`` in ``text``, without the spaces next to it."""
    index = text.find(phrase)
    if index < 0:
        return None
    return text[:index].rstrip(), text[index + len(phrase):].lstrip()


def _final(text):
    return text[-1] if text and text[-1] in _FINAL else ""


def _unpunctuated(text):
    return text.rstrip(_FINAL).rstrip()


def preference_gap(like, dislike, phrase):
    """(template, like chunk, dislike chunk): the words that say like or dislike.

    The noun phrase stays in the template; the gap is the side of it that differs
    (___ la taza. / 저는 컵을 ___.). When both sides differ, or one chunk would be
    empty (Ich mag die Tasse [nicht].), the whole sentences are the choices.
    """
    parts = [_around(text, phrase) for text in (like, dislike)]
    if None not in parts:
        (like_before, like_after), (dislike_before, dislike_after) = parts
        if like_after == dislike_after and like_before and dislike_before:
            rest = like[like.find(phrase):]
            return f"___ {rest}", like_before, dislike_before
        if like_before == dislike_before:
            options = _unpunctuated(like_after), _unpunctuated(dislike_after)
            if all(options) and _final(like) == _final(dislike):
                head = like[:like.find(phrase) + len(phrase)]
                return f"{head} ___{_final(like)}", *options
    return "___", like, dislike


def _gapped(text, phrase):
    if phrase not in text:
        raise ValueError(f"M05 cannot find {phrase!r} in {text!r}")
    return text.replace(phrase, "___", 1)


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    for member in pack.possessives.cast if pack.possessives else []:
        if member.romanization:
            ctx.extra_spellings[member.name] = member.romanization
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _preference_of(ctx, person):
    return next(fact for fact in ctx.facts.scene_facts.preferences if fact.person == person)


def _joined_spelling(ctx, *parts):
    """The Latin spelling of text composed from labels and sentences, when required."""
    if not ctx.pack.language.romanization_required:
        return None
    spellings = [part if isinstance(part, str) else latin_of(part) for part in parts]
    return " ".join(spellings) if all(spellings) else None


def _build_a0(ctx):
    mine = _preference_of(ctx, LEARNER)
    reaction = _polarity(mine, True)
    focus = ctx.by_fact[mine.object_fact_id]
    other_spec = next(spec for spec in ctx.specs("sayPreference")
                      if spec.spec_id.endswith("-other"))
    other = ctx.by_fact[other_spec.bindings["object"]]
    like = ctx.sentence_by_id("sayPreference", "like")
    dislike = ctx.sentence_by_id("sayPreference", "dislike")
    other_statement = ctx.sentence_by_id("sayPreference", "other")
    question = ctx.sentence("askPreference")
    statement = like if mine.likes else dislike
    phrases = differing_parts(statement.text, other_statement.text)
    if phrases is None:
        raise ValueError("M05 A0 needs the two objects' sentences to differ in their noun")
    focus_phrase, other_phrase = phrases
    template, like_chunk, dislike_chunk = preference_gap(like.text, dislike.text, focus_phrase)
    answer_word = ctx.label("yes-answer" if mine.likes else "no-answer")
    answer_word = answer_word.rstrip(".。")
    answer_spelling = ctx.labels["yes-answer" if mine.likes else "no-answer"].romanization
    q5_complete = f"{answer_word}, {lower_first(statement.text)}"
    q5_translation = f"{'Yes' if mine.likes else 'No'}, {statement.translation}"
    what = ctx.label("what-choose")
    choice = None if mine.likes else ctx.sentence_by_id("sayChoice", "other")
    if choice is not None:
        chosen = differing_parts(choice.text, ctx.sentence_by_id("sayChoice", "focus").text)
        if chosen is None:
            raise ValueError("M05 A0 needs the two choice sentences to differ in their noun")
        other_choice, focus_choice = chosen
        q6_complete = f"{dislike.text} {choice.text}"
        q6_translation = f"{dislike.translation} {choice.translation}"
        q6_template = f"{dislike.text} {_gapped(choice.text, other_choice)}"
        q6_options = [other_choice, focus_choice]
        q6_keys = {other_choice: other["key"], focus_choice: focus["key"]}
        q6_correct = other_choice
        note = f"You chose the {other['source']}."
        outcome = {"text": f"The {focus['source']} stays behind. {note}", "kind": "basket",
                   "scene_object_id": other["key"]}
    else:
        q6_complete, q6_translation = like.text, like.translation
        q6_template = _gapped(like.text, focus_phrase)
        q6_options = [focus_phrase, other_phrase]
        q6_keys = {focus_phrase: focus["key"], other_phrase: other["key"]}
        q6_correct = focus_phrase
        note = f"You chose the {focus['source']}."
        outcome = {"text": note, "kind": "basket", "scene_object_id": focus["key"]}

    if answer_spelling and statement.romanization:
        ctx.extra_spellings[q5_complete] = (
            f"{answer_spelling.rstrip('.')}, {lower_first(latin_of(statement))}"
        )
    if choice is not None and (spelling := _joined_spelling(ctx, dislike, choice)):
        ctx.extra_spellings[q6_complete] = spelling
    prep = []
    for sentence in (like, dislike, question):
        prep_add(prep, sentence.text, sentence.translation)
    prep_add(prep, what, ctx.labels["what-choose"].meaning)
    if choice is not None:
        prep_add(prep, choice.text, choice.translation)
    prep_add(prep, q5_complete, q5_translation)
    prep_add(prep, q6_complete, q6_translation)
    prep_add(prep, other_statement.text, other_statement.translation)

    rows = [focus, other, *(row for row in ctx.rows if row["key"] not in {focus["key"],
                                                                           other["key"]})][:3]
    payload = ctx.payload(
        title=ctx.mission.title, approvedObjects=rows, focusObjectId=focus["key"],
        learnerFacts={"preference": {**_learner_choice(ctx, mine, focus, reaction),
                                     "pretend": mine.fictional}},
        prep=prep, negativeMarker=dislike_chunk,
    )
    section = "Picnic choice"
    typed = not ctx.pack.language.romanization_required
    q3_correct = like_chunk if mine.likes else dislike_chunk
    # An assigned (pretend) choice is stated as the scenario on every question.
    scenario = a0_scenario(mine, focus, other)
    feeling = "like" if mine.likes else "don't like"
    question_feeling = "do you like" if mine.likes else "don't you like"
    pick = (f"You said you {feeling} the {object_reference(focus)}. Tap it in your photo."
            if scenario is None else
            f"In this scenario, which object {question_feeling}? Tap it in your photo.")
    questions = [
        marker_question(payload, rows, focus, section, pick, "recognise-preference"),
        choice_question(
            "M05-Q2", "Listen to the sentence. Like or don't like?",
            "Listen to the sentence. Like or don't like?", section, focus["key"],
            ["Like", "Don't like"], "Like" if mine.likes else "Don't like",
            "recognise-preference", payload, salt="q2", audio_text=statement.text,
            listen_first=True,
        ),
        choice_question(
            "M05-Q3", f"Say that you {feeling} this object.",
            f"Complete the sentence to say you {feeling} this object.",
            section, focus["key"], [like_chunk, dislike_chunk], q3_correct, "say-preference",
            payload, salt="q3", gap_type="chunkChoice", slot_template=template,
            complete_chunk=statement.text, complete_translation=statement.translation,
            typed_allowed=typed, accepted_text_answers=[q3_correct, statement.text],
        ),
    ]
    questions[1].option_icons = {
        option.option_id: "like" if option.label == "Like" else "dislike"
        for option in questions[1].options
    }
    picture = choice_question(
        "M05-Q4", "Choose the object that completes the sentence.",
        "Choose the object that completes the sentence.", section, focus["key"],
        [focus_phrase, other_phrase], focus_phrase, "say-preference", payload, salt="q4",
        gap_type="pictureToBlank", slot_template=_gapped(statement.text, focus_phrase),
        complete_chunk=statement.text, complete_translation=statement.translation,
    )
    keys = {focus_phrase: focus["key"], other_phrase: other["key"]}
    picture.option_object_keys = {option.option_id: keys[option.label]
                                  for option in picture.options}
    questions.append(picture)
    questions.append(choice_question(
        "M05-Q5", "Finish the conversation.", "Choose the answer that finishes the conversation.",
        section, focus["key"], [lower_first(like.text), lower_first(dislike.text)],
        lower_first(statement.text), "say-preference", payload, salt="q5",
        gap_type="dialogueGap", slot_template=f"{answer_word}, ___", complete_chunk=q5_complete,
        complete_translation=q5_translation,
        dialogue=[
            {"speaker": "linguini", "text": question.text, "translation": question.translation},
            {"speaker": "learner", "text": f"{answer_word}, ___",
             "translation": f"{'Yes' if mine.likes else 'No'}, ___"},
        ],
    ))
    last_instruction = (
        f"For this practice, choose the {object_reference(other)}. Complete the sentence."
        if not mine.likes else
        f"Complete the sentence about the {object_reference(focus)} you like."
    )
    last = choice_question(
        "M05-Q6", last_instruction, last_instruction,
        section, focus["key"], q6_options, q6_correct, "say-preference", payload, salt="q6",
        gap_type="dialogueGap", slot_template=q6_template, complete_chunk=q6_complete,
        complete_translation=q6_translation,
        dialogue=[
            {"speaker": "linguini", "text": what,
             "translation": ctx.labels["what-choose"].meaning},
            {"speaker": "learner", "text": q6_template, "translation": q6_translation},
        ],
        correct_note=note, outcome=outcome,
    )
    last.option_object_keys = {option.option_id: q6_keys[option.label]
                               for option in last.options}
    questions.append(last)
    for item in questions:
        item.roleplay_premise = scenario
    payload["approvedTargetTexts"] = target_texts(prep, questions)
    result = A0SituationLesson(title=ctx.mission.title, questions=questions)
    validate_a0_situation_lesson(payload, result)
    task = situation_lesson_task(ctx.session_id, ctx.mission, payload, result,
                                 ctx.vocabulary_ids)
    return result, task, payload


def a0_scenario(mine, focus, other):
    """The assigned A0 choice, said in English; ``None`` for the learner's own choice."""
    if not mine.fictional:
        return None
    if mine.likes:
        return f"Let's pretend you like the {object_reference(focus)}."
    return (f"Let's pretend you don't like the {object_reference(focus)}, "
            f"so you pick the {object_reference(other)}.")


def _learner_choice(ctx, mine, focus, reaction):
    """What the learner chose, as dev records it: the objects compared, and the pick."""
    compared = ctx.by_fact.get(mine.compared_fact_id) if mine.compared_fact_id else None
    if compared is None:
        return {"sceneObjectIds": [focus["key"]], "chosenObjectId": None, "reaction": reaction}
    return {"sceneObjectIds": [focus["key"], compared["key"]], "chosenObjectId": focus["key"],
            "reaction": reaction}


def _build_a1(ctx):
    cast = ctx.pack.possessives.cast[:2]
    learner, ana, leo = (_preference_of(ctx, person)
                         for person in (LEARNER, cast[0].owner_id, cast[1].owner_id))
    names = {LEARNER: [], cast[0].owner_id: [cast[0].english_name],
             cast[1].owner_id: [cast[1].english_name]}
    objects = {obj.fact_id: obj for obj in ctx.facts.scene_facts.objects}
    answer_prompt = ctx.label("answer-in-sentence")

    def fact(preference):
        return dict(
            factType="preference",
            sceneObjectId=str(objects[preference.object_fact_id].scene_object_id),
            subjectType="learner" if preference.person == LEARNER else "namedCharacter",
            subjectNames=names[preference.person],
            subjectPerson="first" if preference.person == LEARNER else "third",
            subjectNumber="singular", preference="like" if preference.likes else "dislike",
            source="assignedRoleplay", isFictional=True,
        )

    facts = [fact(preference) for preference in (learner, ana, leo)]
    parsed = {str(item.scene_object_id): item
              for item in parse_roleplay_facts(facts, [item["sceneObjectId"] for item in facts])}

    def detail(preference, sentence, contrast, slot=None):
        row = ctx.by_fact[preference.object_fact_id]
        assigned = parsed[row["key"]]
        found = dict(
            objectKey=row["key"], marker=row["marker"], label=row["label"], noun=row["noun"],
            gender=row["gender"], sentence=sentence.text, contrast=contrast.text,
            nounPhrase=row["name"], premise=premise(assigned, row["label"]),
            subjectType=assigned.subject_type, subjectNames=assigned.subject_names,
            preference=assigned.preference,
            person="first" if preference.person == LEARNER else "third",
            name=(assigned.subject_names or [None])[0], like=preference.likes,
        )
        if slot:
            question = ctx.sentence_by_id(slot, "question")
            found.update(build_prompt=f"{question.text} {answer_prompt}",
                         build_prompt_translation=f"{question.translation} Answer with a sentence.")
            if question.romanization:
                spelling = ctx.labels["answer-in-sentence"].romanization
                ctx.extra_spellings[found["build_prompt"]] = " ".join(
                    filter(None, [latin_of(question), spelling])
                )
        return found

    mine = detail(learner, ctx.sentence_by_id("buildMyPreference", "answer"),
                  ctx.sentence_by_id("buildMyPreference", "contrast"), "buildMyPreference")
    theirs = detail(ana, ctx.sentence_by_id("buildTheirPreference", "answer"),
                    ctx.sentence_by_id("buildTheirPreference", "contrast"),
                    "buildTheirPreference")
    choice = detail(leo, ctx.sentence_by_id("choosePreference", "correct"),
                    ctx.sentence_by_id("choosePreference", "flipped"))
    choice["other_object_sentence"] = ctx.sentence_by_id("choosePreference", "other").text
    payload = ctx.payload(
        facts=facts, fact_details=[mine, theirs, choice],
        all_markers={item["objectKey"]: item["marker"] for item in (mine, theirs, choice)},
        learner=mine, ana=theirs, leo=choice, choice=choice,
        choose_prompt=ctx.label("choose-sentence"),
        choose_prompt_translation=ctx.labels["choose-sentence"].meaning,
        explanation=_explanation(ctx, mine, choice, cast[1].english_name),
    )
    result = assemble_m05_lesson(payload)
    task = m05_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _explanation(ctx, mine, choice, name):
    """The pretend-likes note, with the lesson's own frames (Me gusta… = I like…).

    Frames come from accepted sentences with the noun phrase taken out, so no answer
    is shown whole; a frame that cannot be found is left out.
    """
    parts = []
    phrases = differing_parts(choice["sentence"], choice["other_object_sentence"])
    if phrases is not None:
        their_phrase, mine_phrase = phrases

        def frame(text, phrase):
            if phrase not in text:
                return None
            return re.sub(r"\s+…", "…", _unpunctuated(text.replace(phrase, "…", 1)))

        for text, phrase, meaning in (
            (mine["sentence"], mine_phrase, "I like…"),
            (mine["contrast"], mine_phrase, "I don't like…"),
            (choice["sentence"], their_phrase, f"{name} likes…"),
        ):
            if found := frame(text, phrase):
                parts.append(f"{found} = {meaning}")
    note = "For this practice, the likes are pretend."
    return f"{note} {' · '.join(parts)}" if parts else note


_BUILDERS = {"A0": _build_a0, "A1": _build_a1}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """The role-play names the pack's cast."""
    if level == "A1" and (pack.possessives is None or len(pack.possessives.cast) < 2):
        raise ValueError("M05 role-play needs the pack's cast (possessives.toml)")


def check_lesson(level, result, approved, pack):
    """Keep dev's M05 question count, order, interactions and answer contract."""
    if level in PURPOSES:
        check_questions(result.questions, PURPOSES[level], MISSION_ID)


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=(),
                  mission_choices=None):
    """A0: a learner's own choice, when they make one, names a photo object and whether they
    like it (without a choice the lesson assigns a pretend scenario)."""
    if str(mission.practice_level) != "A0" or mission_choices is None:
        return []
    choices = mission_choices.get("missionChoices", mission_choices)
    preference = choices.get("preference") or {}
    if not preference:
        return []
    focus, _compared, reaction = a0_choice({"preference": preference})
    if focus not in {str(obj.id) for obj in objects} or reaction not in {"like", "dislike"}:
        return [CHOICE_REASON]
    return []


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    photo_reasons=photo_reasons,
    vocabulary=preference_vocabulary,
    facts=preference_facts,
)
