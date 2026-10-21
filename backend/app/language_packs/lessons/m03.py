"""M03 (count objects) as a pack lesson.

Number words are reviewed pack data (``numbers.toml``) added to the lesson's
vocabulary; the sentences that use them are generated. Questions reuse dev's M03
models and task builders (`a0_lesson_task`, `m03_a2_task`); A1 builds its task here
because dev's A1 corrections are written per language.
"""

from __future__ import annotations

import random

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_a0 import (
    A0LessonResult,
    validate_a0_lesson,
)
from app.ai.features.learning_tasks.mission_a0 import (
    _m03 as a0_m03_questions,
)
from app.ai.features.learning_tasks.mission_a2 import MissionA2Question, MissionA2Result
from app.ai.features.learning_tasks.mission_m03 import (
    SECTION_BOARD,
    SECTION_PHOTO,
    M03LessonResult,
    _nearby,
)
from app.missions import get_mission
from app.services.mission_lessons import build_mission_task
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import m03_a2_task
from app.services.mission_lessons_m03 import _EVALUATIONS as A1_EVALUATIONS
from app.services.mission_lessons_m03 import M03_FOCUS
from app.services.quantities import ENGLISH_NUMBERS

from ..generation import ApprovedTerm, ApprovedVocabulary
from .base import PackMission, for_level
from .common import LessonContext, SpecBuilder, check_questions, latin_of

MISSION_ID = "M03"
PURPOSES = {
    "A0": ["countGroup", "matchChunk", "buildChunk"] * 2,
    "A1": ["chooseQuantity", "buildQuantity", "matchQuantity"],
    "A2": [
        "countGroup", "buildQuantity", "compareGroups", "correctRoleplayCount",
        "buildComparison",
    ],
}
# A0 teaches one to three: the photo group (two or three) and the board's other number.
A0_NUMBERS = (1, 2, 3)
A2_SECTIONS = (
    "Task 1 · Count the groups", "Task 2 · Compare the quantities", "Task 3 · Correct the count",
)
_BOARD_LETTERS = "abc"


# ---------------------------------------------------------------- vocabulary


def number_vocabulary(pack, facts, vocabulary):
    """The pack's number words, plus one term per learner count in its noun's form.

    ``number-N`` terms are the alternatives a lesson may name (practice boards, the
    friend's wrong count); a ``count-K`` term is the confirmed count itself, written
    the way it goes with the counted noun (una manzana, 두 개).
    """
    if pack.numbers is None:
        return vocabulary
    terms = list(vocabulary.terms)
    for number in pack.numbers.numbers:
        forms = {"default": number.text}
        forms.update({f"with-noun-{form.agreement or 'any'}": form.text
                      for form in number.with_noun})
        terms.append(ApprovedTerm(
            term_id=f"number-{number.value}", fact_id=f"number:{number.value}",
            source_text=ENGLISH_NUMBERS[number.value], target_text=number.text,
            forms=number.texts, forms_by_key=forms, part_of_speech="determiner",
            provenance="packData", romanization=number.romanization,
            linguistic={"quantity": str(number.value)},
        ))
    nouns = {term.fact_id: term for term in vocabulary.terms}
    for count in facts.scene_facts.counted_groups:
        noun = _group_noun(count, nouns)
        number = pack.numbers.get(count.quantity)
        if noun is None or number is None:
            continue
        form = number.form_for(noun.agreement)
        terms.append(ApprovedTerm(
            term_id=count.fact_id.replace(":", "-"), fact_id=count.fact_id,
            source_text=ENGLISH_NUMBERS[count.quantity], target_text=form.text,
            forms=list(dict.fromkeys([form.text, number.text])),
            forms_by_key={"default": number.text, "with-noun": form.text},
            part_of_speech="determiner", provenance="packData",
            romanization=form.romanization, linguistic={"quantity": str(count.quantity)},
        ))
    return ApprovedVocabulary(terms=terms)


def _group_noun(count, nouns):
    """The counted objects' noun term (members share a label)."""
    return next((nouns[fid] for fid in count.object_fact_ids if fid in nouns), None)


