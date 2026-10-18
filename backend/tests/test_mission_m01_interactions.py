"""Interaction-aware multilingual M01 validation; lesson text is placeholder content."""

import pytest
from test_mission_m01_contract import (
    contract_input,
    planned_a0_output,
    planned_a1_output,
    planned_a2_output,
)
from test_mission_m01_matrix import synthetic_registry as synthetic_registry

from app.missions.m01_multilingual import (
    MissionContractError,
    _inflects,
    validate_contract_output,
)
from app.schemas.mission_m01_contract import Answer, TermUse


def _question(output, question_id):
    return next(item for item in output.questions if item.question_id == question_id)


def _replace(output, question_id, **update):
    return output.model_copy(update={"questions": [
        item.model_copy(update=update) if item.question_id == question_id else item
        for item in output.questions
    ]})


def _answer(output, question_id, **answer):
    answers = {**output.private.answers, question_id: Answer(**answer)}
    return output.model_copy(update={
        "private": output.private.model_copy(update={"answers": answers}),
    })


def _chunk_text(output, question_id, chunk_id, text, term_uses=()):
    question = _question(output, question_id)
    return _replace(output, question_id, chunks=[
        chunk.model_copy(update={"text": text, "term_uses": list(term_uses)})
        if chunk.chunk_id == chunk_id else chunk
        for chunk in question.chunks
    ])


def _rejects(contract, output, plan, pattern):
    with pytest.raises(MissionContractError, match=pattern):
        validate_contract_output(contract, output, plan)


def _objects(contract):
    return contract.scene_facts.objects


# markerChoice


def test_marker_choice_accepts_numeric_labels_without_a_noun():
    contract, output, plan = planned_a0_output()
    question = _question(output, "match-0")
    output = _replace(output, "match-0", options=[
        option.model_copy(update={"label": str(index)})
        for index, option in enumerate(question.options, start=1)
    ])
    validate_contract_output(contract, output, plan)


def test_marker_choice_rejects_a_marker_for_another_object():
    contract, output, plan = planned_a0_output()
    _rejects(
        contract, _answer(output, "match-0", correct_option_id="marker-0-1"), plan,
        r"question 1 \(match-0, slot matchName\): correct marker object object:\S+ "
        r"must be in the question facts",
    )
    table = _objects(contract)[1].fact_id
    moved = _answer(
        _replace(output, "match-0", fact_ids=[table]), "match-0",
        correct_option_id="marker-0-1",
    )
    _rejects(
        contract, moved, plan,
        r"question 2 \(confirm-0, slot confirmName\): questions with the same focus "
        r"must share one object fact",
    )


# yes/no


def test_yes_no_accepts_true_and_false_statements():
    contract, output, plan = planned_a0_output()
    validate_contract_output(contract, output, plan)
    cup, table = (item.fact_id for item in _objects(contract)[:2])
    false_statement = _answer(
        _replace(
            output, "confirm-0", prompt="Is this mesa?", statement_fact_id=table,
            fact_ids=[cup, table],
        ),
        "confirm-0", correct_option_id="no-0",
    )
    validate_contract_output(contract, false_statement, plan)


def test_yes_no_answer_must_match_the_statement_truth():
    contract, output, plan = planned_a0_output()
    cup, table = (item.fact_id for item in _objects(contract)[:2])
    _rejects(
        contract, _answer(output, "confirm-0", correct_option_id="no-0"), plan,
        r"question 2 \(confirm-0, slot confirmName\): correct option no-0 means 'no', "
        r"expected 'yes' because the statement names the focus object",
    )
    false_statement = _replace(
        output, "confirm-0", prompt="Is this mesa?", statement_fact_id=table,
        fact_ids=[cup, table],
    )
    _rejects(
        contract, false_statement, plan,
        r"question 2 \(confirm-0, slot confirmName\): correct option yes-0 means 'yes', "
        rf"expected 'no' because the statement names {table}, not the focus object {cup}",
    )


