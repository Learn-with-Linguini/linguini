"""Deterministic A2 mission lessons validated against closed, reviewed fact sets."""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.ai.features.learning_tasks.mission import (
    MissionGeneration,
    fold,
    tokens,
    unique_question_ids,
)
from app.ai.features.learning_tasks.schemas import GeneratedChoice
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.schemas.base import ApiModel, NonEmptyText
from app.services.mission_language_a2 import A2_ENABLED_LANGUAGES, validate_possessive
from app.services.quantities import NUMBER_WORDS

type A2Purpose = Literal[
    "chooseSceneMarker",
    "buildSceneFact",
    "chooseSceneDescription",
    "buildSceneDescription",
    "followUpSceneFact",
    "readAttributeClue",
    "buildLocationClue",
    "chooseUniqueTarget",
    "clarifyDistractor",
    "buildTargetSentence",
    "countGroup",
    "buildQuantity",
    "compareGroups",
    "correctRoleplayCount",
    "buildComparison",
    "chooseAssignedObject",
    "choosePossessive",
    "clarifyOwnership",
    "buildBelonging",
    "buildOwnershipDescription",
]

_EXPECTED = {
    "M01": [
        "chooseSceneMarker",
        "buildSceneFact",
        "chooseSceneDescription",
        "buildSceneDescription",
        "followUpSceneFact",
    ],
    "M02": [
        "readAttributeClue",
        "buildLocationClue",
        "chooseUniqueTarget",
        "clarifyDistractor",
        "buildTargetSentence",
    ],
    "M03": [
        "countGroup",
        "buildQuantity",
        "compareGroups",
        "correctRoleplayCount",
        "buildComparison",
    ],
    "M04": [
        "chooseAssignedObject",
        "choosePossessive",
        "buildBelonging",
        "clarifyOwnership",
        "buildOwnershipDescription",
    ],
}
_INTERACTIONS = {
    purpose: "sentenceBuilding"
    if purpose
    in {
        "buildSceneFact",
        "buildSceneDescription",
        "buildLocationClue",
        "buildTargetSentence",
        "buildQuantity",
        "buildComparison",
        "buildBelonging",
        "buildOwnershipDescription",
    }
    else "multipleChoice"
    for purposes in _EXPECTED.values()
    for purpose in purposes
}
_ROLEPLAY_NAMES = {"es": {"Marta"}, "fr": {"Léa"}}
_ENGLISH_COLOURS = {
    "red": "red",
    "white": "white",
    "black": "black",
    "yellow": "yellow",
    "purple": "purple",
    "gold": "gold",
    "silver": "silver",
    "blue": "blue",
    "green": "green",
    "grey": "grey",
    "gray": "grey",
    "brown": "brown",
    "pink": "pink",
    "orange": "orange",
    "beige": "beige",
}


class MissionA2Question(ApiModel):
    question_id: NonEmptyText = Field(max_length=64)
    purpose: A2Purpose
    prompt: NonEmptyText = Field(max_length=300)
    target_language_text: list[NonEmptyText] = Field(default_factory=list)
    option_language: Literal["target", "en"] = "target"
    interaction_type: Literal["multipleChoice", "sentenceBuilding"]
    options: Annotated[list[GeneratedChoice], Field(max_length=4)] = Field(default_factory=list)
    correct_option_id: Annotated[str, Field(max_length=64)] | None = None
    correct_text: Annotated[str, Field(max_length=300)] | None = None
    token_bank: Annotated[
        list[Annotated[NonEmptyText, Field(max_length=80)]], Field(max_length=60)
    ] = Field(default_factory=list)
    answer_chunks: list[NonEmptyText] = Field(default_factory=list)
    distractor_chunks: list[NonEmptyText] = Field(default_factory=list)
    translation: Annotated[str, Field(max_length=300)] | None = None
    object_key: NonEmptyText | None = None
    section: Annotated[str, Field(max_length=80)]
    marker_object_ids: dict[str, str] | None = None
    group_object_ids: list[str] = Field(default_factory=list)
    roleplay_premise: Annotated[str, Field(max_length=300)] | None = None
    planning_facts: list[NonEmptyText] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interaction(self) -> MissionA2Question:
        if self.interaction_type != _INTERACTIONS[self.purpose]:
            raise ValueError("The question interaction does not match its purpose.")
        if self.interaction_type == "multipleChoice":
            ids = [option.option_id for option in self.options]
            if len(ids) < 2 or len(ids) != len(set(ids)):
                raise ValueError("Multiple-choice questions need unique options.")
            labels = [fold(option.label) for option in self.options]
            if len(labels) != len(set(labels)):
                raise ValueError("Multiple-choice questions need unique labels.")
            if self.correct_option_id not in ids or self.correct_text or self.token_bank:
                raise ValueError("Multiple-choice questions need one offered answer.")
            if self.answer_chunks or self.distractor_chunks:
                raise ValueError("Multiple-choice questions cannot include sentence chunks.")
        else:
            if (
                self.options
                or self.correct_option_id
                or not self.correct_text
                or not self.token_bank
                or not self.answer_chunks
            ):
                raise ValueError("Sentence building needs an answer and token bank.")
        return self


