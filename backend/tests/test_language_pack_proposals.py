"""Spanish-only proposal integration. Every provider response is mocked, never live."""

import json
from dataclasses import replace

import pytest
from test_language_pack_runtime import MockSpanishProvider, dispatch
from test_language_pack_runtime import runtime as runtime

from app.ai.cache.cache import ResultCache
from app.ai.contracts.text import TextModelConfig
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.language_packs.loader import load_pack
from app.language_packs.model_source import ModelSource
from app.language_packs.pipeline import generate_pilot
from app.language_packs.runtime import session_inputs
from app.repositories.postgres.workflow import _lesson_answer_is_correct, evaluate
from app.schemas.tasks import SubmitVocabularyReviewAttemptRequest


class MockOpenSpanishProvider(MockSpanishProvider):
    """Scripted language proposals and scripted review verdicts, not grammar evidence."""

    def __init__(self, rejected=None, rendered_only=False, invalid_binding=False):
        super().__init__()
        self.rejected = rejected
        self.rendered_only = rendered_only
        self.invalid_binding = invalid_binding

    def generate(self, request):
        response = super().generate(request)
        data = json.loads(request.user_content)
        if request.json_schema_name == "language_vocabulary_proposals":
            forms, distractors = [], []
            for term in data["session_vocabulary"]["terms"]:
                if term["provenance"] != "sessionTranslation":
                    continue
                proposed = dict(term["formsByKey"])
                if term["partOfSpeech"] == "noun":
                    article = "una" if term["agreement"] == "feminine" else "un"
                    proposed.update(indefinite=article + " " + term["targetText"],
                                    article_indefinite=article)
                    distractors.append(dict(
                        for_fact_id=term["factId"], meaning="slipper", text="zapatilla",
                        forms=[dict(key="bare", text="zapatilla")],
                    ))
                elif term["partOfSpeech"] == "adjective":
                    if term["sourceText"] == "tiny":
                        proposed.update(masculine="diminuto", feminine="diminuta")
                    for meaning, text in [("enormous", "enorme"), ("medium-sized", "mediano")]:
                        distractors.append(dict(
                            for_fact_id=(
                                "object:unknown" if self.invalid_binding else term["factId"]
                            ),
                            meaning=meaning, text=text,
                            forms=[dict(key="masculine", text=text),
                                   dict(key="feminine", text=text)],
                        ))
                forms.append(dict(term_id=term["termId"],
                                  forms=[dict(key=k, text=v) for k, v in proposed.items()],
                                  agreement=term["agreement"], position=term["position"]))
            return replace(response, output_text=json.dumps(dict(forms=forms,
                                                                  distractors=distractors)))
        if request.json_schema_name == "language_content_review":
            if self.rejected and (not self.rendered_only or data["rendered_task"]):
                verdict = json.loads(response.output_text)
                verdict[self.rejected] = False
                verdict["issues"] = ["Mock reviewer rejects uncertain or unsuitable content"]
                return replace(response, output_text=json.dumps(verdict))
        if request.json_schema_name == "language_pack_candidates_v1":
            value = json.loads(response.output_text)
            for candidate in value["candidates"]:
                if candidate["text"].startswith("Es "):
                    candidate["text"] = (
                        "Esto " + candidate["text"][:1].lower() + candidate["text"][1:]
                    )
            return replace(response, output_text=json.dumps(value, ensure_ascii=False))
        return response


