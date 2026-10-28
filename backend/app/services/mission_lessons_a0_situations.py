"""Deterministic A0 M04/M05 lesson payloads and grammar-lesson tasks."""

from __future__ import annotations

import random
import unicodedata
from uuid import UUID, uuid5

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_a0_situations import (
    A0SituationLesson,
    SituationQuestion,
)
from app.schemas.missions import A0MissionSnapshot, TaughtChunk
from app.schemas.tasks import SessionTask
from app.services import a0_lexicon as lex
from app.services.mission_lessons import mission_version


def _rng(payload, salt):
    return random.Random(f"{payload['seed']}:{salt}")


def build_a0_situation_payload(payload):
    """Prepare reviewed phrases and learner facts for the closed lesson builder."""
    mission_id = payload["missionId"]
    rows = {str(row["key"]): row for row in payload["approvedObjects"]}
    facts = payload.get("learnerFacts") or {}
    if mission_id == "M04":
        focus_key = str(facts.get("ownedObjectId") or "")
        if focus_key not in rows:
            return {**payload, "approvedObjects": [], "prep": [], "approvedTargetTexts": []}
        preferred = [focus_key]
    else:
        preference = facts.get("preference") or facts
        compared = [str(item) for item in preference.get("sceneObjectIds", [])]
        focus_key = str(
            preference.get("chosenObjectId") if len(compared) == 2
            else compared[0] if compared else ""
        )
        if focus_key not in rows:
            return {**payload, "approvedObjects": [], "prep": [], "approvedTargetTexts": []}
        preferred = [focus_key, *compared]
    ordered = [rows[key] for key in dict.fromkeys(preferred) if key in rows]
    ordered.extend(row for key, row in rows.items() if key not in preferred)
    payload = {**payload, "approvedObjects": ordered[:3], "focusObjectId": focus_key}
    focus = rows[focus_key]
    nouns = {row["key"]: lex.row_noun(row) for row in payload["approvedObjects"]}
    facts = dict(facts)
    if mission_id == "M05":
        preference = dict(facts.get("preference") or facts)
        if len(preference.get("sceneObjectIds", [])) == 2:
            preference["reaction"] = preference.get("reaction") or "like"
        facts["preference"] = preference
    payload["learnerFacts"] = facts
    if mission_id == "M04":
        return _build_ownership_payload(payload, focus, nouns)
    return _build_preference_payload(payload, focus, nouns)


def _prep_add(prep, text, translation):
    if text not in {item["text"] for item in prep}:
        prep.append({"text": text, "translation": translation})


def _choice_question(
    question_id, prompt, instruction, section, object_key, options, correct_label,
    target_group, payload, *, salt, gap_type=None, **extra,
):
    options = list(options)
    _rng(payload, salt).shuffle(options)
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


def _target_texts(prep, questions):
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


