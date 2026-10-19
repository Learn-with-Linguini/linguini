"""Build the M04 A1 ownership payload and its validated grammar lesson."""

from app.schemas.roleplay import parse_roleplay_facts
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.possessives import (
    definite_noun_phrase,
    possessive_sentence,
)

M04_FOCUS = "sayWhoseIsIt"
_CHOOSE_PROMPTS = {"es": "Elige la frase correcta.", "fr": "Choisis la bonne phrase."}
_BUILD_PROMPTS = {
    "es": "¿De quién es {noun}? Responde con una frase.",
    "fr": "À qui est {noun} ? Réponds avec une phrase.",
}
_PROMPT_TRANSLATIONS = {
    "es": "Whose is the {label}? Answer with a sentence.",
    "fr": "Whose is the {label}? Answer with a sentence.",
}
_EXPLANATIONS = {
    "es": (
        "For this practice, the owners are pretend. mi = my · su = his/her "
        "(the owner's name tells you whose)."
    ),
    "fr": (
        "For this practice, the owners are pretend. mon/ma = my · son/sa = his/her "
        "— they agree with the thing, not the owner."
    ),
}
_EVALUATIONS = {
    "chooseOwner": (["choose-possessive"], "recognition", ["chooses-possessive"]),
    "buildMine": (["say-mine"], "construction", ["says-mine"]),
    "buildTheirs": (["say-theirs"], "construction", ["says-theirs"]),
}


def _invalid_payload(language, mission, session_id):
    return {
        "invalidRoleplay": True,
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "facts": [],
        "fact_details": [],
        "all_markers": {},
        "seed": f"{session_id}:M04",
    }


def _fact_subject(fact):
    return fact.owner_names[0] if fact.owner_names else None


def _premise(fact, label):
    if fact.owner_type == "learner":
        return f"Let's pretend the {label} is yours."
    return f"Let's pretend the {label} is {_fact_subject(fact)}'s."


def m04_payload(mission, language, objects, words, translated_scene, session_id, context=None):
    """Only render statements from validated assigned facts and confirmed objects."""
    language = language.lower()
    if language not in {"es", "fr"}:
        return _invalid_payload(language, mission, session_id)
    context = context or {}
    markers = context.get("review_markers") or {}
    raw_facts = context.get("roleplay_facts")
    parsed = parse_roleplay_facts(raw_facts, [obj.id for obj in objects])
    if (
        parsed is None
        or len(parsed) != 3
        or any(fact.fact_type != "ownership" for fact in parsed)
        or any(fact.owner_type not in {"learner", "namedCharacter"} for fact in parsed)
        or sum(fact.owner_type == "learner" for fact in parsed) != 1
        or sum(fact.owner_names == ["Ana"] for fact in parsed) != 1
        or sum(fact.owner_names == ["Leo"] for fact in parsed) != 1
        or any(fact.owner_names not in ([], ["Ana"], ["Leo"]) for fact in parsed)
    ):
        return _invalid_payload(language, mission, session_id)
    object_by_id = {
        str(obj.id): (obj, word)
        for obj, word in zip(objects, words, strict=True)
    }
    facts = [fact.model_dump(mode="json", by_alias=True) for fact in parsed]
    all_markers = {}
    for fact in parsed:
        object_key = str(fact.scene_object_id)
        marker = markers.get(object_key, markers.get(fact.scene_object_id))
        if not isinstance(marker, int) or marker < 1:
            return _invalid_payload(language, mission, session_id)
        all_markers[object_key] = marker
    if len(set(all_markers.values())) != len(all_markers):
        return _invalid_payload(language, mission, session_id)
    if len({object_by_id[key][0].label.strip().casefold() for key in all_markers}) != len(parsed):
        return _invalid_payload(language, mission, session_id)

    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    fact_details = []
    for fact in parsed:
        object_key = str(fact.scene_object_id)
        obj, word = object_by_id[object_key]
        name = _fact_subject(fact)
        gender = noun_gender(terms.get(object_key), word)
        sentence = possessive_sentence(
            language, fact.possessive_person, name, word.display_text, gender,
        )
        contrast_person = "third" if fact.possessive_person == "first" else "first"
        contrast_name = "Ana" if contrast_person == "third" else None
        contrast = possessive_sentence(
            language, contrast_person, contrast_name, word.display_text, gender,
        )
        noun_phrase = definite_noun_phrase(
            language, word.display_text, gender,
        )
        fact_details.append(dict(
            objectKey=object_key,
            marker=all_markers[object_key],
            label=obj.label.strip(),
            noun=word.display_text,
            gender=gender,
            sentence=sentence,
            contrast=contrast,
            nounPhrase=noun_phrase,
            premise=_premise(fact, obj.label.strip()),
            ownerType=fact.owner_type,
            ownerNames=fact.owner_names,
        ))
    details = {item["objectKey"]: item for item in fact_details}
    learner_fact = next(fact for fact in parsed if fact.owner_type == "learner")
    ana_fact = next(fact for fact in parsed if fact.owner_names == ["Ana"])
    learner = details[str(learner_fact.scene_object_id)]
    ana = details[str(ana_fact.scene_object_id)]
    leo_fact = next((fact for fact in parsed if fact.owner_names == ["Leo"]), None)
    leo = details[str(leo_fact.scene_object_id)] if leo_fact else None
    choice = leo
    other = next(item for item in fact_details if item["objectKey"] != choice["objectKey"])
    other_object_sentence = possessive_sentence(
        language, "third", "Ana", other["noun"], other["gender"]
    )
    choice = {
        **choice,
        "other_object_sentence": other_object_sentence,
    }
    leo = choice
    for fact in (learner, ana, choice, other):
        if fact["nounPhrase"] is None:
            continue
        fact["build_prompt"] = _BUILD_PROMPTS[language].format(noun=fact["nounPhrase"])
        fact["build_prompt_translation"] = _PROMPT_TRANSLATIONS[language].format(
            label=fact["label"]
        )
    choose_prompt_translation = "Choose the correct sentence."
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M04",
        "facts": facts,
        "fact_details": fact_details,
        "all_markers": all_markers,
        "learner": learner,
        "ana": ana,
        "leo": leo,
        "choice": choice,
        "choose_prompt": _CHOOSE_PROMPTS.get(language),
        "choose_prompt_translation": choose_prompt_translation,
        "explanation": _EXPLANATIONS.get(language),
    }