def test_yes_no_requires_a_named_statement_and_yes_no_options():
    contract, output, plan = planned_a0_output()
    table = _objects(contract)[1].fact_id
    _rejects(
        contract, _replace(output, "confirm-0", statement_fact_id=None), plan,
        r"question 2 \(confirm-0, slot confirmName\): yes/no questions must name the "
        "stated object in statementFactId",
    )
    _rejects(
        contract, _replace(output, "confirm-0", prompt="Is this it?"), plan,
        r"question 2 \(confirm-0, slot confirmName\): prompt 'Is this it\?' does not "
        r"realise the stated object object:\S+: expected approved term 'taza'",
    )
    _rejects(
        contract, _replace(output, "confirm-0", statement_fact_id=table), plan,
        rf"question 2 \(confirm-0, slot confirmName\): statementFactId {table} must be "
        "listed in factIds",
    )
    options = _question(output, "confirm-0").options
    _rejects(
        contract,
        _replace(output, "confirm-0", options=[
            option.model_copy(update={"meaning": "yes"}) for option in options
        ]),
        plan,
        r"question 2 \(confirm-0, slot confirmName\): yes/no options must be one 'yes' "
        r"and one 'no', got meanings \['yes', 'yes'\]",
    )
    marker_options = _question(output, "match-0").options
    _rejects(
        contract,
        _replace(output, "match-0", options=[
            marker_options[0].model_copy(update={"meaning": "yes"}), *marker_options[1:],
        ]),
        plan,
        r"question 1 \(match-0, slot matchName\): only yes/no options carry a yes/no meaning",
    )


def test_yes_no_highlights_the_first_listed_object():
    contract, output, plan = planned_a0_output()
    cup, table = (item.fact_id for item in _objects(contract)[:2])
    _rejects(
        contract, _replace(output, "confirm-0", fact_ids=[table, cup]), plan,
        r"question 2 \(confirm-0, slot confirmName\): questions with the same focus",
    )


def test_a1_confirm_object_accepts_a_statement_about_the_other_object():
    contract, output, plan = planned_a1_output()
    question = _question(output, "confirm-second")
    assert question.statement_fact_id != question.fact_ids[0]
    validate_contract_output(contract, output, plan)
    _rejects(
        contract, _answer(output, "confirm-second", correct_option_id="yes-second"), plan,
        r"question 2 \(confirm-second, slot confirmObject\): correct option yes-second "
        r"means 'yes', expected 'no'",
    )


# sentenceBuilding


def test_identify_answer_must_realise_the_focus_object():
    contract, output, plan = planned_a0_output()
    _rejects(
        contract, _chunk_text(output, "build-0", "build-0-name", "cosa"), plan,
        r"question 3 \(build-0, slot buildIdentify\): correct answer 'This is cosa\.' "
        r"does not realise the focus object object:\S+: expected approved term 'taza'",
    )


def test_connected_description_does_not_require_incidental_objects():
    contract, output, plan = planned_a2_output()
    validate_contract_output(
        contract,
        _chunk_text(output, "scene-description-build", "connect-table", "it"),
        plan,
    )


def test_connected_description_requires_its_detail_terms():
    contract, output, plan = planned_a2_output()
    _rejects(
        contract,
        _chunk_text(output, "scene-description-build", "connect-on", "near"),
        plan,
        r"question 4 \(scene-description-build, slot buildSceneDescription\): correct "
        r"answer '.*' does not realise the detail fact relation:\S+: expected approved "
        "term 'on'",
    )


def test_describe_object_requires_the_focus_colour():
    contract, output, plan = planned_a1_output()
    _rejects(
        contract, _chunk_text(output, "describe-second", "describe-grande", "big"), plan,
        r"question 4 \(describe-second, slot describeObject\): correct answer "
        r"'La mesa is big\.' does not realise the focus object's colour",
    )


# choice questions about a detail


def test_choose_attribute_answer_must_be_the_focus_colour():
    contract, output, plan = planned_a1_output()
    _rejects(
        contract, _answer(output, "choose-attribute", correct_option_id="red"), plan,
        r"question 3 \(choose-attribute, slot chooseAttribute\): correct answer 'red' "
        r"does not realise the focus object's colour attribute:\S+: expected approved "
        "term 'blue'",
    )


def test_follow_up_answer_must_name_a_listed_detail():
    contract, output, plan = planned_a2_output()
    _rejects(
        contract, _answer(output, "scene-follow-up", correct_option_id="detail-red"), plan,
        r"question 5 \(scene-follow-up, slot followUpSceneFact\): correct answer "
        r"'other-colour' realises none of the listed detail facts",
    )