def _build_ownership_payload(payload, x, nouns):
    language = payload["targetLanguage"]
    rows = payload["approvedObjects"]
    target_id = x["key"]
    y = next(row for row in rows if row["key"] != target_id)
    owner_name = payload["learnerFacts"].get("ownerName")
    x_chunks = lex.ownership_chunks(language, nouns[target_id], x["source"], owner_name)
    y_chunks = lex.ownership_chunks(language, nouns[y["key"]], y["source"], owner_name)
    owner_label = owner_name or "you"
    owner_possessive = f"{owner_name}'s" if owner_name else "yours"
    yes = lex.YES_NO[language][0]
    no = lex.YES_NO[language][1]
    section = "Lost and found"
    prep = []
    short_owner = f"{owner_name}'s" if owner_name else "mine"
    for key, english in (
        ("mine", f"It's {short_owner}."),
        ("notMine", f"It's not {short_owner}."),
        ("isYours", f"Is this {owner_possessive}?"),
        ("xMine", x_chunks["englishMine"]),
        ("xYours", x_chunks["englishYours"]),
    ):
        _prep_add(prep, x_chunks[key], english)
    _prep_add(prep, y_chunks["xMine"], y_chunks["englishMine"])
    q3 = f"{yes} {x_chunks['mine']}"
    q6 = f"{yes} {x_chunks['xMine']}"
    _prep_add(prep, q3, f"Yes. It's {short_owner}.")
    _prep_add(prep, q6, f"Yes. {x_chunks['englishMine']}")
    target_group = "recognise-ownership"
    questions = [
        _choice_question(
            "M04-Q1", x_chunks["isYours"], "Answer yes or no.", section, target_id,
            [yes, no], yes, "recognise-ownership", payload, salt="q1",
            audio_text=x_chunks["isYours"],
        ),
        _choice_question(
            "M04-Q2", "Listen to Linguini. What does Linguini ask?",
            "Listen to Linguini. What does Linguini ask?", section, target_id,
            [f"It belongs to {owner_label}", f"{owner_label.capitalize()} likes it"],
            f"It belongs to {owner_label}", target_group,
            payload, salt="q2", option_icons={"option-1": "belongs", "option-2": "likes"},
            audio_text=x_chunks["isYours"], listen_first=True,
        ),
    ]
    # Re-key icon meanings after the stable seeded order is known.
    questions[1].option_icons = {
        option.option_id: ("belongs" if option.label.startswith("It belongs") else "likes")
        for option in questions[1].options
    }
    mine_pred = x_chunks["minePredicate"]
    yours_pred = x_chunks["yoursPredicate"]
    q3_options = [x_chunks["mine"], x_chunks["notMine"]]
    q3_template = f"{yes} ___"
    questions.append(_choice_question(
        "M04-Q3", "Complete the answer.", "Choose the words that complete the answer.",
        section, target_id, q3_options, x_chunks["mine"], "say-mine", payload,
        salt="q3", gap_type="chunkChoice", slot_template=q3_template,
        complete_chunk=q3, complete_translation=f"Yes. It's {short_owner}.",
        typed_allowed=language != "ko",
        accepted_text_answers=[x_chunks["mine"], q3],
    ))
    q4_noun = lex.situational_noun(language, nouns[target_id], topic=language == "ko")
    q4_template = f"{q4_noun.capitalize()} ___."
    q4_complete = x_chunks["xMine"]
    q4 = _choice_question(
        "M04-Q4", "Complete the sentence.", "Choose the words that complete the sentence.",
        section, target_id, [mine_pred, yours_pred], mine_pred, "say-mine", payload,
        salt="q4", gap_type="chunkChoice", slot_template=q4_template,
        complete_chunk=q4_complete, complete_translation=x_chunks["englishMine"],
        typed_allowed=language != "ko",
        accepted_text_answers=[mine_pred, q4_complete],
    )
    questions.append(q4)
    x_n = lex.situational_noun(language, nouns[target_id], topic=True)
    localized_owner = (
        {"Ana": "아나", "Leo": "레오"}.get(owner_name)
        if language == "ko" else owner_name
    )
    mine_word = localized_owner or {
        "es": "mí" + ("o" if nouns[target_id].gender == lex.M else "a"),
        "fr": "moi", "de": "mir", "ko": "제",
    }[language]
    yours_word = {
        "es": "tuy" + ("o" if nouns[target_id].gender == lex.M else "a"),
        "fr": "toi", "de": "dir", "ko": "본인",
    }[language]
    q5_template = {
        "es": f"{lex.situational_noun(language, nouns[target_id]).capitalize()} es ___.",
        "fr": f"{lex.situational_noun(language, nouns[target_id]).capitalize()} est à ___.",
        "de": f"{lex.situational_noun(language, nouns[target_id]).capitalize()} gehört ___.",
        "ko": f"{x_n} ___ 거예요.",
    }[language]
    questions.append(_choice_question(
        "M04-Q5", "Listen, then complete the sentence.", "Listen, then complete the sentence.",
        section, target_id, [mine_word, yours_word], mine_word, "say-mine", payload,
        salt="q5", gap_type="audioGap", slot_template=q5_template,
        complete_chunk=q4_complete, complete_translation=x_chunks["englishMine"],
        audio_text=x_chunks["xMine"], listen_first=True,
    ))
    questions.append(_choice_question(
        "M04-Q6", "Finish the conversation.", "Choose the answer that finishes the conversation.",
        section, target_id, [x_chunks["xMine"], y_chunks["xMine"]], x_chunks["xMine"],
        "say-mine", payload, salt="q6", gap_type="dialogueGap",
        slot_template=f"{yes} ___", complete_chunk=q6,
        complete_translation=f"Yes. {x_chunks['englishMine']}",
        dialogue=[
            {
                "speaker": "linguini", "text": x_chunks["isYours"],
                "translation": f"Is this {owner_possessive}?",
            },
            {
                "speaker": "learner", "text": f"{yes} ___",
                "translation": f"Yes. The object is {owner_possessive}.",
            },
        ],
        correct_note=f"Yes—Linguini knows the {x['source']} is {owner_possessive}.",
        outcome={
            "text": f"Great—Linguini knows it is {owner_possessive}.",
            "kind": "returned",
            "scene_object_id": target_id,
        },
    ))
    approved = _target_texts(prep, questions)
    return {
        **payload,
        "prep": prep,
        "approvedTargetTexts": approved,
        "questions": _plain(questions),
    }


