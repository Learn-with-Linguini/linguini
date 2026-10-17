"""Build the M05 A1 preference payload and its validated grammar lesson."""

from uuid import UUID

from app.schemas.roleplay import parse_roleplay_facts
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.possessives import definite_noun_phrase
from app.services.preferences import preference_sentence

M05_FOCUS = "sayWhatYouLike"
_CHOOSE_PROMPTS = {"es": "Elige la frase correcta.", "fr": "Choisis la bonne phrase."}
_BUILD_PROMPTS = {
    "first": {
        "es": "¿Te gusta {noun}? Responde con una frase.",
        "fr": "Tu aimes {noun} ? Réponds avec une phrase.",
    },
    "third": {
        "es": "¿A {name} le gusta {noun}? Responde con una frase.",
        "fr": "Est-ce que {name} aime {noun} ? Réponds avec une phrase.",
    },
}
_PROMPT_TRANSLATIONS = {
    "first": "Do you like the {label}? Answer with a sentence.",
    "third": "Does {name} like the {label}? Answer with a sentence.",
}
_EXPLANATIONS = {
    "es": (
        "For this practice, the likes are pretend. Me gusta… = I like… · "
        "No me gusta… = I don't like… · A Ana le gusta… = Ana likes…"
    ),
    "fr": (
        "For this practice, the likes are pretend. J'aime… = I like… · "
        "Je n'aime pas… = I don't like… · Ana aime… = Ana likes…"
    ),
}
_EVALUATIONS = {
    "matchPreference": (
        ["understand-preference"], "recognition", ["matches-assigned-preference"]
    ),
    "choosePreference": (["choose-preference"], "recognition", ["chooses-preference"]),
    "buildMyPreference": (
        ["say-my-preference"], "construction", ["says-my-preference"]
    ),
    "buildTheirPreference": (
        ["say-their-preference"], "construction", ["says-their-preference"]
    ),
}


def _invalid_payload(language, mission, session_id):
    return {
        "invalidRoleplay": True,
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "facts": [],
        "fact_details": [],
        "all_markers": {},
        "seed": f"{session_id}:M05",
    }


def _subject(fact):
    return fact.subject_names[0] if fact.subject_names else None


def _premise(fact, label):
    if fact.subject_type == "learner":
        subject = "you"
    else:
        subject = _subject(fact)
    preference = "like" if fact.preference == "like" else "don't like"
    if subject == "you":
        return f"Let's pretend you {preference} the {label}."
    verb = "likes" if fact.preference == "like" else "doesn't like"
    return f"Let's pretend {subject} {verb} the {label}."


def _match_premise(fact):
    subject = "you" if fact.subject_type == "learner" else _subject(fact)
    if fact.subject_type == "learner":
        verb = "like" if fact.preference == "like" else "don't like"
    else:
        verb = "likes" if fact.preference == "like" else "doesn't like"
    return f"Let's pretend {subject} {verb} one of these things."


def _build_prompt(person, language, name, noun):
    if person == "third" and language == "fr":
        vowels = "aeiouyàâäéèêëîïôöùûüœ"
        connector = "qu'" if name[0].casefold() in vowels else "que "
        return f"Est-ce {connector}{name} aime {noun} ? Réponds avec une phrase."
    values = {"noun": noun}
    if person == "third":
        values["name"] = name
    return _BUILD_PROMPTS[person][language].format(**values)


