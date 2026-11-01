"""M06 (ask for the details) as a pack lesson.

The order is a lesson fact: dev's seeded M06 transaction (the photo item, how many,
a size for café drinks, the detail the server asks about and the one detail the
server may repeat wrongly). Order quantities and detail words are pack data
(``requests.toml``); every sentence is generated. Questions reuse dev's M06
question model, validator and two-task builder, so grading, wrong-field feedback,
assistance steps and the scenario card stay unchanged.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_m06 import (
    M06Question,
    MissionM06Result,
    validate_m06_lesson,
)
from app.schemas.tasks import VocabularyChoice
from app.services.lesson_tasks.m06 import (
    SCENARIO_PROMPTS,
    build_m06_tasks,
    opposite_value,
    order_label,
    quantity_choices,
    scenario_of,
    select_transaction,
)
from app.services.mission_m06_lexicon import ITEMS, normalize_item_label, requestable_objects
from app.services.quantities import ENGLISH_NUMBERS

from ..generation import (
    ApprovedTerm,
    ApprovedVocabulary,
    ConfirmedOrder,
    ConfirmedRequest,
    derive_chunks,
)
from .base import PackMission, for_level
from .common import (
    LessonContext,
    SpecBuilder,
    differing_parts,
    usable_objects,
    with_romanization,
)

MISSION_ID = "M06"
PURPOSES = {
    "A2": [
        "listenOrderCard", "politeChunkGap", "buildRequest", "identifyMissingDetail",
        "replyWithDetail", "confirmOrRepair",
    ],
}
REQUEST_REASON = "Confirm a food, drink or everyday object you could ask for."
# The polite frame each scenario teaches: order (café, shop), borrow, or ask to pass.
FRAMES = {"cafe": "order", "shop": "order", "classroom": "borrow", "home": "pass"}
# The follow-up question's use names the detail it asks about.
ASK = {
    "serviceSetting": "askServiceSetting", "temperature": "askTemperature",
    "size": "askSize", "colour": "askColour",
}
SECTIONS = 3  # questions in "Task 1 · Place the order"; the rest finish the order
_FINAL = ".?!。？！"


# ---------------------------------------------------------------- order facts


def detail_key(field, value):
    """The pack key of a transaction detail (dev calls a large follow-up size big)."""
    if field == "size" and value == "big":
        value = "large"
    return f"{field}:{value}"


def _detail_term(key):
    return "detail-" + key.replace(":", "-").lower()


def _reply_mode(saved, progress):
    """How the reply is practised, from the learner's M06 history (as dev decides)."""
    mode = (saved or {}).get("q5Mode") or progress.get("m06Q5Mode")
    if mode is not None:
        return mode
    if progress.get("m06IndependentQ5", 0) >= 2:
        return "openCloze"
    return "wordBank" if progress.get("m06CompletedLessons", 0) >= 1 else "chunkChoice"


def order_facts(pack, level, facts, vocabulary, context):
    """The role-play order: the first requestable photo object (or the saved one) and
    dev's seeded transaction for it, with one request fact per ordered detail."""
    if facts.scene_facts.orders:
        return facts
    candidates = [
        (obj, ITEMS[key]) for obj in usable_objects(facts, vocabulary)
        if (key := normalize_item_label(obj.label))
    ]
    if not candidates:
        return facts
    candidates.sort(key=lambda pair: (
        pair[0].marker if pair[0].marker is not None else 10**6, str(pair[0].scene_object_id),
    ))
    progress = context.get("progress") or {}
    saved = progress.get("m06Transaction") or None
    chosen = next((pair for pair in candidates
                   if saved and str(pair[0].scene_object_id) == str(saved.get("sceneObjectId"))),
                  None)
    if chosen is None:
        saved = None
    obj, item = chosen or candidates[0]
    transaction = dict(saved) if saved else select_transaction(
        context.get("seed", ""), item, pack.language.code,
    )
    transaction.update(
        sceneObjectId=str(obj.scene_object_id), itemKey=item.key, itemLabel=item.label,
        scenario=item.category, targetLanguage=pack.language.code,
        # Choosing another item would need new sentences, so a pack lesson offers none.
        alternatives=[], scenarioAccepted=bool(transaction.get("scenarioAccepted", False)),
        q5Mode=_reply_mode(saved, progress),
    )
    requests = [ConfirmedRequest(fact_id="request:quantity", object_fact_id=obj.fact_id,
                                 field="quantity", value=str(transaction["quantity"]))]
    details = [("size", size)] if (size := transaction["requestDetails"].get("size")) else []
    details.append((transaction["followUp"]["type"], transaction["followUp"]["value"]))
    for field, value in details:
        requests.append(ConfirmedRequest(
            fact_id=f"request:{field}", object_fact_id=obj.fact_id, field=field,
            value=detail_key(field, value).split(":", 1)[1],
        ))
    scene = facts.scene_facts.model_copy(update={
        "orders": [ConfirmedOrder(fact_id="order", object_fact_id=obj.fact_id,
                                  scenario=item.category, transaction=transaction)],
        "requests": requests,
    })
    return facts.model_copy(update={"scene_facts": scene})