def _counted(facts, vocabulary, numbers):
    """(count fact, noun term) for every count the lesson can teach."""
    nouns = {term.fact_id: term for term in vocabulary.terms if term.part_of_speech == "noun"}
    found = []
    for count in facts.scene_facts.counted_groups:
        noun = _group_noun(count, nouns)
        if noun is not None and count.quantity in numbers:
            found.append((count, noun))
    return found


def _taught(pack, level):
    """Numbers practice may use: the mission's quantity range, as far as the pack spells it."""
    if level == "A0":
        low, high = A0_NUMBERS[0], A0_NUMBERS[-1]
    else:
        requirements = get_mission(MISSION_ID, level, 1).photo_requirements
        low, high = requirements.min_quantity, requirements.max_quantity
    spelled = pack.numbers.values if pack.numbers else set()
    return [number for number in range(low, high + 1) if number in spelled]


def _a2_selection(groups, seed):
    """Two counts of different objects and quantities, chosen as dev's A2 lesson does."""
    pairs = [
        (left, right)
        for index, left in enumerate(groups)
        for right in groups[index + 1:]
        if fold(left[1].source_text) != fold(right[1].source_text)
        and left[0].quantity != right[0].quantity
    ]
    if not pairs:
        return None
    return random.Random(f"{seed}:M03-A2").choice(pairs)


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed):
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, pack, facts, vocabulary, seed)
    return specs.build()


def _plan_a0(specs, pack, facts, vocabulary, _seed):
    groups = _counted(facts, vocabulary, {2, 3})
    if not groups:
        raise ValueError("M03 A0 needs a counted group of 2 or 3 objects")
    # As in dev, the first group is counted; more groups never block the lesson.
    count, noun = groups[0]
    specs.add("countGroup-1", "question", "how-many-question", {"object": noun.fact_id})
    for number in A0_NUMBERS:
        if number == count.quantity:
            specs.add("matchChunk-1", "option", "quantity-chunk",
                      {"object": noun.fact_id, "count": count.fact_id}, suffix=f"n{number}")
        else:
            specs.add("matchChunk-1", "option", "quantity-chunk", {"object": noun.fact_id},
                      truth=False, counterfactual={"count": f"number-{number}"},
                      suffix=f"n{number}")
    # Both tasks reuse the question and the three chunks.
    for slot in ("buildChunk-1", "countGroup-2", "matchChunk-2", "buildChunk-2"):
        specs.skip(slot)


def _plan_a1(specs, pack, facts, vocabulary, seed):
    taught = _taught(pack, "A1")
    groups = _counted(facts, vocabulary, set(taught))
    if not groups or len(taught) < 2:
        raise ValueError("M03 A1 needs a counted group within the taught number range")
    count, noun = groups[0]
    target = _board_target(count.quantity, taught, seed)
    specs.add("chooseQuantity", "question", "how-many-question", {"object": noun.fact_id})
    specs.add("buildQuantity", "answer", "quantity-statement",
              {"object": noun.fact_id, "count": count.fact_id})
    # The practice board is fictional: a statement with another taught number.
    specs.add("matchQuantity", "board", "quantity-statement", {"object": noun.fact_id},
              truth=False, counterfactual={"count": f"number-{target}"})


def _board_target(quantity, taught, seed):
    """The board's number: a larger taught number when there is one (as dev chooses)."""
    rng = random.Random(f"{seed}:M03-board")
    greater = [number for number in taught if number > quantity]
    others = [number for number in taught if number != quantity]
    return rng.choice(greater or others)


