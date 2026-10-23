"""M13 (choose the word that goes with the noun) as a pack lesson.

Each object's chunk is generated: the noun with the word it pairs with at A0 (la taza,
l'assiette, die Tasse, 책이에요). The words a noun can pair with are closed pack data
(``pairs.toml``); the generated chunk decides which one is right, and the others,
attached to the same noun, are the wrong choices, as in dev's reviewed lessons. The
lesson reuses dev's A0 questions, validator and task builder.
"""

from __future__ import annotations

import random

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0 import ORDERS, SLOT, fallback_a0_lesson
from app.services.mission_lessons_a0 import a0_lesson_task

from ..schema import pair_with
from .base import PackMission, for_level
from .common import (
    LessonContext,
    SpecBuilder,
    check_questions,
    differently_named,
    latin_of,
    usable_objects,
)

MISSION_ID = "M13"
PURPOSES = {"A0": ORDERS["M13"] * 2}
# Dev's A0 lessons use up to three objects: two focus objects and another marker.
MAX_OBJECTS = 3


# ---------------------------------------------------------------- planning


def plan_lesson(pack, level, facts, vocabulary, seed):
    specs = SpecBuilder()
    for_level(_PLANNERS, level, MISSION_ID)(specs, pack, facts, vocabulary, seed)
    return specs.build()


def _plan_a0(specs, pack, facts, vocabulary, _seed):
    # A marker question names an object, so the objects need different names.
    named = differently_named(usable_objects(facts, vocabulary), vocabulary)
    if len(named) < 2:
        raise ValueError("M13 A0 needs two differently named objects")
    # Every object's chunk is written once; both tasks reuse them.
    for index, obj in enumerate(named[:MAX_OBJECTS], 1):
        specs.add("chooseChunk-1", "name", "noun-word-pair", {"object": obj.fact_id},
                  suffix=f"object-{index}")
    for slot in ("matchSpoken-1", "fillSlot-1", "chooseChunk-2", "matchSpoken-2", "fillSlot-2"):
        specs.skip(slot)


_PLANNERS = {"A0": _plan_a0}


# ---------------------------------------------------------------- paired words


def split_pair(paired, text):
    """(paired word, noun) of a generated chunk: the pack word at the chunk's edge.

    ``la taza`` gives (la, taza), ``l'assiette`` (l', assiette), ``책이에요`` (이에요, 책).
    """
    for word in sorted(paired.words, key=lambda item: len(item.text), reverse=True):
        if word.position == "after":
            if text.endswith(word.text) and len(text) > len(word.text):
                return word, text[: -len(word.text)].strip()
            continue
        prefix = pair_with(word.text, "", "before")
        if text.casefold().startswith(prefix.casefold()) and len(text) > len(prefix):
            return word, text[len(prefix):]
    raise ValueError(f"M13 chunk {text!r} does not use one of the pack's paired words")


def form_choices(paired, word, plurals_taught):
    """The right word first, then up to two others that differ from it only in the word.

    Elided words (l') contrast only with an elided noun; plural words appear only once
    plurals were taught, as in dev's lessons.
    """
    others = [
        item for item in paired.words
        if item.text != word.text
        and (plurals_taught or not item.plural)
        and (word.elided or not item.elided)
    ]
    return [word, *others][:3]


# ---------------------------------------------------------------- assembly


def build_lesson(level, pack, facts, vocabulary, plan, accepted, *, builder_selection=None,
                 session_id=None):
    ctx = LessonContext(MISSION_ID, level, pack, facts, vocabulary, plan, accepted,
                        builder_selection=builder_selection, session_id=session_id)
    result, task, payload = for_level(_BUILDERS, level, MISSION_ID)(ctx)
    return result, ctx.finish(task, result), payload