# ---------------------------------------------------------------- vocabulary


def request_vocabulary(pack, facts, vocabulary):
    """The pack's order words, plus one term per detail of this order.

    ``number-N`` and ``detail-<field>-<value>`` terms are the alternatives a lesson may
    name (a wrong quantity tile, a server's wrong repeat); a ``request-<field>`` term is
    the order's own quantity or detail, written in every form the pack gives it.
    """
    if pack.requests is None:
        return vocabulary
    terms = list(vocabulary.terms)
    for quantity in pack.requests.quantities:
        terms.append(_term(f"number-{quantity.value}", f"number:{quantity.value}",
                           ENGLISH_NUMBERS.get(quantity.value, str(quantity.value)),
                           quantity.forms, "determiner", {"quantity": str(quantity.value)}))
    for detail in pack.requests.details:
        terms.append(_term(_detail_term(detail.detail), f"detail:{detail.detail}",
                           detail.meaning, detail.forms, "phrase",
                           {"field": detail.field, "value": detail.value}))
    for fact in facts.scene_facts.requests:
        if fact.field == "quantity":
            entry = pack.requests.quantity(int(fact.value))
            meaning = ENGLISH_NUMBERS.get(int(fact.value), fact.value)
            part_of_speech = "determiner"
        else:
            entry = pack.requests.detail(f"{fact.field}:{fact.value}")
            meaning = entry.meaning if entry else fact.value
            part_of_speech = "phrase"
        if entry is None:
            continue
        terms.append(_term(f"request-{fact.field.lower()}", fact.fact_id, meaning, entry.forms,
                           part_of_speech, {"field": fact.field, "value": fact.value}))
    return ApprovedVocabulary(terms=terms)


def _term(term_id, fact_id, meaning, forms, part_of_speech, linguistic):
    return ApprovedTerm(
        term_id=term_id, fact_id=fact_id, source_text=meaning, target_text=forms[0],
        forms=list(forms), forms_by_key={"default": forms[0]}, part_of_speech=part_of_speech,
        provenance="packData", linguistic=linguistic,
    )


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed):
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, pack, facts, vocabulary, seed)
    return specs.build()


def _order(facts):
    if not facts.scene_facts.orders:
        raise ValueError("M06 needs a confirmed food, drink or everyday object to ask for")
    return facts.scene_facts.orders[0]


def _roles(order):
    """Order role -> request fact: the item, its quantity and size, the asked detail."""
    transaction = order.transaction
    roles = {"object": order.object_fact_id, "quantity": "request:quantity"}
    if transaction["requestDetails"].get("size"):
        roles["size"] = "request:size"
    roles["detail"] = f"request:{transaction['followUp']['type']}"
    return roles


def _mismatch_role(transaction):
    """The role the server repeats wrongly: quantity, the asked detail or the size."""
    field = transaction["mismatch"]["field"]
    if field == "quantity":
        return "quantity"
    return "detail" if field == transaction["followUp"]["type"] else "size"


def _alternative(role, transaction, value):
    """The term that states ``value`` for an order role."""
    if role == "quantity":
        return f"number-{value}"
    field = transaction["followUp"]["type"] if role == "detail" else "size"
    return _detail_term(detail_key(field, value))


def _other_detail(follow_type):
    """A reply about another detail (dev's third reply choice)."""
    other = ("serviceSetting" if follow_type == "colour"
             else "colour" if follow_type == "serviceSetting" else "serviceSetting")
    return other, "takeAway" if other == "serviceSetting" else "blue"