def _plan_a2(specs, pack, facts, vocabulary, seed):
    taught = _taught(pack, "A2")
    selection = _a2_selection(_counted(facts, vocabulary, set(taught)), seed)
    if selection is None:
        raise ValueError("M03 A2 needs two counted groups of different objects and quantities")
    (first, first_noun), (second, second_noun) = selection
    false_count, alternative = _a2_wrong_counts(first, second, taught, seed)
    more = first.quantity > second.quantity
    comparative, reverse = ("more", "fewer") if more else ("fewer", "more")
    pair = {"first": first_noun.fact_id, "second": second_noun.fact_id}
    specs.add("countGroup", "question", "how-many-question", {"object": first_noun.fact_id})
    specs.add("buildQuantity", "answer", "quantity-statement",
              {"object": second_noun.fact_id, "count": second.fact_id})
    specs.add("compareGroups", "answer", "quantity-comparison", pair, labels=[comparative],
              suffix="correct")
    specs.add("compareGroups", "option", "quantity-comparison", pair, labels=[reverse],
              truth=False, suffix="reverse")
    specs.add("compareGroups", "option", "quantity-comparison",
              {"first": second_noun.fact_id, "second": first_noun.fact_id},
              labels=[comparative], truth=False, suffix="swapped")
    statement = {"object": first_noun.fact_id}
    specs.add("correctRoleplayCount", "roleplay", "quantity-statement", statement,
              truth=False, counterfactual={"count": f"number-{false_count}"}, suffix="friend")
    specs.add("correctRoleplayCount", "correction", "quantity-statement",
              {**statement, "count": first.fact_id}, labels=["no"], suffix="correct")
    specs.add("correctRoleplayCount", "option", "quantity-statement", statement,
              truth=False, counterfactual={"count": f"number-{alternative}"}, suffix="wrong")
    specs.add("buildComparison", "answer", "quantity-pair", {
        **pair, "first-count": first.fact_id, "second-count": second.fact_id,
    })


def _a2_wrong_counts(first, second, taught, seed):
    """The friend's fictional count and one more wrong count, never a confirmed one."""
    confirmed = {first.quantity, second.quantity}
    wrong = [number for number in taught if number not in confirmed]
    if len(wrong) < 2:
        raise ValueError("M03 A2 needs two taught numbers that no group has")
    false_count = random.Random(f"{seed}:M03-A2-roleplay").choice(wrong)
    alternative = next(number for number in wrong if number != false_count)
    return false_count, alternative


_PLANNERS = {"A0": _plan_a0, "A1": _plan_a1, "A2": _plan_a2}


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    _spell_numbers(ctx)
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _spell_numbers(ctx):
    """Number words appear as options and tiles; record their spellings."""
    if ctx.pack.numbers is None:
        return
    for number in ctx.pack.numbers.numbers:
        for item in (number, *number.with_noun):
            if not item.romanization:
                continue
            ctx.extra_spellings[item.text] = item.romanization
            native, latin = item.text.split(), item.romanization.split()
            if len(native) == len(latin):
                ctx.extra_spellings.update(zip(native, latin, strict=True))


def _number_word(ctx, value, noun):
    """How the number is written with this noun (the option a learner picks)."""
    return ctx.pack.numbers.get(value).form_for(noun["gender"]).text


def _group(ctx, count_fact_id):
    """The count fact, its noun row and the counted objects' scene IDs."""
    count = next(item for item in ctx.facts.scene_facts.counted_groups
                 if item.fact_id == count_fact_id)
    objects = {obj.fact_id: obj for obj in ctx.facts.scene_facts.objects}
    row = next(ctx.by_fact[fid] for fid in count.object_fact_ids if fid in ctx.by_fact)
    object_ids = [str(objects[fid].scene_object_id) for fid in count.object_fact_ids]
    return count, row, object_ids


def _counterfactual_number(ctx, spec):
    return int(ctx.terms_by_id[spec.counterfactual["count"]].linguistic["quantity"])