class MissionA2Result(ApiModel):
    title: NonEmptyText = Field(max_length=80)
    questions: Annotated[list[MissionA2Question], Field(min_length=5, max_length=5)]


def _approved(payload):
    facts = payload.get("approvedFacts")
    if not isinstance(facts, dict):
        raise LearningTaskGenerationError("A2 generation needs approved facts.")
    return facts


def _question_text(question):
    values = [question.prompt]
    values.extend(option.label for option in question.options)
    if question.correct_text:
        values.append(question.correct_text)
    values.extend(question.token_bank)
    return values


def _join_chunks(chunks):
    text = ""
    for chunk in chunks:
        if chunk in {".", ",", "?", "!", ";", ":"}:
            text = text.rstrip() + chunk
        elif text.endswith(("'", "’")):
            text += chunk
        else:
            text = f"{text} {chunk}".strip()
    return text


def _check_roleplay_provenance(facts, language):
    objects = {row["key"] for row in facts["approvedObjects"]}
    groups = {row["key"]: row for row in facts["approvedCountedGroups"]}
    for fact in facts["approvedRoleplayFacts"]:
        if fact.get("isFictional") is not True or fact.get("source") != "assignedRoleplay":
            raise LearningTaskGenerationError("Role-play facts need explicit assigned provenance.")
        if fact.get("kind") == "ownership":
            if fact.get("objectKey") not in objects:
                raise LearningTaskGenerationError("Ownership references an unapproved object.")
            if fact.get("owner") not in {"learner", *_ROLEPLAY_NAMES[language]}:
                raise LearningTaskGenerationError("Ownership uses an unknown role-play owner.")
        elif fact.get("kind") == "falseCount":
            group = groups.get(fact.get("groupKey"))
            if (
                group is None
                or fact.get("quantity") == group["quantity"]
                or fact.get("quantity") not in NUMBER_WORDS[language]
                or fact.get("numberWord") != NUMBER_WORDS[language][fact["quantity"]]
            ):
                raise LearningTaskGenerationError(
                    "The fictional count must contradict a taught count."
                )
        elif fact.get("kind") == "lostObject":
            if fact.get("objectKey") not in objects:
                raise LearningTaskGenerationError("The role-play clue names an unapproved object.")
        else:
            raise LearningTaskGenerationError("Role-play facts need known provenance.")