def _plan_a2(specs, pack, facts, vocabulary, _seed):
    order = _order(facts)
    transaction = order.transaction
    target = order.object_fact_id
    roles = _roles(order)
    follow_type = transaction["followUp"]["type"]
    follow_value = transaction["followUp"]["value"]
    mismatch = transaction["mismatch"]

    request = {role: fact for role, fact in roles.items() if role != "detail"}
    specs.add("listenOrderCard", FRAMES[order.scenario], "polite-request", request,
              suffix="request")
    # The order phrase as written inside the request locates its polite frame.
    specs.add("politeChunkGap", "request", "order-phrase", request, suffix="order")
    # The same phrase with another quantity: the wrong tiles of the built request.
    wrong = next(number for number in quantity_choices(order.scenario)
                 if number != transaction["quantity"])
    specs.add("buildRequest", "request", "order-phrase",
              {role: fact for role, fact in request.items() if role != "quantity"},
              truth=False, counterfactual={"quantity": f"number-{wrong}"},
              suffix="wrong-quantity")
    specs.add("identifyMissingDetail", ASK[follow_type], "detail-question", {"target": target},
              suffix="question")

    specs.add("replyWithDetail", "reply", "detail-reply",
              {"target": target, "detail": roles["detail"]}, suffix="reply")
    mode = transaction["q5Mode"]
    if mode in {"chunkChoice", "wordBank"}:
        opposite = opposite_value(follow_type, follow_value)
        specs.add("replyWithDetail", "reply", "detail-reply", {"target": target}, truth=False,
                  counterfactual={"detail": _alternative("detail", transaction, opposite)},
                  suffix="wrong-value")
    if mode == "chunkChoice":
        other = detail_key(*_other_detail(follow_type))
        specs.add("replyWithDetail", "reply", "detail-reply", {"target": target}, truth=False,
                  counterfactual={"detail": _detail_term(other)}, suffix="other-detail")

    repeat, counterfactual = dict(roles), {}
    if mismatch["flag"]:
        role = _mismatch_role(transaction)
        repeat.pop(role)
        counterfactual = {role: _alternative(role, transaction, mismatch["servedValue"])}
    # The server's repeat is false when it gets one detail wrong.
    specs.add("confirmOrRepair", "repeat", "order-repeat", repeat,
              truth=not mismatch["flag"], counterfactual=counterfactual, suffix="repeat")
    specs.add("confirmOrRepair", "confirm", "order-confirmation", {}, suffix="confirm")
    role = _mismatch_role(transaction) if mismatch["flag"] else "detail"
    specs.add("confirmOrRepair", "repair", "order-repair", {"target": target, role: roles[role]},
              suffix="repair")
    # The served (or, without a mistake, the other) value: the wrong-value tile.
    wrong_value = (mismatch["servedValue"] if mismatch["flag"]
                   else opposite_value(follow_type, follow_value))
    specs.add("confirmOrRepair", "repair", "order-repair", {"target": target}, truth=False,
              counterfactual={role: _alternative(role, transaction, wrong_value)},
              suffix="wrong-value")


_PLANNERS = {"A2": _plan_a2}


# ---------------------------------------------------------------- sentence parts


def _final(text):
    return text[-1] if text and text[-1] in _FINAL else ""


def _unpunctuated(text):
    return text.rstrip(_FINAL).rstrip()


def request_gap(request, phrase):
    """(template, polite chunk): the request with its polite frame taken out.

    The frame is the side of the order phrase that carries it: before the phrase
    (Quisiera ___, ¿Me pasas ___) or, when nothing precedes it, after it
    (작은 커피 두 잔 ___.).
    """
    match = re.search(re.escape(phrase), request, re.IGNORECASE)
    if match is None:
        raise ValueError(f"M06 cannot find the order phrase {phrase!r} in {request!r}")
    before = request[:match.start()].rstrip()
    if any(char.isalpha() for char in before):
        return f"___ {request[match.start():]}", before
    after = request[match.end():]
    final = _final(after)
    chunk = after[:len(after) - len(final)].strip()
    if not any(char.isalpha() for char in chunk):
        raise ValueError(f"M06 cannot find a polite frame around {phrase!r} in {request!r}")
    return f"{request[:match.end()]} ___{final}", chunk


def short_reply(reply):
    """The detail a reply gives, without its politeness tail (Para llevar)."""
    return _unpunctuated(reply).split(",", 1)[0].strip()


def _words(text):
    return [word for word in re.findall(r"[^\s.,!?;:¿¡]+", text)]


def _phrase_chunks(ctx, candidate):
    language = ctx.pack.language
    derived = derive_chunks(candidate, language.word_separator, phrase_chunks=True,
                            phrase_boundaries=language.phrase_boundaries)
    return [chunk.text for chunk in derived.chunks]