def _build_a0(ctx):
    counted = next(
        spec.bindings["count"] for spec in ctx.specs("matchChunk-1") if "count" in spec.bindings
    )
    count, row, object_ids = _group(ctx, counted)
    how_many = ctx.sentence("countGroup-1", "question")
    words, chunks, translations = {}, {}, {how_many.text: how_many.translation}
    for number in A0_NUMBERS:
        chunk = ctx.sentence_by_id("matchChunk-1", f"n{number}")
        words[str(number)] = _number_word(ctx, number, row)
        chunks[str(number)] = chunk.text
        translations[words[str(number)]] = ENGLISH_NUMBERS[number]
        translations[chunk.text] = chunk.translation
    payload = ctx.payload(
        title=ctx.mission.title,
        yesNo=[ctx.label("yes-answer"), ctx.label("no-answer")],
        group=dict(key=row["key"], objectIds=object_ids, boardObjectId=row["key"],
                   quantity=count.quantity, confirmedQuantity=count.quantity),
        focus=[], howMany=how_many.text, approvedNumberWords=words, quantityChunks=chunks,
        approvedObjects=[row], approvedTranslations=translations,
        approvedSentenceChunks=[how_many.text, *chunks.values()],
        approvedArticlesOrEndings=[], pluralsTaught=True,
    )
    result = A0LessonResult(title=ctx.mission.title, questions=a0_m03_questions(payload))
    validate_a0_lesson(payload, result)
    task = a0_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _build_a1(ctx):
    build_spec = ctx.spec("buildQuantity")
    count, row, object_ids = _group(ctx, build_spec.bindings["count"])
    taught = _taught(ctx.pack, "A1")
    question = ctx.sentence("chooseQuantity", "question")
    statement = ctx.sentence("buildQuantity", "answer")
    board = ctx.sentence("matchQuantity", "board")
    target = _counterfactual_number(ctx, ctx.spec("matchQuantity"))
    rng = random.Random(f"{ctx.seed}:M03")
    word = {number: _number_word(ctx, number, row) for number in taught}

    distractors = _nearby(count.quantity, taught, skip_first=True)
    choices = [count.quantity, *distractors[:2]]
    rng.shuffle(choices)
    choose_options = [dict(option_id=f"number-{_BOARD_LETTERS[i]}", label=word[number])
                      for i, number in enumerate(choices)]

    statement_tokens = {fold(token) for token in tokens(statement.text)}
    extras = [row["noun"]] if fold(row["noun"]) not in statement_tokens else []
    wrong_number = next((token for token in tokens(word[distractors[0]])
                         if fold(token) not in statement_tokens), None)
    extras += [wrong_number] if wrong_number else []
    build = ctx.chunks(statement, extras, salt="build-quantity")

    counts = [target, *_nearby(target, taught)[:2]]
    rng.shuffle(counts)
    board_options = [dict(option_id=f"board-{_BOARD_LETTERS[i]}",
                          label=f"Board {_BOARD_LETTERS[i].upper()}")
                     for i in range(len(counts))]
    common = dict(object_key=row["key"], quantity_word=None, board_counts=None,
                  board_object_id=None)
    questions = [
        dict(question_id="choose-quantity", purpose="chooseQuantity", prompt=question.text,
             interaction_type="multipleChoice", options=choose_options,
             correct_option_id=choose_options[choices.index(count.quantity)]["option_id"],
             correct_text=None, token_bank=[], translation=None, section=SECTION_PHOTO,
             group_object_ids=object_ids, **common),
        dict(question_id="build-quantity", purpose="buildQuantity",
             prompt=f"{question.text} {ctx.label('answer-in-sentence')}",
             interaction_type="sentenceBuilding", options=[], correct_option_id=None,
             correct_text=statement.text, token_bank=build["token_bank"], translation=None,
             section=SECTION_PHOTO, group_object_ids=object_ids, **common),
        dict(question_id="match-quantity", purpose="matchQuantity", prompt=board.text,
             interaction_type="multipleChoice", options=board_options,
             correct_option_id=board_options[counts.index(target)]["option_id"],
             correct_text=None, token_bank=[], translation=None, section=SECTION_BOARD,
             group_object_ids=[], object_key=row["key"], quantity_word=word[target],
             board_counts={option["option_id"]: number
                           for option, number in zip(board_options, counts, strict=True)},
             board_object_id=row["key"]),
    ]
    if question.romanization:
        ctx.extra_spellings[questions[1]["prompt"]] = (
            f"{latin_of(question)} {ctx.labels['answer-in-sentence'].romanization}"
        )
    group = dict(key=f"{row['key']}:count", objectKey=row["key"], objectIds=object_ids,
                 boardObjectId=row["key"], source=row["source"], quantity=count.quantity,
                 numberWord=word[count.quantity], singular=row["noun"],
                 statement=statement.text, question=question.text)
    payload = ctx.payload(
        numberRange={"low": taught[0], "high": taught[-1], "source": "missionDefault"},
        group=group,
    )
    result = M03LessonResult(title="Say how many", questions=questions)
    task = _a1_task(ctx, result, group, word, question, statement, extras)
    return result, task, payload