def test_scene_description_choice_does_not_require_incidental_objects():
    contract, output, plan = planned_a2_output()
    question = _question(output, "scene-description-choice")
    output = _replace(output, "scene-description-choice", options=[
        option.model_copy(update={"label": "There is taza blue."})
        if option.option_id == "description-correct" else option
        for option in question.options
    ])
    validate_contract_output(contract, output, plan)


# declared surface forms in an agglutinative synthetic language


def _agglutinative_a0():
    contract = contract_input(level="A0", language="es")
    words = {"cup": "kalam", "table": "pusu", "chair": "veedu"}
    contract = contract.model_copy(update={
        "target_language": "qaa",
        "vocabulary": [
            term.model_copy(update={"target_text": words[term.term_id], "linguistic": {}})
            for term in contract.vocabulary
        ],
    })
    return planned_a0_output(contract)


def test_declared_inflected_surface_realises_the_approved_term(synthetic_registry):
    contract, output, plan = _agglutinative_a0()
    inflected = _chunk_text(
        output, "build-0", "build-0-name", "kalattil",
        [TermUse(term_id="cup", surface="kalattil")],
    )
    validate_contract_output(contract, inflected, plan)
    prompt = _replace(
        output, "confirm-0", prompt="kalatha?",
        prompt_term_uses=[TermUse(term_id="cup", surface="kalatha")],
    )
    validate_contract_output(contract, prompt, plan)


def test_undeclared_or_unrelated_surface_forms_are_rejected(synthetic_registry):
    contract, output, plan = _agglutinative_a0()
    _rejects(
        contract, _chunk_text(output, "build-0", "build-0-name", "kalattil"), plan,
        r"question 3 \(build-0, slot buildIdentify\): correct answer .* does not realise "
        "the focus object",
    )
    _rejects(
        contract,
        _chunk_text(
            output, "build-0", "build-0-name", "veettil",
            [TermUse(term_id="cup", surface="veettil")],
        ),
        plan,
        r"question 3 \(build-0, slot buildIdentify\): chunk build-0-name surface "
        r"'veettil' is not a recognised form of approved term 'kalam' \(cup\)",
    )
    _rejects(
        contract,
        _chunk_text(
            output, "build-0", "build-0-name", "pusuvil",
            [TermUse(term_id="table", surface="pusuvil")],
        ),
        plan,
        r"question 3 \(build-0, slot buildIdentify\): correct answer .* does not realise "
        "the focus object",
    )
    _rejects(
        contract,
        _chunk_text(
            output, "build-0", "build-0-name", "kalattil",
            [TermUse(term_id="cup", surface="kalathil")],
        ),
        plan,
        r"question 3 \(build-0, slot buildIdentify\): chunk build-0-name declares "
        r"surface 'kalathil' for 'cup', but its text is 'kalattil'",
    )
    _rejects(
        contract,
        _chunk_text(
            output, "build-0", "build-0-name", "kalattil",
            [TermUse(term_id="unknown", surface="kalattil")],
        ),
        plan,
        r"question 3 \(build-0, slot buildIdentify\): chunk build-0-name declares "
        "unknown term 'unknown'",
    )


@pytest.mark.parametrize(("term", "surface", "expected"), [
    ("kalam", "kalattil", True),
    ("kalam", "kalatha", True),
    ("rojo", "roja", True),
    ("taza", "tazas", True),
    ("al lado de", "al lado del", True),
    ("cat", "car", False),
    ("mesa", "mano", False),
    ("kalam", "kal", False),
    ("kalam", "veettil", False),
    ("al lado de", "junto a", False),
])
def test_declared_inflection_check_is_conservative(term, surface, expected):
    assert _inflects(term, surface) is expected


def test_preparation_count_error_explains_the_plan():
    contract, output, plan = planned_a0_output()
    expected = len(contract.scene_facts.objects) + 2
    _rejects(
        contract, output.model_copy(update={"preparation": output.preparation[:-1]}), plan,
        rf"preparation-card count {expected - 1} is outside {expected}–{expected} "
        rf"\(one per confirmed object \({expected - 2}\) plus 2 extra\)",
    )