def outside_reference_scene(runtime, monkeypatch):
    import app.language_packs.context as module
    from app.language_packs.loader import PackSet

    original = module.load_packs

    def without_dictionary(*args):
        pack = original(*args).get("es", "everyday")
        return PackSet((pack.model_copy(update={"lexical": {}}),))

    monkeypatch.setattr(module, "load_packs", without_dictionary)
    for obj in runtime[0]:
        obj.attributes = {"size": "tiny"}
    for attr in runtime[3].attributes:
        attr.key = attr.key.replace(":color", ":size")
        attr.source, attr.translation = "tiny", "diminuto"


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_new_words_and_required_forms_without_pack_dictionary(level, runtime, monkeypatch):
    outside_reference_scene(runtime, monkeypatch)
    provider = MockOpenSpanishProvider()
    (task,) = dispatch(level, runtime, provider)
    answers = task.answer_key.correct_option_ids
    assert evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=answers))
    assert all(_lesson_answer_is_correct(task, key, answer) for key, answer in answers.items())
    assert len(provider.proposal_requests) == 1
    assert len(provider.review_requests) == 2
    rendered = json.loads(provider.review_requests[-1].user_content)
    assert rendered["rendered_task"]["answerKey"]
    assert "evaluations" not in json.loads(provider.requests[0].user_content)
    if level == "A1":
        labels = {o.label.casefold() for o in task.public_content.questions[2].options}
        assert "diminuta" in labels and "enorme" in labels
        answer = answers["describe-object"]
        assert answer.startswith("Esto es ") and "diminuto" in answer
    if level == "A0":
        assert "zapatilla" in task.public_content.questions[2].token_bank
        facts = json.loads(provider.review_requests[0].user_content)["facts"]
        assert "slipper" not in json.dumps(facts)
    for question in task.public_content.questions:
        if question.interaction_type == "sentenceBuilding":
            assert question.sentence_join_modes


@pytest.mark.parametrize("criterion", [
    "grammatical", "meaning_matches", "level_register_ok", "unambiguous",
    "distractors_suitable", "distinct", "scene_claims_supported", "certain",
])
def test_reviewer_rejection_or_uncertainty_exhausts_bounded_repair(criterion, runtime):
    provider = MockOpenSpanishProvider(rejected=criterion)
    with pytest.raises(LearningTaskGenerationError, match=criterion):
        dispatch("A1", runtime, provider)
    assert len(provider.requests) == 3
    assert len(provider.review_requests) == 3


def test_assembled_ambiguous_mcq_rejected_even_after_sentence_review(runtime, monkeypatch):
    outside_reference_scene(runtime, monkeypatch)

    class MockAmbiguousProvider(MockOpenSpanishProvider):
        def generate(self, request):
            response = super().generate(request)
            data = json.loads(request.user_content)
            value = json.loads(response.output_text)
            if request.json_schema_name == "language_vocabulary_proposals":
                for alternative in value["distractors"]:
                    if alternative["meaning"] == "enormous":
                        # A synonym of the correct tiny detail is another valid answer.
                        alternative.update(meaning="minute", text="minúsculo",
                                           forms=[dict(key="masculine", text="minúsculo"),
                                                  dict(key="feminine", text="minúscula")])
            elif request.json_schema_name == "language_content_review" and data["rendered_task"]:
                question = data["rendered_task"]["publicContent"]["questions"][2]
                labels = {o["label"].casefold() for o in question["options"]}
                assert {"diminuta", "minúscula"} <= labels
                value.update(unambiguous=False, issues=["Two synonymous tiny answers"])
            return replace(response, output_text=json.dumps(value, ensure_ascii=False))

    provider = MockAmbiguousProvider()
    with pytest.raises(LearningTaskGenerationError, match="unambiguous"):
        dispatch("A1", runtime, provider)
    assert len(provider.review_requests) == 2
    assert json.loads(provider.review_requests[-1].user_content)["rendered_task"]