def check_closed_facts(payload, result):
    """Reject target-language text or references outside the supplied approved facts."""
    facts = _approved(payload)
    language = payload.get("targetLanguage")
    if language not in A2_ENABLED_LANGUAGES:
        raise LearningTaskGenerationError("A2 mission lessons support Spanish or French only.")
    _check_roleplay_provenance(facts, language)
    allowed = {fold(token) for token in facts["approvedVocabulary"]}
    for question in result.questions:
        if question.marker_object_ids:
            allowed.update(fold(option.label) for option in question.options)
    objects = {row["key"] for row in facts["approvedObjects"]}

    def check_text(text):
        for token in tokens(text):
            normalized = fold(token).strip("¿¡«»")
            if not normalized or normalized in {".", ",", "?", "!", ";", ":"}:
                continue
            if normalized not in allowed:
                raise LearningTaskGenerationError(
                    f"Question uses unapproved vocabulary: {token}"
                )

    for question in result.questions:
        if question.object_key and question.object_key not in objects:
            raise LearningTaskGenerationError("A question references an unapproved object.")
        if question.marker_object_ids and not set(question.marker_object_ids.values()) <= objects:
            raise LearningTaskGenerationError("A marker answer references an unapproved object.")
        if not set(question.group_object_ids) <= objects:
            raise LearningTaskGenerationError("A counted question references an unapproved object.")
        for text in question.target_language_text:
            if text not in question.prompt and text not in (question.roleplay_premise or ""):
                raise LearningTaskGenerationError(
                    "Target-language text must appear in its prompt or role-play premise."
                )
            check_text(text)
        if question.interaction_type == "sentenceBuilding":
            if fold(_join_chunks(question.answer_chunks)) != fold(question.correct_text or ""):
                raise LearningTaskGenerationError("Answer chunks must form the correct sentence.")
            extras = Counter(map(fold, question.token_bank)) - Counter(
                map(fold, question.answer_chunks)
            )
            if extras != Counter(map(fold, question.distractor_chunks)):
                raise LearningTaskGenerationError(
                    "The token bank must contain answer chunks and defined distractors only."
                )
            for text in question.token_bank:
                check_text(text)
        elif question.option_language == "target" and not question.marker_object_ids:
            for option in question.options:
                check_text(option.label)
        if question.planning_facts and question.planning_facts != payload.get("planningFacts", []):
            raise LearningTaskGenerationError(
                "Planning facts must match the confirmed description."
            )
    if payload.get("missionId") == "M04":
        ownership = [
            fact for fact in facts["approvedRoleplayFacts"] if fact.get("kind") == "ownership"
        ]
        if len(ownership) != 2:
            raise LearningTaskGenerationError("M04 needs two explicitly assigned role-play owners.")
    if payload.get("missionId") == "M03":
        for group in facts["approvedCountedGroups"]:
            low = payload["quantityRange"]["min"]
            high = payload["quantityRange"]["max"]
            if not low <= group["quantity"] <= high:
                raise LearningTaskGenerationError(
                    "A counted quantity is outside the mission range."
                )


def _check_sentence_chunks(question):
    if not question.correct_text:
        raise LearningTaskGenerationError("Sentence-building needs a correct answer.")
    if fold(_join_chunks(question.answer_chunks)) != fold(question.correct_text):
        raise LearningTaskGenerationError("The correct sentence must match its answer chunks.")
    extras = Counter(map(fold, question.token_bank)) - Counter(map(fold, question.answer_chunks))
    if extras != Counter(map(fold, question.distractor_chunks)):
        raise LearningTaskGenerationError("Only listed distractor chunks may extend the bank.")