def _lower_first(value):
    return value[:1].lower() + value[1:]


def _build_preference_payload(payload, focus, nouns):
    language = payload["targetLanguage"]
    rows = payload["approvedObjects"]
    facts = payload["learnerFacts"]["preference"]
    compared = [str(item) for item in facts.get("sceneObjectIds", [])]
    focus_key = focus["key"]
    reaction = facts["reaction"]
    subject_name = facts.get("subjectName")
    subject = subject_name or "you"
    subject_verb = "chooses" if subject_name else "choose"
    distractor_key = compared[1] if len(compared) > 1 else None
    if not distractor_key or distractor_key == focus_key or distractor_key not in nouns:
        candidates = [row["key"] for row in rows if row["key"] != focus_key]
        if not candidates:
            return {**payload, "approvedObjects": [], "prep": [], "approvedTargetTexts": []}
        distractor_key = _rng(payload, "M05-other").choice(candidates)
    other = next(row for row in rows if row["key"] == distractor_key)
    f = lex.preference_chunks(language, nouns[focus_key], focus["source"], subject_name)
    o = lex.preference_chunks(language, nouns[distractor_key], other["source"], subject_name)
    yes = lex.YES_NO[language][0 if reaction == "like" else 1]
    section = "Picnic choice"
    statement = f[reaction]
    prep = []
    for text, translation in (
        (f["like"], f["englishLike"]),
        (f["dislike"], f["englishDislike"]),
        (f["doYouLike"], f["englishDoYouLike"]),
        (
            f["whatChoose"],
            f"What does {subject_name} choose?" if subject_name else "What do you choose?",
        ),
    ):
        _prep_add(prep, text, translation)
    if reaction == "dislike":
        _prep_add(
            prep, o["iChoose"],
            f"{subject.capitalize()} {subject_verb} the {other['source']}.",
        )
    q5_statement = statement if subject_name else _lower_first(statement)
    q5_complete = f"{yes.rstrip('.')}, {q5_statement}"
    _prep_add(
        prep, q5_complete,
        f"{'Yes' if reaction == 'like' else 'No'}, "
        f"{f['englishLike' if reaction == 'like' else 'englishDislike']}",
    )
    q6_complete = statement if reaction == "like" else f"{f['dislike']} {o['iChoose']}"
    q6_translation = f["englishLike"] if reaction == "like" else (
        f"{f['englishDislike']} {subject.capitalize()} {subject_verb} the {other['source']}."
    )
    _prep_add(prep, q6_complete, q6_translation)
    all_phrases = {
        row["key"]: lex.preference_chunks(
            language, nouns[row["key"]], row["source"], subject_name,
        )
        for row in rows
    }
    for row in rows:
        phrase = all_phrases[row["key"]]
        _prep_add(prep, phrase["like"], phrase["englishLike"])
        _prep_add(prep, phrase["dislike"], phrase["englishDislike"])
    target_group = "recognise-preference"
    questions = [
        _choice_question(
            "M05-Q1", "Which phrase matches the scenario?",
            "Choose the phrase that matches the scenario.", section, focus_key,
            [f["like"], f["dislike"]], statement, "say-preference",
            payload, salt="q1",
        ),
    ]
    questions.append(_choice_question(
        "M05-Q2", "Listen to the sentence. Like or don't like?",
        "Listen to the sentence. Like or don't like?", section, focus_key,
        ["Like", "Don't like"], "Like" if reaction == "like" else "Don't like",
        target_group, payload, salt="q2", audio_text=statement, listen_first=True,
        option_icons={},
    ))
    questions[1].option_icons = {
        option.option_id: ("like" if option.label == "Like" else "dislike")
        for option in questions[1].options
    }
    q3_options = [f["like"], f["dislike"]]
    q3_template = "___"
    q3_correct = (
        q3_options[0] if reaction == "like" else q3_options[1]
    )
    q3_complete = statement
    questions.append(_choice_question(
        "M05-Q3", "Complete the sentence.", "Choose the words that complete the sentence.",
        section, focus_key, q3_options, q3_correct, "say-preference", payload,
        salt="q3", gap_type="chunkChoice", slot_template=q3_template,
        complete_chunk=q3_complete,
        complete_translation=f["englishLike" if reaction == "like" else "englishDislike"],
        typed_allowed=language != "ko",
        accepted_text_answers=[q3_correct, q3_complete],
    ))
    n_f = lex.situational_noun(language, nouns[focus_key], accusative=language == "de")
    n_o = lex.situational_noun(language, nouns[distractor_key], accusative=language == "de")
    q4_template = f"{f['likeFrame' if reaction == 'like' else 'dislikeFrame']}."
    object_options = [(focus_key, n_f), (distractor_key, n_o)]
    second_key = compared[1] if len(compared) > 1 else None
    if second_key and second_key != focus_key and second_key in nouns and second_key not in {
        key for key, _label in object_options
    } and len(object_options) < 3:
        object_options.append((
            second_key,
            lex.situational_noun(
                language, nouns[second_key], accusative=language == "de"
            ),
        ))
    _rng(payload, "q4").shuffle(object_options)
    q4_options = [label for _key, label in object_options]
    q4 = _choice_question(
        "M05-Q4", "Choose the object that completes the sentence.",
        "Choose the object that completes the sentence.", section, focus_key,
        q4_options, n_f, "say-preference", payload, salt="q4",
        gap_type="pictureToBlank", slot_template=q4_template,
        complete_chunk=statement,
        complete_translation=f["englishLike" if reaction == "like" else "englishDislike"],
    )
    # The picture labels and IDs share the already shuffled visible order.
    q4.option_object_keys = {
        option.option_id: next(
            key for key, label in object_options if fold(label) == fold(option.label)
        )
        for option in q4.options
    }
    questions.append(q4)
    q5_like = f["like"] if reaction == "like" else f["dislike"]
    q5_response = "Yes" if reaction == "like" else "No"
    q5_dialogue = [
        {"speaker": "linguini", "text": f["doYouLike"], "translation": f["englishDoYouLike"]},
        {
            "speaker": "learner",
            "text": f"{yes.rstrip('.')}, ___",
            "translation": f"{q5_response}, ___",
        },
    ]
    questions.append(_choice_question(
        "M05-Q5", "Finish the conversation.", "Choose the answer that finishes the conversation.",
        section, focus_key,
        [f["like"], f["dislike"]] if subject_name else [
            _lower_first(f["like"]), _lower_first(f["dislike"]),
        ],
        q5_like if subject_name else _lower_first(q5_like),
        "say-preference", payload, salt="q5",
        gap_type="dialogueGap", slot_template=f"{yes.rstrip('.')}, ___",
        complete_chunk=q5_complete,
        complete_translation=f"{q5_response}, "
        f"{f['englishLike' if reaction == 'like' else 'englishDislike']}",
        dialogue=q5_dialogue,
    ))
    if reaction == "like":
        q6_template = f"{f['likeFrame']}."
        q6_options = [n_f, n_o]
        q6_correct = n_f
        q6_complete = f["like"]
        q6_translation = f["englishLike"]
        outcome = {
            "text": f"{subject.capitalize()} {subject_verb} the {focus['source']}.",
            "kind": "basket",
            "scene_object_id": focus_key,
        }
        correct_note = f"{subject.capitalize()} {subject_verb} the {focus['source']}."
        option_keys = {n_f: focus_key, n_o: distractor_key}
    else:
        i_choose = o["iChoose"].replace(n_o, "___")
        q6_template = f"{f['dislike']} {i_choose}"
        q6_options = [n_o, n_f]
        q6_correct = n_o
        q6_complete = q6_translation = ""
        outcome = {
            "text": (
                f"The {focus['source']} stays behind. "
                f"{subject.capitalize()} {subject_verb} the {other['source']}."
            ),
            "kind": "basket",
            "scene_object_id": distractor_key,
        }
        correct_note = f"{subject.capitalize()} {subject_verb} the {other['source']}."
        option_keys = {n_o: distractor_key, n_f: focus_key}
    if reaction == "dislike":
        q6_complete = f"{f['dislike']} {o['iChoose']}"
        q6_translation = (
            f"{f['englishDislike']} {subject.capitalize()} {subject_verb} "
            f"the {other['source']}."
        )
    q6_dialogue = [
        {
            "speaker": "linguini", "text": f["whatChoose"],
            "translation": (
                f"What does {subject_name} choose?" if subject_name else "What do you choose?"
            ),
        },
        {"speaker": "learner", "text": q6_template, "translation": q6_translation},
    ]
    q6 = _choice_question(
        "M05-Q6", "Finish the conversation.", "Choose the answer that finishes the conversation.",
        section, focus_key, q6_options, q6_correct, "say-preference", payload,
        salt="q6", gap_type="dialogueGap", slot_template=q6_template,
        complete_chunk=q6_complete, complete_translation=q6_translation,
        dialogue=q6_dialogue, correct_note=correct_note, outcome=outcome,
    )
    q6.option_object_keys = {
        option.option_id: next(
            key for label, key in option_keys.items()
            if fold(label) == fold(option.label)
        )
        for option in q6.options
    }
    questions.append(q6)
    approved = _target_texts(prep, questions)
    return {
        **payload, "prep": prep, "approvedTargetTexts": approved,
        "questions": _plain(questions),
    }