def test_new_realization_is_model_assessed_never_reported_as_reviewed(runtime, monkeypatch):
    from test_language_pack_runtime import PACK

    outside_reference_scene(runtime, monkeypatch)
    pack = load_pack(PACK).model_copy(update={"lexical": {}})
    facts, vocabulary = session_inputs(pack, *runtime, {})

    class MockRealizationProvider(MockOpenSpanishProvider):
        def generate(self, request):
            response = super().generate(request)
            if request.json_schema_name != "language_pack_candidates_v1":
                return response
            data, value = json.loads(request.user_content), json.loads(response.output_text)
            by_fact = {term["factId"]: term for term in data["candidate_vocabulary"]["terms"]}
            specs = {spec["spec_id"]: spec for spec in data["specs"]}
            for sentence in value["candidates"]:
                if sentence["slot_id"] == "describeObject":
                    spec = specs[sentence["spec_id"]]
                    term = by_fact[spec["bindings"]["attribute"]]
                    sentence["text"] = sentence["text"].replace("diminuto", "diminutito")
                    sentence["realizations"] = [dict(term_id=term["termId"], surface="diminutito")]
            return replace(response, output_text=json.dumps(value, ensure_ascii=False))

    provider = MockRealizationProvider()
    generated = generate_pilot(pack, "A1", facts, vocabulary,
                               ModelSource(provider, TextModelConfig(model_name="mock")),
                               preview=True)
    assert generated.assurance == "modelAssessed"
    description = next(item for item in generated.approved
                       if item.candidate.slot_id == "describeObject")
    assert description.provenance.review_status == "generated"
    assert description.deterministic_report.term_surfaces_are_reviewed is False
    assert "diminutito" in description.candidate.text
    from app.language_packs.schema import join_pack_chunks

    assert join_pack_chunks(description.candidate.chunks, "space") == description.candidate.text


def test_unknown_binding_rejected_before_sentence_generation(runtime):
    provider = MockOpenSpanishProvider(invalid_binding=True)
    with pytest.raises(LearningTaskGenerationError, match="confirmed"):
        dispatch("A1", runtime, provider)
    assert not provider.requests and not provider.review_requests


def test_proposal_and_review_versions_invalidate_sentence_cache(runtime, monkeypatch):
    import app.language_packs.proposals as module

    provider, cache = MockOpenSpanishProvider(), ResultCache()
    dispatch("A0", runtime, provider, cache=cache)
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 1
    monkeypatch.setattr(module, "PROPOSAL_VERSION", module.PROPOSAL_VERSION + ".changed")
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 2
    monkeypatch.setattr(module, "REVIEW_VERSION", module.REVIEW_VERSION + ".changed")
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 3


@pytest.mark.parametrize("invalid", ["unknown", "unbound", "fact-id"])
@pytest.mark.parametrize("recover", [True, False])
def test_realization_id_errors_use_bounded_repair_without_loosening_bindings(
    runtime, invalid, recover,
):
    class MockInvalidRealizationProvider(MockOpenSpanishProvider):
        def generate(self, request):
            response = super().generate(request)
            if request.json_schema_name != "language_pack_candidates_v1":
                return response
            data, value = json.loads(request.user_content), json.loads(response.output_text)
            if recover and len(self.requests) > 1:
                return response
            terms = data["candidate_vocabulary"]["terms"]
            spec = next(s for s in data["specs"] if s["slot_id"] == "describeObject")
            allowed = {entry["term_id"] for entry in spec["realization_terms"]}
            if invalid == "unknown":
                term_id = "invented-term-id"
            elif invalid == "fact-id":
                term_id = spec["bindings"]["attribute"]
            else:
                term_id = next(t["termId"] for t in terms if t["termId"] not in allowed)
            for candidate in value["candidates"]:
                if candidate["slot_id"] == "describeObject":
                    candidate["realizations"] = [dict(term_id=term_id, surface="rojo")]
            return replace(response, output_text=json.dumps(value, ensure_ascii=False))

    provider = MockInvalidRealizationProvider()
    if recover:
        (task,) = dispatch("A1", runtime, provider)
        answers = task.answer_key.correct_option_ids
        assert evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=answers))
        assert len(provider.requests) == 2
    else:
        with pytest.raises(LearningTaskGenerationError) as error:
            dispatch("A1", runtime, provider)
        assert "after 3 attempt" in str(error.value)
        assert "Invalid realization term_id=" in str(error.value)
        assert "describeObject/describeObject-answer" in str(error.value)
        assert len(provider.requests) == 3
    repair = json.loads(provider.requests[1].user_content)
    assert [spec["slot_id"] for spec in repair["specs"]] == ["describeObject"]
    reasons = repair["repair"]["describeObject/describeObject-answer"]
    assert any("Use only this spec's term IDs" in reason for reason in reasons)