def _check_m02(payload, questions):
    facts = _approved(payload)
    selection = payload["selection"]
    target = next(
        row for row in facts["approvedObjects"] if row["key"] == selection["targetObjectKey"]
    )
    for question in questions[:4]:
        public_text = " ".join(_question_text(question)).casefold()
        for noun in (target["bareNoun"], target["nounPhrase"], target["englishLabel"]):
            if fold(noun) and fold(noun) in fold(public_text):
                raise LearningTaskGenerationError(
                    "M02 hides target nouns until the final question."
                )
    attr = next(
        row for row in facts["approvedAttributes"] if row["key"] == selection["attributeKey"]
    )
    relation = next(
        row for row in facts["approvedRelationships"] if row["key"] == selection["relationshipKey"]
    )
    both = [
        row["key"]
        for row in facts["approvedObjects"]
        if any(
            item["objectKey"] == row["key"]
            and (item["kind"], item["value"]) == (attr["kind"], attr["value"])
            for item in facts["approvedAttributes"]
        )
        and any(
            item["subjectKey"] == row["key"]
            and item["position"] == relation["position"]
            and item["referenceKey"] == relation["referenceKey"]
            for item in facts["approvedRelationships"]
        )
    ]
    if both != [selection["targetObjectKey"]]:
        raise LearningTaskGenerationError("M02 requires exactly one object matching both clues.")
    distractor = next(
        row for row in facts["approvedObjects"] if row["key"] == selection["distractorObjectKey"]
    )
    attribute_match = any(
        item["objectKey"] == distractor["key"]
        and (item["kind"], item["value"]) == (attr["kind"], attr["value"])
        for item in facts["approvedAttributes"]
    )
    relation_match = any(
        item["subjectKey"] == distractor["key"]
        and item["position"] == relation["position"]
        and item["referenceKey"] == relation["referenceKey"]
        for item in facts["approvedRelationships"]
    )
    if attribute_match and relation_match:
        raise LearningTaskGenerationError("The M02 distractor may match at most one clue.")
    choices = {option.option_id: option.label for option in questions[0].options}
    correct_meaning = next(
        label for option_id, label in payload["facts"]["englishChoices"]
        if option_id == questions[0].correct_option_id
    )
    if choices.get(questions[0].correct_option_id) != correct_meaning:
        raise LearningTaskGenerationError("M02 Q1 must translate the selected attribute.")
    if questions[1].correct_text != payload["facts"]["locationClue"]:
        raise LearningTaskGenerationError("M02 Q2 must build the selected relation clue.")
    marker_map = questions[2].marker_object_ids or {}
    marker_options = {option.option_id for option in questions[2].options}
    if (
        marker_map.get(questions[2].correct_option_id) != target["key"]
        or selection["distractorObjectKey"] not in marker_map.values()
        or not marker_options <= marker_map.keys()
    ):
        raise LearningTaskGenerationError("M02 Q3 must offer the target and its distractor.")
    q4_options = {option.option_id: option.label for option in questions[3].options}
    if (
        not questions[3].roleplay_premise
        or distractor["key"] not in questions[3].group_object_ids
    ):
        raise LearningTaskGenerationError("M02 Q4 must show its role-play distractor.")
    if q4_options.get(questions[3].correct_option_id) != payload["facts"]["correctClarification"]:
        raise LearningTaskGenerationError("M02 Q4 must name the detail the distractor lacks.")
    shares_detail = payload["facts"]["distractorSharesAttribute"] or payload["facts"][
        "distractorSharesRelation"
    ]
    if shares_detail and (
        "clarify-shared" not in q4_options
        or q4_options["clarify-shared"] == q4_options[questions[3].correct_option_id]
    ):
        raise LearningTaskGenerationError("M02 Q4 must offer the shared detail as a wrong option.")
    q5 = questions[4].correct_text or ""
    if fold(target["bareNoun"]) not in fold(q5):
        raise LearningTaskGenerationError("M02 Q5 must name the selected target.")