def _a1_task(ctx, result, group, word, question, statement, extras):
    """dev's M03 A1 task with corrections from the generated sentences."""
    meaning = {fold(text): number for number, text in word.items()}
    translations = {
        "chooseQuantity": question.translation,
        "buildQuantity": f"{question.translation} {ctx.labels['answer-in-sentence'].meaning}",
        "matchQuantity": None,
    }
    correct_note = f"You counted {group['quantity']}: {group['numberWord']}."

    def corrections(item, label):
        if item.purpose == "buildQuantity":
            found = [
                dict(mistake="wordOrder", correction=statement.text,
                     explanation=f"Build: {statement.text}"),
                dict(mistake="wrongQuantity", correction=statement.text,
                     explanation=correct_note),
            ]
            if group["singular"] in extras:
                found.insert(0, dict(
                    mistake="pluralForm", correction=statement.text,
                    explanation=f"After {group['numberWord']}, use the counted noun's plural.",
                ))
            return found, None
        if item.purpose == "matchQuantity":
            target = (item.board_counts or {}).get(item.correct_option_id)
            note = f"“{item.quantity_word}” means {target}."
            return [dict(mistake="wrongQuantity", answers=[option.option_id], correction=label,
                         explanation=note)
                    for option in item.options if option.option_id != item.correct_option_id
                    ], note
        return [
            dict(mistake="wrongQuantity", answers=[option.option_id], correction=label,
                 note=f"“{option.label}” means {meaning[fold(option.label)]}.",
                 explanation=f"“{option.label}” means {meaning[fold(option.label)]}; "
                             f"{correct_note[0].lower()}{correct_note[1:]}")
            for option in item.options if option.option_id != item.correct_option_id
        ], correct_note

    def evaluate(item, label):
        target_ids, evidence_type, criteria = A1_EVALUATIONS[item.purpose]
        vocabulary_id = ctx.vocabulary_ids.get(item.object_key)
        found, note = corrections(item, label)
        return dict(
            target_ids=target_ids, evidence_type=evidence_type, rubric_criterion_ids=criteria,
            vocabulary_item_ids=(
                [vocabulary_id] if vocabulary_id and item.purpose == "buildQuantity" else []
            ),
            corrections=found, correct_note=note,
        )

    def shown(item):
        fields = dict(section=item.section, prompt_translation=translations[item.purpose])
        if item.section == SECTION_PHOTO:
            fields.update(scene_object_id=item.object_key, object_label=group["source"],
                          group_object_ids=item.group_object_ids)
        else:
            fields.update(board_counts=item.board_counts, board_object_id=item.board_object_id,
                          quantity_word=item.quantity_word)
        return fields

    return build_mission_task(ctx.session_id, ctx.mission, M03_FOCUS, result, evaluate, shown)