def _new(chunks, *taken):
    """``chunks`` not already among ``taken``, once each."""
    seen = {fold(chunk) for group in taken for chunk in group}
    found = []
    for chunk in chunks:
        if fold(chunk) not in seen:
            seen.add(fold(chunk))
            found.append(chunk)
    return found


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    return for_level(_BUILDERS, level, MISSION_ID)(ctx)


def _choices(ctx, choices, salt):
    shuffled = ctx.shuffle(choices, salt)
    return shuffled, [VocabularyChoice(option_id=key, label=label) for key, label, *_ in shuffled]


def _build_a2(ctx):
    order = _order(ctx.facts)
    transaction = dict(order.transaction)
    item = ITEMS[transaction["itemKey"]]
    scenario = transaction["scenario"]
    quantity = transaction["quantity"]
    size = transaction["requestDetails"].get("size")
    follow_type = transaction["followUp"]["type"]
    mismatch = transaction["mismatch"]
    mode = transaction["q5Mode"]

    request = ctx.sentence_by_id("listenOrderCard", "request")
    question = ctx.sentence_by_id("identifyMissingDetail", "question")
    reply = ctx.sentence_by_id("replyWithDetail", "reply")
    repeat = ctx.sentence_by_id("confirmOrRepair", "repeat")

    # Q1: the order heard, as dev's English order cards (one wrong field each).
    fields = {"item": item.key, "quantity": quantity, **transaction["requestDetails"]}
    wrong_quantity = next(number for number in quantity_choices(scenario) if number != quantity)
    cards = [("correct", order_label(quantity, item, size), fields),
             ("wrong-quantity", order_label(wrong_quantity, item, size),
              {**fields, "quantity": wrong_quantity})]
    if size:
        wrong_size = "large" if size == "small" else "small"
        cards.append(("wrong-size", order_label(quantity, item, wrong_size),
                      {**fields, "size": wrong_size}))
    else:
        other = next(candidate for candidate in ITEMS.values()
                     if candidate.category == item.category and candidate.key != item.key)
        cards.append(("wrong-item", order_label(quantity, other), {**fields, "item": other.key}))
    cards, options = _choices(ctx, cards, "q1")
    q1 = M06Question(
        question_id="m06-q1", purpose="listenOrderCard", prompt="Which order did you hear?",
        interaction_type="multipleChoice", options=options, correct_option_id="correct",
        audio_text=request.text, listen_first=True, gap_kind="orderCard",
        assistance_steps=["replayAudio", "visualDetail", "phraseOnset", "chunkBank", "fullModel"],
        target_id="understand-order", evidence_type="recognition",
        option_fields={
            key: {name: str(value) for name, value in values.items()
                  if fields.get(name) != value}
            for key, _label, values in cards
        },
        distractor_fields={key: key.removeprefix("wrong-") for key, *_ in cards
                           if key != "correct"},
    )

    # Q2: the polite frame, against the pack's two wrong frames.
    phrase = ctx.sentence_by_id("politeChunkGap", "order").text
    template, polite = request_gap(request.text, phrase)
    have, exists = ctx.label("request-distractor-have"), ctx.label("request-distractor-exists")
    _cards, options = _choices(ctx, [("correct", polite), ("wrong-a", have),
                                     ("wrong-b", exists)], "q2")
    q2 = M06Question(
        question_id="m06-q2", purpose="politeChunkGap",
        prompt="Choose the polite phrase that completes the request.",
        interaction_type="multipleChoice", options=options, correct_option_id="correct",
        slot_template=template, complete_chunk=request.text, gap_kind="functionalChunk",
        assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
        target_id="use-request-chunk", evidence_type="recognition",
        distractor_fields={"wrong-a": "functionalChunk", "wrong-b": "functionalChunk"},
    )

    # Q3: build the request; the wrong quantity's words and a wrong frame are extra tiles.
    parts = differing_parts(phrase, ctx.sentence_by_id("buildRequest", "wrong-quantity").text)
    if parts is None:
        raise ValueError("M06 needs the wrong-quantity phrase to differ from the order")
    answer_words = [chunk.text for chunk in derive_chunks(
        request, ctx.pack.language.word_separator).chunks]
    wrong_words = _new(_words(parts[1]), answer_words)
    if not wrong_words:
        raise ValueError("M06 needs a wrong-quantity tile that is not in the request")
    built = ctx.chunks(request, [*wrong_words, *_new([have], answer_words)], salt="q3")
    q3 = M06Question(
        question_id="m06-q3", purpose="buildRequest", prompt="Build a polite request for the item.",
        interaction_type="sentenceBuilding", correct_text=built["correct_text"],
        token_bank=built["token_bank"], correct_chunks=built["answer_chunks"],
        gap_kind="multiSlotRequest", assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
        target_id="build-request", evidence_type="construction",
        distractor_fields={**{word: "quantity" for word in wrong_words}, have: "request"},
    )

    # Q4: which detail the server asks about (English choices, as in dev).
    asked = {"serviceSetting": "Eat in or take away", "temperature": "Hot or cold",
             "size": "Which size", "colour": "Which colour"}[follow_type]
    given = ["How many", *(["Which size"] if size else [])]
    other_label = next(label for label in ("Which colour", "Hot or cold", "Eat in or take away",
                                           "Which size")
                       if label != asked and label not in given)
    q4_cards, options = _choices(ctx, [("correct", asked), ("given", given[0]),
                                       ("other", other_label)], "q4")
    q4 = M06Question(
        question_id="m06-q4", purpose="identifyMissingDetail",
        prompt="The server asks a question. What do they need to know?",
        interaction_type="multipleChoice", options=options, correct_option_id="correct",
        audio_text=question.text, listen_first=True, gap_kind="missingDetail",
        assistance_steps=["replayAudio", "visualDetail", "fullModel"],
        target_id="identify-missing-detail", evidence_type="recognition",
        distractor_fields={"given": "quantity", "other": "other detail"},
        option_fields={key: {"field": label} for key, label in q4_cards},
    )

    # Q5: reply with the detail, practised as dev's history decides.
    short = short_reply(reply.text)
    accepted_replies = list(dict.fromkeys([short, _unpunctuated(reply.text)]))
    dialogue = [{"speaker": "learner", "text": request.text},
                {"speaker": "server", "text": question.text}]
    reply_template = reply.text.replace(short, "___", 1)
    shared = dict(question_id="m06-q5", purpose="replyWithDetail",
                  prompt="Reply with the saved detail.", accepted_answers=accepted_replies,
                  dialogue=dialogue, assistance_steps=["phraseOnset", "chunkBank", "fullModel"],
                  target_id="reply-with-detail")
    if mode == "chunkChoice":
        _cards, options = _choices(ctx, [
            ("correct", reply.text),
            ("wrong-value", ctx.sentence_by_id("replyWithDetail", "wrong-value").text),
            ("wrong-detail", ctx.sentence_by_id("replyWithDetail", "other-detail").text),
        ], "q5")
        q5 = M06Question(
            **shared, interaction_type="multipleChoice", options=options,
            correct_option_id="correct", gap_kind="detailGap", evidence_type="recognition",
            distractor_fields={"wrong-value": follow_type, "wrong-detail": follow_type},
        )
    elif mode == "wordBank":
        answer = _phrase_chunks(ctx, reply)
        wrong = _new(_phrase_chunks(ctx, ctx.sentence_by_id("replyWithDetail", "wrong-value")),
                     answer)
        if not wrong:
            raise ValueError("M06 needs a wrong-value reply tile that is not in the reply")
        built = ctx.chunks(reply, wrong, phrase=True, salt="q5")
        q5 = M06Question(
            **shared, interaction_type="sentenceBuilding", correct_text=built["correct_text"],
            token_bank=built["token_bank"], correct_chunks=built["answer_chunks"],
            slot_template=reply_template, complete_chunk=reply.text, gap_kind="detailGap",
            evidence_type="construction", distractor_fields={chunk: follow_type for chunk in wrong},
        )
    else:
        q5 = M06Question(
            **shared, interaction_type="textCloze", correct_text=short,
            slot_template=reply_template, complete_chunk=reply.text, gap_kind="openCloze",
            evidence_type="construction",
        )

    # Q6: confirm an accurate repeat, or repair its one wrong detail.
    confirm = ctx.sentence_by_id("confirmOrRepair", "confirm")
    repair = ctx.sentence_by_id("confirmOrRepair", "repair")
    answer, other = (repair, confirm) if mismatch["flag"] else (confirm, repair)
    answer_chunks = _phrase_chunks(ctx, answer)
    other_chunks = _new(_phrase_chunks(ctx, other), answer_chunks)
    wrong_chunks = _new(_phrase_chunks(ctx, ctx.sentence_by_id("confirmOrRepair", "wrong-value")),
                        answer_chunks, other_chunks)
    if not wrong_chunks:
        raise ValueError("M06 needs a wrong-value tile that is not in the responses")
    built = ctx.chunks(answer, [*other_chunks, *wrong_chunks], phrase=True, salt="q6")
    full_dialogue = [*dialogue, {"speaker": "learner", "text": reply.text},
                     {"speaker": "server", "text": repeat.text}]
    wrong_field = mismatch["field"] or follow_type
    q6 = M06Question(
        question_id="m06-q6", purpose="confirmOrRepair",
        prompt="Listen to the server repeat your order. Confirm it or correct it.",
        interaction_type="sentenceBuilding", correct_text=built["correct_text"],
        token_bank=built["token_bank"], correct_chunks=built["answer_chunks"],
        repair_chunks=_phrase_chunks(ctx, repair), wrong_value_chunk=wrong_chunks[0],
        audio_text=repeat.text, gap_kind="dialogueResponse", dialogue=full_dialogue,
        assistance_steps=["replayAudio", "phraseOnset", "chunkBank", "fullModel"],
        target_id="confirm-or-repair", evidence_type="construction",
        distractor_fields={**{chunk: "confirmOrRepair" for chunk in other_chunks},
                           **{chunk: wrong_field for chunk in wrong_chunks}},
    )

    result = MissionM06Result(questions=[q1, q2, q3, q4, q5, q6])
    transaction.update(
        dialogue=full_dialogue,
        optionOrder={q.question_id: [o.option_id for o in q.options] for q in result.questions},
        answers={q.question_id: {"correct": q.correct_option_id or q.correct_text,
                                 "accepted": q.accepted_answers} for q in result.questions},
        distractorFields={q.question_id: q.distractor_fields for q in result.questions},
        gapKinds={q.question_id: q.gap_kind for q in result.questions},
    )
    prompt = SCENARIO_PROMPTS[scenario_of(item)]
    if scenario == "classroom":
        prompt = f"Imagine you need to borrow this {item.label}."
    payload = ctx.payload(
        sessionId=str(ctx.session_id), itemKey=item.key, itemLabel=item.label,
        sceneObjectId=transaction["sceneObjectId"], scenarioPrompt=prompt, alternatives=[],
        transaction=transaction, q5Mode=mode, expectedQ6Answer=answer.text,
        # Dev's Korean chunk rules describe its own tiles; pack tiles come from sentences.
        packLesson=True,
    )
    result = validate_m06_lesson(payload, result)
    tasks = build_m06_tasks(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    finished = [
        with_romanization(task, SimpleNamespace(questions=questions), ctx.pack, ctx.accepted,
                          ctx.vocabulary, ctx.extra_spellings)
        for task, questions in zip(
            tasks, (result.questions[:SECTIONS], result.questions[SECTIONS:]), strict=True,
        )
    ]
    return result, finished, payload


_BUILDERS = {"A2": _build_a2}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """The order's words come from the pack's ``requests.toml``."""
    if pack.requests is None:
        raise ValueError("M06 needs the pack's order words (requests.toml)")
    _order(facts)


def check_lesson(level, result, approved, pack):
    """Keep dev's six M06 purposes, IDs and answerable shapes."""
    questions = result.questions
    if [question.purpose for question in questions] != PURPOSES["A2"]:
        raise ValueError("assembled M06 questions do not preserve the mission sequence")
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError("assembled M06 question IDs must be unique")
    for question in questions:
        if question.interaction_type == "multipleChoice":
            labels = {fold(option.label) for option in question.options}
            if len(labels) != len(question.options):
                raise ValueError("assembled M06 choices must be distinct")
        elif question.interaction_type == "sentenceBuilding":
            if not set(question.correct_chunks) <= set(question.token_bank):
                raise ValueError("assembled M06 tiles must include the answer")
        elif not question.correct_text:
            raise ValueError("assembled M06 cloze needs an answer")


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=(),
                  mission_choices=None):
    """A food, drink or everyday object someone could ask for (dev's requestable items)."""
    return [] if requestable_objects(objects) else [REQUEST_REASON]


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    phrase_slots={"A2": frozenset({"replyWithDetail", "confirmOrRepair"})},
    photo_reasons=photo_reasons,
    vocabulary=request_vocabulary,
    facts=order_facts,
)