def _plain(questions):
    """JSON-ready questions, so the payload can be sent to the model and cached."""
    return [question.model_dump(mode="json", by_alias=True) for question in questions]


def build_a0_situation_lesson(payload):
    prepared = build_a0_situation_payload(payload)
    return A0SituationLesson.model_validate(
        dict(title=prepared["title"], questions=prepared["questions"]),
    )


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


def a0_situation_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    prepared = build_a0_situation_payload(payload)
    focus = next(
        row for row in prepared["approvedObjects"]
        if row["key"] == prepared["focusObjectId"]
    )
    if mission.mission_id == "M04":
        owner_name = prepared["learnerFacts"].get("ownerName")
        owner = f"{owner_name}'s" if owner_name else "yours"
        scenario = f"Let's pretend the {focus['source']} is {owner}."
    else:
        preference_facts = prepared["learnerFacts"]["preference"]
        reaction = preference_facts["reaction"]
        subject_name = preference_facts.get("subjectName")
        preference = "like" if reaction == "like" else "don't like"
        if subject_name:
            preference = "likes" if reaction == "like" else "doesn't like"
        subject = subject_name or "you"
        scenario = f"Let's pretend {subject} {preference} the {focus['source']}."
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
                for answer in _normalized_equivalents(candidate, payload["targetLanguage"])
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
            roleplay_premise=scenario,
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
            owner_name=facts.get("ownerName"),
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
            subject_name=preference.get("subjectName"),
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