def m04_ready(payload):
    """Whether both core facts and all required contrast sentences are reviewed."""
    learner, ana, leo, choice = (
        payload.get("learner", {}),
        payload.get("ana", {}),
        payload.get("leo", {}),
        payload.get("choice", {}),
    )
    return bool(
        learner.get("sentence")
        and learner.get("contrast")
        and learner.get("build_prompt")
        and ana.get("sentence")
        and ana.get("contrast")
        and ana.get("build_prompt")
        and leo.get("sentence")
        and leo.get("contrast")
        and leo.get("other_object_sentence")
        and choice.get("sentence")
        and choice.get("contrast")
        and choice.get("other_object_sentence")
        and len({
            choice.get("sentence"),
            choice.get("contrast"),
            choice.get("other_object_sentence"),
        }) == 3
        and payload.get("choose_prompt")
        and payload.get("explanation")
    )


def m04_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """Build the public M04 grammar lesson; its evaluations never affect vocabulary."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        corrections = (
            [
                dict(
                    mistake="wrongWord",
                    answers=[option.option_id],
                    correction=label,
                    explanation="Check whose pretend thing the sentence describes.",
                )
                for option in question.options if option.option_id != question.correct_option_id
            ]
            if question.interaction_type == "multipleChoice"
            else [dict(
                mistake="wordOrder",
                correction=question.correct_text,
                explanation="Use the taught possessive statement.",
            )]
        )
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[],
            corrections=corrections,
        )

    def shown(question):
        detail = next(
            item for item in payload["fact_details"] if item["objectKey"] == question.object_key
        )
        return dict(
            scene_object_id=question.object_key,
            object_label=detail["label"].capitalize(),
            section=question.section,
            roleplay_premise=question.roleplay_premise,
            prompt_translation=question.prompt_translation,
            keep_option_order=(
                True if question.interaction_type == "multipleChoice" else None
            ),
        )

    return build_mission_task(
        session_id,
        mission,
        M04_FOCUS,
        result,
        evaluate,
        shown,
        content_fields=dict(explanation=payload["explanation"], roleplay_facts=payload["facts"]),
    )