def m05_payload(mission, language, objects, words, translated_scene, session_id, context=None):
    """Only render preference statements from validated assigned facts."""
    language = language.lower()
    context = context or {}
    if language not in {"es", "fr"}:
        return _invalid_payload(language, mission, session_id)
    markers = context.get("review_markers") or {}
    parsed = parse_roleplay_facts(context.get("roleplay_facts"), [obj.id for obj in objects])
    if (
        parsed is None
        or len(parsed) != 3
        or any(fact.fact_type != "preference" for fact in parsed)
        or any(fact.subject_type not in {"learner", "namedCharacter"} for fact in parsed)
        or sum(fact.subject_type == "learner" and fact.preference == "like"
               for fact in parsed) != 1
        or sum(fact.subject_names == ["Ana"] and fact.preference == "dislike"
               for fact in parsed) != 1
        or any(
            fact.subject_names not in ([], ["Ana"], ["Leo"])
            or (fact.subject_names == ["Leo"] and fact.preference != "like")
            for fact in parsed
        )
    ):
        return _invalid_payload(language, mission, session_id)
    roles = {
        (fact.subject_type, tuple(fact.subject_names), fact.preference)
        for fact in parsed
    }
    expected_roles = {
        ("learner", (), "like"),
        ("namedCharacter", ("Ana",), "dislike"),
        ("namedCharacter", ("Leo",), "like"),
    }
    if roles != expected_roles or len(roles) != len(parsed):
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
        name = _subject(fact)
        person = "first" if fact.subject_type == "learner" else "third"
        like = fact.preference == "like"
        gender = noun_gender(terms.get(object_key), word)
        sentence = preference_sentence(
            language, person, name, like, word.display_text, gender
        )
        contrast = preference_sentence(
            language, person, name, not like, word.display_text, gender
        )
        noun_phrase = definite_noun_phrase(language, word.display_text, gender)
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
            matchPremise=_match_premise(fact),
            subjectType=fact.subject_type,
            subjectNames=fact.subject_names,
            preference=fact.preference,
            person=person,
            name=name,
            like=like,
        ))
    details = {item["objectKey"]: item for item in fact_details}
    learner_fact = next(
        fact for fact in parsed
        if fact.subject_type == "learner" and fact.preference == "like"
    )
    ana_fact = next(
        fact for fact in parsed
        if fact.subject_names == ["Ana"] and fact.preference == "dislike"
    )
    learner = details[str(learner_fact.scene_object_id)]
    ana = details[str(ana_fact.scene_object_id)]
    leo_fact = next((fact for fact in parsed if fact.subject_names == ["Leo"]), None)
    leo = details[str(leo_fact.scene_object_id)] if leo_fact else None
    choice = leo
    other = next(item for item in fact_details if item["objectKey"] != choice["objectKey"])
    other_object_sentence = preference_sentence(
        language, choice["person"], choice["name"], choice["like"],
        other["noun"], other["gender"],
    )
    for fact in fact_details:
        if fact["nounPhrase"] is None:
            continue
        fact["build_prompt"] = _build_prompt(
            fact["person"], language, fact["name"], fact["nounPhrase"],
        )
        fact["build_prompt_translation"] = _PROMPT_TRANSLATIONS[fact["person"]].format(
            label=fact["label"], name=fact["name"],
        )
    choice = {
        **details[str(leo_fact.scene_object_id)],
        "other_object_sentence": other_object_sentence,
    }
    leo = choice
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M05",
        "facts": facts,
        "fact_details": fact_details,
        "all_markers": all_markers,
        "learner": learner,
        "ana": ana,
        "leo": leo,
        "choice": choice,
        "choose_prompt": _CHOOSE_PROMPTS.get(language),
        "choose_prompt_translation": "Choose the correct sentence.",
        "explanation": _EXPLANATIONS.get(language),
    }


def m05_ready(payload):
    """Whether the learner and Ana have reviewed positive/negative sentences."""
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
        and ana.get("matchPremise")
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


def m05_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """Build the public M05 grammar lesson; preference attempts never affect vocabulary."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        corrections = (
            [
                dict(
                    mistake="wrongObject",
                    answers=[option.option_id],
                    correction=label,
                    explanation="That marker isn't the thing in the sentence.",
                )
                for option in question.options if option.option_id != question.correct_option_id
            ]
            if question.interaction_type == "multipleChoice"
            else [dict(
                mistake="wordOrder",
                correction=question.correct_text,
                explanation="Use the taught like or dislike statement.",
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
            object_label=(
                None if question.purpose == "matchPreference"
                else detail["label"].capitalize()
            ),
            section=question.section,
            roleplay_premise=question.roleplay_premise,
            prompt_translation=question.prompt_translation,
            marker_object_ids=(
                {key: UUID(value) for key, value in question.option_object_ids.items()}
                if question.option_object_ids is not None else None
            ),
            keep_option_order=(
                True if question.interaction_type == "multipleChoice" else None
            ),
        )

    return build_mission_task(
        session_id,
        mission,
        M05_FOCUS,
        result,
        evaluate,
        shown,
        content_fields=dict(explanation=payload["explanation"], roleplay_facts=payload["facts"]),
    )