def _check_m03(payload, questions):
    facts = _approved(payload)
    selection = payload["selection"]
    groups = {row["key"]: row for row in facts["approvedCountedGroups"]}
    first, second = groups[selection["firstGroupKey"]], groups[selection["secondGroupKey"]]
    if fold(first["label"]) == fold(second["label"]):
        raise LearningTaskGenerationError("M03 comparisons require different group labels.")
    if first["quantity"] == second["quantity"]:
        raise LearningTaskGenerationError("M03 comparisons cannot use equal quantities.")
    for group in (first, second):
        if (
            not payload["quantityRange"]["min"]
            <= group["quantity"]
            <= payload["quantityRange"]["max"]
        ):
            raise LearningTaskGenerationError("M03 uses only quantities within the taught range.")
    roleplay_facts = [
        fact for fact in facts["approvedRoleplayFacts"] if fact["kind"] == "falseCount"
    ]
    if len(roleplay_facts) != 1:
        raise LearningTaskGenerationError("M03 needs one fictional role-play count.")
    roleplay = roleplay_facts[0]
    if (
        roleplay["groupKey"] != first["key"]
        or roleplay["quantity"] in {group["quantity"] for group in groups.values()}
    ):
        raise LearningTaskGenerationError("The role-play count must be a fictional false count.")
    if questions[2].correct_text:
        raise LearningTaskGenerationError("A comparison selection must use multiple choice.")
    first_word = NUMBER_WORDS[payload["targetLanguage"]][first["quantity"]]
    if (
        next(
            option.label for option in questions[0].options
            if option.option_id == questions[0].correct_option_id
        ) != first_word
        or questions[1].correct_text != payload["facts"]["secondSentence"]
    ):
        raise LearningTaskGenerationError("M03 count answers must match the confirmed groups.")
    comparison = next(
        option.label for option in questions[2].options
        if option.option_id == questions[2].correct_option_id
    )
    if comparison != payload["facts"]["compareSentence"]:
        raise LearningTaskGenerationError("M03 Q3 comparison direction must match the counts.")
    if (
        not questions[3].roleplay_premise
        or fold(payload["facts"]["friendStatement"]) not in fold(questions[3].roleplay_premise)
    ):
        raise LearningTaskGenerationError("M03 Q4 must show the friend's role-play statement.")
    correct_roleplay = next(
        option.label for option in questions[3].options
        if option.option_id == questions[3].correct_option_id
    )
    if first_word not in correct_roleplay or roleplay["numberWord"] in correct_roleplay:
        raise LearningTaskGenerationError("M03 Q4 must correct the fictional count.")
    if roleplay["numberWord"] not in questions[3].prompt:
        raise LearningTaskGenerationError("M03 must present the fictional count as role-play.")
    if any(
        fold(roleplay["numberWord"]) in {fold(token) for token in tokens(text)}
        for index, question in enumerate(questions)
        if index != 3
        for text in (
            *_question_text(question),
            question.roleplay_premise or "",
        )
    ):
        raise LearningTaskGenerationError(
            "The fictional count must not appear outside its role-play statement."
        )
    if any(
        fold(roleplay["numberWord"]) in {fold(token) for token in tokens(text)}
        for text in (
            questions[3].correct_text or "",
            *(option.label for option in questions[3].options),
        )
    ):
        raise LearningTaskGenerationError("The fictional count must not appear in the answer.")
    if questions[4].correct_text != payload["facts"]["combined"]:
        raise LearningTaskGenerationError("M03 Q5 must report and compare both confirmed counts.")
    low, high = payload["quantityRange"]["min"], payload["quantityRange"]["max"]
    all_text = " ".join(
        text
        for question in questions
        for text in (
            *_question_text(question),
            *question.target_language_text,
            question.roleplay_premise or "",
        )
    )
    folded_text = fold(all_text).split()
    for quantity, number_word in NUMBER_WORDS[payload["targetLanguage"]].items():
        if not low <= quantity <= high and fold(number_word) in folded_text:
            raise LearningTaskGenerationError("M03 uses a number word outside the taught range.")


def _check_m04(payload, questions):
    facts = _approved(payload)
    owner_facts = [
        fact for fact in facts["approvedRoleplayFacts"] if fact.get("kind") == "ownership"
    ]
    for fact in owner_facts:
        if fact.get("isFictional") is not True or fact.get("source") != "assignedRoleplay":
            raise LearningTaskGenerationError("Ownership must remain fictional role-play.")
    if len(owner_facts) != 2 or len({fact["objectKey"] for fact in owner_facts}) != 2:
        raise LearningTaskGenerationError("M04 needs two distinct assigned role-play objects.")
    if questions[0].roleplay_premise is None or questions[3].roleplay_premise is None:
        raise LearningTaskGenerationError("M04 must show its role-play premise.")
    if not any(fact["owner"] in questions[0].roleplay_premise for fact in owner_facts):
        raise LearningTaskGenerationError("The role-play premise must name the assigned owner.")
    if questions[3].roleplay_premise != questions[0].roleplay_premise:
        raise LearningTaskGenerationError("M04 ownership questions must share their premise.")
    assigned = next(
        row for row in facts["approvedObjects"]
        if row["key"] == payload["selection"]["assignedObjectKey"]
    )
    alternative = next(
        row for row in facts["approvedObjects"]
        if row["key"] == payload["selection"]["alternativeObjectKey"]
    )
    if alternative["key"] not in questions[3].group_object_ids:
        raise LearningTaskGenerationError("M04 Q4 must highlight the alternative object.")
    correct_marker = questions[0].marker_object_ids.get(questions[0].correct_option_id)
    if correct_marker != assigned["key"]:
        raise LearningTaskGenerationError("M04 Q1 must select the learner-assigned object.")
    possessive_option = next(
        option.label for option in questions[1].options
        if option.option_id == questions[1].correct_option_id
    )
    if not validate_possessive(
        f"{possessive_option} {assigned['bareNoun']}",
        payload["targetLanguage"],
        assigned["gender"],
        noun=assigned["bareNoun"],
    ):
        raise LearningTaskGenerationError("M04 Q2 possessive must agree with its assigned noun.")
    expected_prefix = f"{possessive_option.capitalize()} {assigned['bareNoun']}".casefold()
    for question in (questions[2], questions[4]):
        if not (question.correct_text or "").casefold().startswith(expected_prefix):
            raise LearningTaskGenerationError(
                "M04 ownership answers must start with the agreed noun."
            )
    alternative_owner = next(
        fact["owner"] for fact in owner_facts if fact["objectKey"] == alternative["key"]
    )
    owner_answer = next(
        option.label for option in questions[3].options
        if option.option_id == questions[3].correct_option_id
    )
    if alternative_owner not in owner_answer:
        raise LearningTaskGenerationError("M04 Q4 must name the alternative object's owner.")


