"""A0 situation lessons (M04, M05): question helpers and the lesson task."""

from __future__ import annotations

import random
import unicodedata
from uuid import UUID, uuid5

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0_situations import SituationQuestion
from app.schemas.missions import A0MissionSnapshot, TaughtChunk
from app.schemas.tasks import SessionTask
from app.services.lesson_tasks.common import mission_version


def seeded_rng(payload, salt):
    return random.Random(f"{payload['seed']}:{salt}")


def prep_add(prep, text, translation):
    if text not in {item["text"] for item in prep}:
        prep.append({"text": text, "translation": translation})


def object_reference(row):
    """Name one photo instance even when several objects share the same noun."""
    return f"{row['source']} at marker {row['marker']}"


def choice_question(
    question_id, prompt, instruction, section, object_key, options, correct_label,
    target_group, payload, *, salt, gap_type=None, **extra,
):
    options = list(options)
    seeded_rng(payload, salt).shuffle(options)
    choices = [
        {"option_id": f"option-{index}", "label": label}
        for index, label in enumerate(options, 1)
    ]
    correct = next(
        choice["option_id"] for choice in choices if fold(choice["label"]) == fold(correct_label)
    )
    return SituationQuestion(
        question_id=question_id,
        prompt=prompt,
        instruction=instruction,
        section=section,
        gap_type=gap_type,
        options=choices,
        correct_option_id=correct,
        object_key=object_key,
        target_group=target_group,
        **extra,
    )


def marker_question(payload, rows, focus, section, instruction, target_group):
    shown = sorted(rows, key=lambda row: row["marker"])[:3]
    if focus["key"] not in {row["key"] for row in shown}:
        shown = [*shown[:2], focus]
        shown.sort(key=lambda row: row["marker"])
    options = [
        {"option_id": f"marker-{row['marker']}", "label": str(row["marker"])}
        for row in shown
    ]
    return SituationQuestion(
        question_id=f"{payload['missionId']}-Q1",
        prompt=instruction,
        instruction=instruction,
        section=section,
        options=options,
        correct_option_id=f"marker-{focus['marker']}",
        object_key=focus["key"],
        marker_keys={f"marker-{row['marker']}": row["key"] for row in shown},
        target_group=target_group,
    )


def target_texts(prep, questions):
    texts = [item["text"] for item in prep]
    for question in questions:
        texts.extend(
            text for text in (
                question.audio_text, question.slot_template, question.complete_chunk,
                *(option.label for option in question.options),
                *(turn["text"] for turn in question.dialogue or []),
            ) if text
        )
    return list(dict.fromkeys(texts))


def lower_first(value):
    return value[:1].lower() + value[1:]


def _normalized_equivalents(value, language):
    values = {value}
    if language in {"es", "fr"}:
        values.add(value.replace("’", "'"))
        values.add(value.replace("'", "’"))
    if language == "es":
        normalized = unicodedata.normalize("NFD", value)
        values.add("".join(char for char in normalized if unicodedata.category(char) != "Mn"))
    if language == "de":
        values.add(value.replace("ö", "oe").replace("Ö", "Oe"))
    return sorted(values)


def situation_lesson_task(session_id, mission, prepared, result, vocabulary_ids):
    """The public situation lesson from prepared content (approved objects, learner facts
    and preparation cards), as the pack's M04 or M05 lesson prepares it."""
    answers = {}
    accepted = {}
    evaluations = []
    public_questions = []
    for question in result.questions:
        answers[question.question_id] = question.correct_option_id
        if question.accepted_text_answers:
            accepted[question.question_id] = list(dict.fromkeys(
                answer
                for candidate in question.accepted_text_answers
                for answer in _normalized_equivalents(candidate, prepared["targetLanguage"])
            ))
        object_id = UUID(question.object_key)
        evaluation = dict(
            question_id=question.question_id,
            objective_id=mission.objective.objective_id,
            target_ids=[question.target_group],
            evidence_type="recognition",
            vocabulary_item_ids=[vocabulary_ids[str(object_id)]]
            if str(object_id) in vocabulary_ids else [],
            scene_object_id=object_id,
        )
        evaluations.append(evaluation)
        option_objects = {
            option_id: UUID(key) for option_id, key in (question.option_object_keys or {}).items()
        }
        marker_objects = {
            option_id: UUID(key) for option_id, key in (question.marker_keys or {}).items()
        }
        public_questions.append(dict(
            question_id=question.question_id,
            prompt=question.prompt,
            interaction_type="multipleChoice",
            options=[option.model_dump(mode="json", by_alias=True) for option in question.options],
            section=question.section,
            instruction=question.instruction,
            audio_text=question.audio_text,
            listen_first=question.listen_first,
            slot_template=question.slot_template,
            complete_chunk=question.complete_chunk,
            gap_type=question.gap_type,
            dialogue=question.dialogue,
            option_object_ids=option_objects or None,
            option_icons=question.option_icons,
            complete_translation=question.complete_translation,
            outcome=question.outcome,
            correct_note=question.correct_note,
            typed_allowed=question.typed_allowed,
            roleplay_premise=question.roleplay_premise,
            marker_object_ids=marker_objects or None,
            scene_object_id=object_id,
            object_label=next(
                row["label"] for row in prepared["approvedObjects"]
                if row["key"] == question.object_key
            ),
        ))
    facts = prepared["learnerFacts"]
    if mission.mission_id == "M04":
        snapshot = A0MissionSnapshot(
            mission_id="M04",
            situation="lostAndFound",
            taught_chunks=[TaughtChunk(**item) for item in prepared["prep"]],
            owned_object_id=UUID(facts["ownedObjectId"]),
            pretend=bool(facts.get("pretend", False)),
        )
    else:
        preference = facts["preference"]
        compared = [UUID(item) for item in preference["sceneObjectIds"]]
        snapshot = A0MissionSnapshot(
            mission_id="M05",
            situation="everydayChoice",
            taught_chunks=[TaughtChunk(**item) for item in prepared["prep"]],
            preference_object_ids=compared,
            chosen_object_id=(
                UUID(preference["chosenObjectId"])
                if preference.get("chosenObjectId") else None
            ),
            reaction=preference["reaction"],
            pretend=bool(preference.get("pretend", False)),
        )
    return SessionTask(
        id=uuid5(session_id, f"mission:{mission_version(mission)}:lesson"),
        session_id=session_id,
        phase="learning",
        kind="grammarLesson",
        order_index=0,
        public_content=dict(
            kind="grammarLesson",
            focus="ownership" if mission.mission_id == "M04" else "preference",
            title=result.title,
            explanation=None,
            prep=prepared["prep"],
            questions=public_questions,
            check_each_question=True,
            situation="lostAndFound" if mission.mission_id == "M04" else "everydayChoice",
            taught_chunks=prepared["prep"],
            mission_snapshot=snapshot.model_dump(mode="json", by_alias=True),
            mission_id=mission.mission_id,
            practice_level=mission.practice_level,
            content_version=mission.content_version,
        ),
        answer_key=dict(
            correct_option_ids=answers,
            accepted_text_answers_by_question=accepted,
            question_evaluations=evaluations,
        ),
        scene_object_id=UUID(result.questions[-1].object_key),
    )
