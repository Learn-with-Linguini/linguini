"""The A0 scene lesson task: preparation cards, grading and corrections."""

from __future__ import annotations

from app.services.lesson_tasks.common import build_mission_task

_EXPLANATIONS = {
    "M01": "Learn each object's name, then say what it is.",
    "M02": "Learn the names, then find each object in your photo.",
    "M03": "Learn one, two and three, then say how many.",
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
}


_NAME_PURPOSES = {"matchName", "findNamed", "chooseName", "listenSelect"}


_MARKER_PURPOSES = {"matchName", "findNamed", "listenSelect"}


def with_article(noun):
    return f"an {noun}" if noun[:1] in "aeiou" else f"a {noun}"


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
    names = [card(row["name"], row["key"]) for row in rows]
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
        meaning = f"This is {with_article(target['source'])}: {target['identify']}"
        return [dict(mistake="wrongObject", answers=[option.option_id], correction=label,
                     explanation=meaning) for option in wrong], meaning
    if purpose in {"chooseName"}:
        return [dict(mistake="wrongWord", answers=[option.option_id], correction=label,
                     explanation=f"This is {target['name']}.") for option in wrong], None
    if purpose in {"countGroup", "matchChunk"}:
        note = f"{label} — {payload['approvedTranslations'].get(label, label)}."
        return [dict(mistake="wrongQuantity", answers=[option.option_id], correction=label,
                     explanation=note) for option in wrong], note
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
        return fields

    task = build_mission_task(
        session_id, mission, f"a0{mission.mission_id}", result, evaluate, shown,
        content_fields=dict(prep=_prep(payload), explanation=_EXPLANATIONS[mission.mission_id]),
    )
    return task.model_copy(update={
        "answer_key": task.answer_key.model_copy(update={"statement_correct": statement_correct}),
    })