def _check_m01(payload, questions):
    facts = _approved(payload)
    language = payload["targetLanguage"]
    selection = payload["selection"]
    objects = {row["key"]: row for row in facts["approvedObjects"]}
    sentences = set()
    for obj in objects.values():
        article = {
            "es": {"masculine": "un", "feminine": "una"},
            "fr": {"masculine": "un", "feminine": "une"},
        }[language][obj["gender"]]
        prefix = "Hay" if language == "es" else "Il y a"
        also_prefix = "También hay" if language == "es" else "Il y a aussi"
        sentences.add(
            f"{prefix} {article} {obj['bareNoun']}."
        )
        sentences.add(f"{also_prefix} {article} {obj['bareNoun']}.")
        for approved_attribute in facts["approvedAttributes"]:
            if approved_attribute["objectKey"] != obj["key"]:
                continue
            noun = (
                f"{approved_attribute['form']} {obj['bareNoun']}"
                if approved_attribute["before"]
                else f"{obj['bareNoun']} {approved_attribute['form']}"
            )
            sentences.add(f"{prefix} {article} {noun}.")
            sentences.add(f"{also_prefix} {article} {noun}.")
    location_verb = "está" if language == "es" else "est"
    for relation in facts["approvedRelationships"]:
        sentences.add(
            f"{objects[relation['subjectKey']]['nounPhrase']} {location_verb} "
            f"{relation['phrase']}."
        )
    description = questions[3].correct_text or ""
    if selection["firstFactKind"] == "attribute":
        attribute = next(
            row for row in facts["approvedAttributes"]
            if row["key"] == selection["attributeKey"]
        )
        selected_object_key = attribute["objectKey"]
        selected_detail = attribute["form"]
        selected_object = objects[selected_object_key]
        selected_article = {
            "es": {"masculine": "un", "feminine": "una"},
            "fr": {"masculine": "un", "feminine": "une"},
        }[language][selected_object["gender"]]
        selected_noun = (
            f"{attribute['form']} {selected_object['bareNoun']}"
            if attribute["before"]
            else f"{selected_object['bareNoun']} {attribute['form']}"
        )
        selected_fact = (
            f"{'Hay' if language == 'es' else 'Il y a'} "
            f"{selected_article} {selected_noun}."
        )
        if fold(attribute["form"]) not in fold(description):
            raise LearningTaskGenerationError(
                "M01's follow-up must ask about an approved fact in the built description."
            )
    else:
        relation = next(
            row for row in facts["approvedRelationships"]
            if row["key"] == selection["relationKey"]
        )
        selected_object_key = relation["subjectKey"]
        selected_detail = relation["phrase"]
        selected_fact = (
            f"{objects[relation['subjectKey']]['nounPhrase']} "
            f"{'está' if language == 'es' else 'est'} {relation['phrase']}."
        )
    asked_fact = questions[4]
    correct_option = next(
        option for option in asked_fact.options if option.option_id == asked_fact.correct_option_id
    )
    if asked_fact.object_key != selected_object_key or fold(correct_option.label) != fold(
        selected_detail
    ):
        raise LearningTaskGenerationError(
            "M01's follow-up must ask about an approved fact in the built description."
        )
    if fold(questions[1].correct_text or "") not in {fold(sentence) for sentence in sentences}:
        raise LearningTaskGenerationError("M01 Q2 must build an approved fact sentence.")
    correct_description = next(
        option.label for option in questions[2].options
        if option.option_id == questions[2].correct_option_id
    )
    connectors = facts["approvedConnectors"]
    connected = {
        f"{left[:-1]} {connector} {right[0].lower()}{right[1:]}"
        for left in sentences
        for right in sentences
        if left != right
        for connector in connectors
    }
    if fold(correct_description) not in {fold(sentence) for sentence in connected}:
        raise LearningTaskGenerationError("M01 Q3 must connect approved fact sentences.")
    if any(
        fold(option.label) in {
            *(fold(sentence) for sentence in sentences),
            *(fold(sentence) for sentence in connected),
        }
        for option in questions[2].options
        if option.option_id != questions[2].correct_option_id
    ):
        raise LearningTaskGenerationError("M01 Q3 distractors must not be true fact sentences.")
    description_sentences = [
        f"{sentence.strip()}."
        for sentence in description.split(".")
        if sentence.strip()
    ]
    if not 2 <= len(description_sentences) <= 3:
        raise LearningTaskGenerationError("M01 Q4 must connect two or three approved facts.")
    if any(
        fold(sentence) not in {fold(fact_sentence) for fact_sentence in sentences}
        for sentence in description_sentences
    ):
        raise LearningTaskGenerationError("M01 Q4 contains a sentence outside the approved facts.")
    if fold(selected_fact) not in {fold(sentence) for sentence in description_sentences}:
        raise LearningTaskGenerationError("M01 Q4 must contain its follow-up fact.")