def _build_a0(ctx):
    paired = ctx.pack.paired_words
    plurals_taught = bool((ctx.selection.get("progress") or {}).get("plurals_taught"))
    translations, rows = {}, []
    for spec in ctx.specs("chooseChunk-1"):
        sentence = ctx.sentence_for("chooseChunk-1", spec)
        word, noun = split_pair(paired, sentence.text)
        row = dict(ctx.by_fact[spec.bindings["object"]])
        choices = form_choices(paired, word, plurals_taught)
        chunks = [sentence.text, *(item.join(noun) for item in choices[1:])]
        row.update(
            label=row["source"].capitalize(), chunk=sentence.text, form=word.text,
            slotTemplate=pair_with(SLOT, noun, word.position), batchim=word.final == "consonant",
            formChoices=[dict(form=item.text, chunk=chunk, plural=item.plural)
                         for item, chunk in zip(choices, chunks, strict=True)],
            formNote=(
                f"{noun} ends in a {word.final}, so it takes {word.text}: {sentence.text}."
                if word.final else f"{noun} goes with {word.text}: {sentence.text}."
            ),
        )
        translations[sentence.text] = sentence.translation
        translations[row["slotTemplate"]] = sentence.translation
        _spell(ctx, row, sentence, noun, choices)
        rows.append(row)
    payload = ctx.payload(
        title=ctx.mission.title, focus=_focus(ctx, rows), approvedObjects=rows,
        approvedTranslations=translations, pluralsTaught=plurals_taught, yesNo=[],
        whatIsThis=None, group=None, approvedNumberWords={}, quantityChunks={}, howMany=None,
        approvedArticlesOrEndings=sorted({item["form"] for row in rows
                                          for item in row["formChoices"]}),
        approvedSentenceChunks=list(dict.fromkeys([
            *translations, *(item["chunk"] for row in rows for item in row["formChoices"]),
        ])),
        explanation=paired.explanation,
    )
    result = fallback_a0_lesson(payload)
    task = a0_lesson_task(ctx.session_id, ctx.mission, payload, result, ctx.vocabulary_ids)
    return result, task, payload


def _focus(ctx, rows):
    """Two focus objects, preferring two that take different words (as dev chooses)."""
    ordered = list(rows)
    random.Random(f"{ctx.seed}:focus").shuffle(ordered)
    first = ordered[0]
    second = next((row for row in ordered[1:] if row["form"] != first["form"]), ordered[1])
    return [first["key"], second["key"]]


def _spell(ctx, row, sentence, noun, choices):
    """Latin spellings for the paired words and the chunks built from them."""
    if not ctx.pack.language.romanization_required:
        return
    noun_latin = ctx.terms[row["fact_id"]].romanization
    for item in choices:
        if item.romanization:
            ctx.extra_spellings[item.text] = item.romanization
        if noun_latin and item.romanization:
            ctx.extra_spellings.setdefault(
                item.join(noun), pair_with(item.romanization, noun_latin, item.position),
            )
    if sentence.romanization:
        ctx.extra_spellings[sentence.text] = latin_of(sentence)
    if noun_latin:
        ctx.extra_spellings[row["slotTemplate"]] = pair_with(
            SLOT, noun_latin, choices[0].position,
        )


_BUILDERS = {"A0": _build_a0}


# ---------------------------------------------------------------- checks


def check_inputs(level, pack, facts, vocabulary, plan):
    """The choices come from the pack's paired words (pairs.toml)."""
    if pack.paired_words is None:
        raise ValueError("M13 needs the pack's paired words (pairs.toml)")


def check_lesson(level, result, approved, pack):
    """Keep dev's two tasks of three questions; the right chunk is the generated one."""
    check_questions(result.questions, PURPOSES[level], MISSION_ID)
    generated = {fold(item.candidate.text) for item in approved}
    for question in result.questions:
        if question.purpose == "chooseChunk":
            label = next(option.label for option in question.options
                         if option.option_id == question.correct_option_id)
            if fold(label) not in generated:
                raise ValueError("the M13 chunk answer must be a generated, validated chunk")


MISSION = PackMission(
    mission_id=MISSION_ID,
    plan=plan_lesson,
    build=build_lesson,
    check_inputs=check_inputs,
    check_lesson=check_lesson,
)