def _build_a2(ctx):
    pair_spec = ctx.spec("buildComparison")
    first, first_row, first_ids = _group(ctx, pair_spec.bindings["first-count"])
    second, second_row, second_ids = _group(ctx, pair_spec.bindings["second-count"])
    taught = _taught(ctx.pack, "A2")
    count_question = ctx.sentence("countGroup", "question")
    second_statement = ctx.sentence("buildQuantity", "answer")
    compare = {suffix: ctx.sentence_by_id("compareGroups", suffix)
               for suffix in ("correct", "reverse", "swapped")}
    friend = ctx.sentence_by_id("correctRoleplayCount", "friend")
    correction = ctx.sentence_by_id("correctRoleplayCount", "correct")
    wrong = ctx.sentence_by_id("correctRoleplayCount", "wrong")
    pair = ctx.sentence("buildComparison", "answer")
    false_count = _counterfactual_number(ctx, next(
        spec for spec in ctx.specs("correctRoleplayCount") if spec.use == "roleplay"
    ))
    s1, s2, s3 = A2_SECTIONS
    both = list(dict.fromkeys(first_ids + second_ids))
    word = {number: _number_word(ctx, number, first_row) for number in taught}
    numbers = [first.quantity, *(n for n in taught if n not in {first.quantity, false_count})][:3]
    second_tokens = {fold(token) for token in tokens(second_statement.text)}
    number_extra = [token for token in tokens(_number_word(ctx, first.quantity, second_row))
                    if fold(token) not in second_tokens][:1]
    friend_prompt = ctx.label("friend-says", statement=friend.text)
    if friend.romanization:
        ctx.extra_spellings[friend_prompt] = ctx.labels["friend-says"].romanization.replace(
            "{statement}", latin_of(friend))
    combined = _joined(ctx, pair, compare["correct"])

    def choice(qid, purpose, prompt, options, correct_id, section, key, **fields):
        rows = ctx.shuffle([dict(option_id=option_id, label=text) for option_id, text in options],
                           qid)
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="multipleChoice",
            options=rows, correct_option_id=correct_id, object_key=key, section=section,
            target_language_text=[prompt], **fields,
        )

    def building(qid, purpose, prompt, candidate, extras, section, key, group_ids, *,
                 phrase=False):
        tiles = ctx.chunks(candidate, extras, phrase=phrase, salt=qid)
        return MissionA2Question(
            question_id=qid, purpose=purpose, prompt=prompt, interaction_type="sentenceBuilding",
            correct_text=tiles["correct_text"], token_bank=tiles["token_bank"],
            answer_chunks=tiles["answer_chunks"], distractor_chunks=tiles["distractor_chunks"],
            translation=candidate.translation, object_key=key, section=section,
            group_object_ids=group_ids, target_language_text=[prompt],
        )

    questions = [
        choice("m03-q1", "countGroup", count_question.text,
               [(f"number-{i}", word[n]) for i, n in enumerate(numbers)], "number-0", s1,
               first_row["key"], group_object_ids=first_ids),
        building("m03-q2", "buildQuantity", ctx.label("build-group-sentence"),
                 second_statement, number_extra, s1, second_row["key"], second_ids),
        choice("m03-q3", "compareGroups", ctx.label("choose-comparison"),
               [(f"comparison-{suffix}", sentence.text) for suffix, sentence in compare.items()],
               "comparison-correct", s2, first_row["key"], group_object_ids=both,
               roleplay_premise=(f"Group {first_row['marker']} has {first.quantity}; "
                                 f"group {second_row['marker']} has {second.quantity}.")),
        choice("m03-q4", "correctRoleplayCount", friend_prompt,
               [("count-correct", correction.text),
                ("count-repeat", ctx.label("friend-is-right")),
                ("count-wrong", wrong.text)],
               "count-correct", s3, first_row["key"], group_object_ids=first_ids,
               roleplay_premise=f"Role-play: a friend says «{friend.text}»."),
        building("m03-q5", "buildComparison", ctx.label("describe-compare"), combined,
                 [compare["reverse"].text], s3, first_row["key"], both, phrase=True),
    ]
    questions[3].target_language_text.append(friend.text)
    payload = ctx.payload(
        approvedFacts=dict(approvedObjects=ctx.rows,
                           sceneFacts=ctx.facts.model_dump(mode="json"),
                           approvedVocabulary=ctx.vocabulary.model_dump(mode="json")),
        selection=dict(firstGroupKey=first.fact_id, secondGroupKey=second.fact_id),
        quantityRange={"min": taught[0], "max": taught[-1]},
    )
    result = MissionA2Result(title="Describe and compare quantities", questions=questions)
    task = m03_a2_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


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
    """Counting needs the pack's number words for the level's range."""
    if pack.numbers is None:
        raise ValueError("M03 needs the pack's number words (numbers.toml)")


def check_lesson(level, result, approved, pack):
    """Keep dev's M03 question count, order, interactions and answer contract."""
    check_questions(result.questions, PURPOSES[level], MISSION_ID)


def photo_reasons(mission, objects, relations, attributes_of, counted_groups=()):
    """A0 counts the first small group; A2 compares two groups of different objects."""
    level = str(mission.practice_level)
    requirements = mission.photo_requirements
    labels = {str(obj.id): fold(obj.label) for obj in objects}
    groups = [
        group for group in counted_groups
        if requirements.min_quantity <= group["quantity"] <= requirements.max_quantity
    ]
    if level == "A0" and not groups:
        return ["Count a group of 2 or 3 matching objects."]
    if level == "A2":
        def label(group):
            return next((labels[str(item)] for item in group["sceneObjectIds"]
                         if str(item) in labels), None)

        if not any(
            label(left) != label(right) and left["quantity"] != right["quantity"]
            for index, left in enumerate(groups) for right in groups[index + 1:]
        ):
            return [
                "Confirm two differently named groups with different quantities from "
                f"{requirements.min_quantity} to {requirements.max_quantity}."
            ]
    return []


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
    photo_reasons=photo_reasons,
    vocabulary=number_vocabulary,
)