def validate_a2_lesson(payload: dict[str, Any], result: MissionA2Result) -> None:
    """Mission-specific contracts shared by the deterministic fallback builders."""
    mission_id = payload.get("missionId")
    expected = _EXPECTED.get(mission_id)
    questions = result.questions
    if expected is None or [question.purpose for question in questions] != expected:
        raise LearningTaskGenerationError("A2 questions must follow the mission's Q1–Q5 sequence.")
    unique_question_ids(questions)
    check_closed_facts(payload, result)
    for question in questions:
        if question.interaction_type == "sentenceBuilding":
            _check_sentence_chunks(question)
        elif question.distractor_chunks or question.answer_chunks:
            raise LearningTaskGenerationError(
                "Multiple-choice questions cannot contain token chunks."
            )
    if mission_id == "M01":
        if len(questions[3].planning_facts) < 2:
            raise LearningTaskGenerationError("M01 must expose the facts used in its description.")
        _check_m01(payload, questions)
    elif mission_id == "M02":
        _check_m02(payload, questions)
    elif mission_id == "M03":
        _check_m03(payload, questions)
    elif mission_id == "M04":
        _check_m04(payload, questions)


def _fallback(mission_id):
    def build(payload):
        from app.services.mission_lessons_a2 import build_a2_result

        result = build_a2_result(payload, mission_id)
        validate_a2_lesson(payload, result)
        return result

    return build


def _generation(mission_id):
    code = mission_id.lower()
    return MissionGeneration(
        prompt_version=f"learning-tasks.{code}-a2.v1",
        schema_version=f"learning-tasks-{code}-a2-result.v1",
        validator_version=f"learning-tasks-{code}-a2-validator.v1",
        system_prompt="Build a deterministic A2 scene-mission lesson from approved facts.",
        result_model=MissionA2Result,
        validate=validate_a2_lesson,
        fallback=_fallback(mission_id),
        json_schema_name=f"mission_lesson_{code}_a2_v1",
        uses_model=False,
    )


A2_GENERATIONS = {
    mission_id: _generation(mission_id) for mission_id in ("M01", "M02", "M03", "M04")
}
