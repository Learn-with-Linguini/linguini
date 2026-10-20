"""Spanish-only M01 runtime integration. All provider responses are mocked, never live."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.cache.cache import ResultCache
from app.ai.cache.store import CacheScope
from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.features.learning_tasks.service import LearningTaskService
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.ai.observability import NoOpAITracer
from app.language_packs.generation import check_deterministic, derive_chunks
from app.language_packs.loader import load_pack
from app.language_packs.model_source import ModelSource
from app.language_packs.plan import bind_plan
from app.language_packs.runtime import session_inputs
from app.missions import get_mission
from app.repositories.postgres.workflow import (
    PostgresWorkflowRepository,
    _lesson_answer_is_correct,
    evaluate,
)
from app.schemas.tasks import SubmitVocabularyReviewAttemptRequest

PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


class MockSpanishProvider:
    """Deterministic provider double; its grammar is test data, not model evidence."""

    def __init__(self, corrupt=False):
        self.requests = []
        self.proposal_requests = []
        self.review_requests = []
        self.corrupt = corrupt

    def generate(self, request):
        if request.json_schema_name == "language_vocabulary_proposals":
            self.proposal_requests.append(request)
            # Scripted provider output supplies grammatical forms at runtime;
            # production packs deliberately contain no finite vocabulary tables.
            terms = json.loads(request.user_content)["session_vocabulary"]["terms"]
            forms, distractors = [], []
            adjective_forms = {
                "rojo": ("rojo", "roja"), "roja": ("rojo", "roja"),
                "blanco": ("blanco", "blanca"), "blanca": ("blanco", "blanca"),
            }
            for term in terms:
                proposed = dict(term["formsByKey"])
                if term["partOfSpeech"] == "noun":
                    article = "una" if term["agreement"] == "feminine" else "un"
                    proposed.update(indefinite=article + " " + term["targetText"],
                                    article_indefinite=article)
                elif term["partOfSpeech"] == "adjective":
                    masculine, feminine = adjective_forms.get(
                        term["targetText"], (term["targetText"], term["targetText"]),
                    )
                    proposed.update(masculine=masculine, feminine=feminine)
                    for meaning, native in (("black", "negro"), ("blue", "azul")):
                        if meaning == term["sourceText"]:
                            continue
                        distractors.append(dict(
                            for_fact_id=term["factId"], meaning=meaning, text=native,
                            forms=[dict(key="masculine", text=native), dict(
                                key="feminine", text="negra" if native == "negro" else native,
                            )],
                        ))
                forms.append(dict(
                    term_id=term["termId"],
                    forms=[dict(key=key, text=value) for key, value in proposed.items()],
                    agreement=term["agreement"], position=term["position"],
                ))
            return TextModelResponse(
                output_text=json.dumps({"forms": forms, "distractors": distractors}),
                model_name="mocked-Spanish-only", prompt_version=request.prompt_version,
            )
        if request.json_schema_name == "language_content_review":
            self.review_requests.append(request)
            return TextModelResponse(
                output_text=json.dumps(dict(
                    meaning_matches=True, grammatical=True, level_register_ok=True,
                    distractors_suitable=True, distinct=True, unambiguous=True,
                    scene_claims_supported=True, certain=True, issues=[],
                )), model_name="mocked-Spanish-only", prompt_version=request.prompt_version,
            )
        self.requests.append(request)
        data = json.loads(request.user_content)
        vocabulary = data.get("candidate_vocabulary", data.get("approved_vocabulary"))
        terms = {term["factId"]: term for term in vocabulary["terms"]}
        terms_by_id = {term["termId"]: term for term in terms.values()}
        candidates = []
        for spec in data["specs"]:
            bindings = dict(spec["bindings"])
            for role, tid in spec["counterfactual"].items():
                bindings[role] = terms_by_id[tid]["factId"]
            obj = terms.get(bindings.get("object") or bindings.get("subject"))
            noun = obj["targetText"] if obj else ""
            forms = obj["formsByKey"] if obj else {}
            phrase = forms.get("indefinite", "")
            attr = terms.get(bindings.get("attribute"))
            detail = attr["formsByKey"].get(obj["agreement"], attr["targetText"]) if attr else ""
            existence = f"Hay {phrase}{' ' + detail if detail else ''}."
            construction = spec["construction_id"]
            if construction == "identify-object":
                text = forms["definite"] if spec["use"] == "name" else f"Es {phrase}."
            elif construction == "yes-no-identification":
                text = (
                    f"¿Es {phrase}?"
                    if spec["use"] in {"question", "prompt"}
                    else f"{'Sí' if spec['truth'] else 'No'}, es {phrase}."
                )
            elif construction == "describe-attribute":
                text = (
                    f"¿De qué color es {forms['definite']}?"
                    if spec["use"] == "followup"
                    else f"Es {phrase} {detail}."
                )
            elif construction == "scene-existence":
                text = existence
                if spec["use"] == "fact3":
                    text = "También " + text[:1].lower() + text[1:]
            elif construction == "scene-location":
                relation = terms[bindings["relation"]]["targetText"]
                reference = terms[bindings["reference"]]["formsByKey"]["definite"]
                text = f"{forms['definite'].capitalize()} está {relation} {reference}."
            elif construction == "connected-description":
                other = terms[bindings["other-object"]]["formsByKey"]["indefinite"]
                text = (
                    existence[:-1]
                    + f" y {'no' if spec['use'] == 'wrongExistence' else 'también'} hay {other}."
                )
            else:
                raise AssertionError(construction)
            if self.corrupt and spec["slot_id"] == "buildIdentify-1":
                text = "Es un libro."
            candidates.append(
                dict(
                    slot_id=spec["slot_id"],
                    spec_id=spec["spec_id"],
                    text=text,
                    translation=f"Mock meaning: {noun}",
                )
            )
        return TextModelResponse(
            output_text=json.dumps({"candidates": candidates}, ensure_ascii=False),
            model_name="mocked-Spanish-only",
            prompt_version=request.prompt_version,
        )


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("LINGUINI_M01_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(PACK))
    objects, words, translated, attrs = [], [], [], []
    for index, (source, native, article, gender, colour, target) in enumerate(
        (
            ("cup", "taza", "la", "feminine", "red", "rojo"),
            ("book", "libro", "el", "masculine", "green", "verde"),
            ("table", "mesa", "la", "feminine", "white", "blanco"),
        ),
        1,
    ):
        oid = UUID(int=index)
        objects.append(SimpleNamespace(id=oid, label=source, attributes={"color": colour}))
        words.append(SimpleNamespace(id=UUID(int=index + 10), display_text=native, gender=gender))
        translated.append(
            SimpleNamespace(
                key=str(oid), source=source, translation=native, article=article, gender=gender
            )
        )
        attrs.append(SimpleNamespace(key=f"{oid}:color", source=colour, translation=target))
    relation = SimpleNamespace(
        id=UUID(int=30),
        subject_scene_object_id=objects[0].id,
        reference_scene_object_id=objects[2].id,
        relation="on",
    )
    translation = SimpleNamespace(
        objects=translated,
        attributes=attrs,
        relationships=[SimpleNamespace(key=str(relation.id), source="on", translation="sobre")],
    )
    return objects, [relation], words, translation


def service(provider, cache=None):
    return LearningTaskService(
        provider,
        TextModelConfig(model_name="mocked-Spanish-only"),
        tracer=NoOpAITracer(),
        provider="mock",
        cache=cache,
    )


def dispatch(level, runtime, provider, *, cache=None, sid=100):
    from app.language_packs.context import resolve_language_context

    try:
        context = resolve_language_context("es")
    except ValueError as exc:
        raise LearningTaskGenerationError(str(exc)) from exc
    objects, relations, words, translated = runtime
    claim = SimpleNamespace(
        profile={"target_language_code": "es"},
        session_id=UUID(int=sid),
        missions=[get_mission("M01", level, 1)],
        counted_groups=[],
        mission_progress={},
        review_markers={},
        roleplay_facts={},
        learner_facts={},
        cache_scope=CacheScope.user("mock-user"),
        language_context=context,
    )
    repo = SimpleNamespace(learning_task_generator=service(provider, cache))
    return PostgresWorkflowRepository._mission_lessons(
        repo, claim, objects, relations, words, translated, []
    )


@pytest.mark.parametrize("level,count", [("A0", 6), ("A1", 4), ("A2", 5)])
def test_normal_dispatch_flag_on_spanish_mocked(level, count, runtime):
    assert load_pack(PACK).lexical == {}
    provider = MockSpanishProvider()
    (task,) = dispatch(level, runtime, provider)
    assert task.session_id == UUID(int=100)
    assert len(task.public_content.questions) == count
    assert len(provider.requests) == 1
    data = json.loads(provider.requests[0].user_content)
    assert data["register"]["registerId"] == "everyday"
    assert all(spec["bindings"] for spec in data["specs"])
    assert all(entry["constructions"][0]["guidance"] for entry in data["guidance"])
    assert "evaluations" not in data and "acceptable" not in data
    answers = task.answer_key.correct_option_ids
    assert all(
        _lesson_answer_is_correct(task, q.question_id, answers[q.question_id])
        for q in task.public_content.questions
    )
    assert evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=answers))
    wrong = {
        q.question_id: next(
            (o.option_id for o in q.options if o.option_id != answers[q.question_id]), "incorrect"
        )
        for q in task.public_content.questions
    }
    assert not evaluate(task, SubmitVocabularyReviewAttemptRequest(answers=wrong))
    for question in task.public_content.questions:
        if question.interaction_type == "sentenceBuilding":
            assert question.sentence_join_modes
    if level == "A0":
        assert len(task.public_content.prep) == 5
    if level == "A2":
        assert task.public_content.check_each_question
        assert len(task.public_content.questions[3].planning_facts) == 3


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_flag_off_uses_unchanged_legacy_dispatch(level, runtime, monkeypatch):
    monkeypatch.delenv("LINGUINI_M01_LANGUAGE_PACKS")
    provider = MockSpanishProvider()
    (task,) = dispatch(level, runtime, provider)
    assert task.public_content.practice_level == level
    assert not provider.requests
    assert all(q.sentence_join_modes is None for q in task.public_content.questions)


def test_release_gate_is_not_bypassed_by_feature_flag(runtime, monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "false")
    provider = MockSpanishProvider()
    with pytest.raises(LearningTaskGenerationError, match="human review"):
        dispatch("A0", runtime, provider)
    assert not provider.requests
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(LearningTaskGenerationError, match="human review"):
        dispatch("A0", runtime, provider)


def test_exhausted_repairs_recoverable_and_no_fallback(runtime):
    provider = MockSpanishProvider(corrupt=True)
    with pytest.raises(LearningTaskGenerationError, match="after 3 attempt"):
        dispatch("A0", runtime, provider)
    assert len(provider.requests) == 3
    assert len(json.loads(provider.requests[-1].user_content)["specs"]) == 1


def _same_colour_scene(runtime):
    objects, _relations, _words, translated = runtime
    for obj in objects:
        obj.attributes = {"color": "red"}
    for attribute in translated.attributes:
        attribute.source = "red"
        attribute.translation = "rojo"


def test_a1_same_colour_scene_uses_model_mcq_contrasts_mocked(runtime):
    _same_colour_scene(runtime)
    provider = MockSpanishProvider()
    (task,) = dispatch("A1", runtime, provider)
    assert len(provider.requests) == 1
    assert len(task.public_content.questions) == 4
    question = task.public_content.questions[2]
    assert question.interaction_type == "multipleChoice"
    assert len(question.options) >= 2
    labels = {option.label.casefold() for option in question.options}
    assert "roja" in labels
    assert len(labels) == len(question.options)
    expected = task.answer_key.correct_option_ids[question.question_id]
    for option in question.options:
        assert _lesson_answer_is_correct(task, question.question_id, option.option_id) is (
            option.option_id == expected
        )


def test_a1_missing_contrast_fails_before_sentence_generation(runtime):
    _same_colour_scene(runtime)

    class MissingContrastProvider(MockSpanishProvider):
        def generate(self, request):
            from dataclasses import replace

            response = super().generate(request)
            if request.json_schema_name == "language_vocabulary_proposals":
                body = json.loads(response.output_text)
                body["distractors"] = []
                return replace(response, output_text=json.dumps(body))
            return response

    provider = MissingContrastProvider()
    with pytest.raises(LearningTaskGenerationError, match="colour:red"):
        dispatch("A1", runtime, provider)
    assert provider.requests == []
    assert len(provider.proposal_requests) == 1


@pytest.mark.parametrize("recover", [True, False])
def test_a1_article_failure_repair_has_sentence_and_expected_phrase(runtime, recover):
    class MockArticleProvider(MockSpanishProvider):
        def generate(self, request):
            result = super().generate(request)
            if request.json_schema_name != "language_pack_candidates_v1":
                if request.json_schema_name == "language_content_review":
                    from dataclasses import replace

                    data = json.loads(request.user_content)
                    bad = any("¿Es un taza?" == c["text"] or "¿Es una libro?" == c["text"]
                              for c in data["candidates"])
                    if bad:
                        review = json.loads(result.output_text)
                        review.update(grammatical=False, issues=["Expected approved noun phrase"])
                        return replace(result, output_text=json.dumps(review))
                return result
            if recover and len(self.requests) > 1:
                return result
            payload = json.loads(result.output_text)
            for candidate in payload["candidates"]:
                if candidate["spec_id"] == "confirmObject-2-prompt":
                    # Always invert the approved article in this mocked question.
                    candidate["text"] = candidate["text"].replace(" una ", " WRONG ")
                    candidate["text"] = candidate["text"].replace(" un ", " una ")
                    candidate["text"] = candidate["text"].replace(" WRONG ", " un ")
            from dataclasses import replace

            return replace(result, output_text=json.dumps(payload, ensure_ascii=False))

    provider = MockArticleProvider()
    if recover:
        (task,) = dispatch("A1", runtime, provider)
        assert len(task.public_content.questions) == 4
        assert len(provider.requests) == 2
    else:
        with pytest.raises(LearningTaskGenerationError) as error:
            dispatch("A1", runtime, provider)
        assert "after 3 attempt" in str(error.value)
        assert "Rejected sentence:" in str(error.value)
        assert "Expected approved noun phrase" in str(error.value)
        assert len(provider.requests) == 3
    repair = json.loads(provider.requests[1].user_content)
    reasons = repair["repair"]["confirmObject-2/confirmObject-2-prompt"]
    assert reasons[0].startswith("Previous rejected sentence:")
    assert any("Expected approved noun phrase" in reason for reason in reasons)
    assert "confirmObject-2-prompt" in [spec["spec_id"] for spec in repair["specs"]]


@pytest.mark.parametrize(
    "text,passes",
    [("¿Es una taza?", True), ("¿Es UNA TAZA?", True),
     ("¿Es una  taza?", True), ("¿Es un taza?", False), ("¿Es una tazadora?", False)],
)
def test_spanish_noun_phrase_matching_case_spacing_and_boundaries(text, passes):
    from app.language_packs.generation import (
        ApprovedTerm,
        ApprovedVocabulary,
        CandidateSentence,
        TermUse,
    )
    from app.language_packs.validators import select_validator

    vocabulary = ApprovedVocabulary(terms=[ApprovedTerm(
        term_id="cup", fact_id="object:cup", source_text="cup", target_text="Taza",
        forms=["Taza", "una"], forms_by_key={"bare": "Taza", "article_indefinite": "una"},
        part_of_speech="noun", agreement="feminine", provenance="sessionTranslation",
    )])
    candidate = CandidateSentence(
        slot_id="confirmObject-2", spec_use="prompt", construction_id="yes-no-identification",
        text=text, origin="model",
        term_uses=[TermUse(term_id="cup", fact_id="object:cup", surface="Taza", role="object")],
    )
    pack = load_pack(PACK)
    # Article agreement now comes from the shared noun-phrase validator.
    result = select_validator("es", vocabulary, pack).validate(candidate, pack)
    assert result.passed is passes
    if not passes:
        assert any(
            "own indefinite articles with 'Taza'" in message and ": una." in message
            for message in result.messages
        )


def test_binding_and_chunks_rejected_before_assembly(runtime):
    pack = load_pack(PACK)
    facts, vocabulary = session_inputs(pack, *runtime, {})
    source = ModelSource(MockSpanishProvider(), TextModelConfig(model_name="mocked-Spanish-only"))
    vocabulary = source.prepare(pack, "A1", facts, vocabulary)
    plan = bind_plan(pack, "A1", facts, vocabulary)
    from app.language_packs.loader import guidance_for

    candidate = source.generate(
        plan, facts, vocabulary, guidance_for(pack, plan.required_constructions), pack
    )[-1]
    wrong = candidate.model_copy(update={"text": "Es una taza roja."})
    assert not check_deterministic(wrong, plan, facts, vocabulary, pack).passed
    invalid_chunks = candidate.model_copy(update={"chunks": [dict(text="invalid", join="none")]})
    from app.language_packs.schema import SentenceChunk

    invalid_chunks = invalid_chunks.model_copy(
        update={"chunks": [SentenceChunk(text="invalid", join="none")]}
    )
    assert not check_deterministic(invalid_chunks, plan, facts, vocabulary, pack).passed
    derived = derive_chunks(candidate, pack.language.word_separator)
    from app.language_packs.schema import join_pack_chunks

    assert join_pack_chunks(derived.chunks, pack.language.word_separator) == candidate.text


def test_runtime_cache_invalidation(runtime):
    provider = MockSpanishProvider()
    cache = ResultCache()
    (first,) = dispatch("A0", runtime, provider, cache=cache)
    (second,) = dispatch("A0", runtime, provider, cache=cache)
    assert first.public_content == second.public_content
    assert first.answer_key == second.answer_key
    assert len(provider.requests) == 1
    objects, relations, words, translation = runtime
    translation.objects[0].translation = "tacita"
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 2


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_flag_on_preserves_mission_completion_evidence(level, runtime):
    from app.services.question_outcomes import review_details

    (task,) = dispatch(level, runtime, MockSpanishProvider())
    answers = task.answer_key.correct_option_ids
    details = review_details(
        task,
        SubmitVocabularyReviewAttemptRequest(answers=answers),
        {key: True for key in answers},
        answers,
    )
    # The unchanged outcome evaluator decides mission completion from the pack task.
    assert details
    assert all(outcome["outcome"] == "correct" for outcome in details["questionOutcomes"])


def test_duplicate_object_names_keep_instance_bindings(runtime):
    objects, relations, words, translation = runtime
    objects[1].label = objects[0].label
    words[1].display_text = words[0].display_text
    words[1].gender = words[0].gender
    translation.objects[1].translation = translation.objects[0].translation
    translation.objects[1].article = translation.objects[0].article
    translation.objects[1].gender = translation.objects[0].gender
    (task,) = dispatch("A1", runtime, MockSpanishProvider())
    assert [q.scene_object_id for q in task.public_content.questions] == [
        objects[0].id,
        objects[1].id,
        objects[0].id,
        objects[1].id,
    ]
    assert task.answer_key.question_evaluations[0].vocabulary_item_ids == [words[0].id]
    assert task.answer_key.question_evaluations[1].vocabulary_item_ids == [words[1].id]


def test_incorrect_attribute_instance_and_claim_are_rejected(runtime):
    pack = load_pack(PACK)
    facts, vocabulary = session_inputs(pack, *runtime, {})
    source = ModelSource(MockSpanishProvider(), TextModelConfig(model_name="mocked-Spanish-only"))
    vocabulary = source.prepare(pack, "A1", facts, vocabulary)
    plan = bind_plan(pack, "A1", facts, vocabulary)
    from app.language_packs.loader import guidance_for

    candidate = source.generate(
        plan, facts, vocabulary, guidance_for(pack, plan.required_constructions), pack
    )[-1]
    slot = plan.slots[-1]
    wrong = slot.specs[0].model_copy(
        update={
            "bindings": {
                **slot.specs[0].bindings,
                "attribute": facts.scene_facts.attributes[0].fact_id,
            }
        }
    )
    wrong_plan = plan.model_copy(
        update={"slots": [*plan.slots[:-1], slot.model_copy(update={"specs": [wrong]})]}
    )
    report = check_deterministic(candidate, wrong_plan, facts, vocabulary, pack)
    assert "attribute binding belongs to another object instance" in report.failures


class MockRomanizedSpanishProvider(MockSpanishProvider):
    def generate(self, request):
        import re
        from dataclasses import replace

        response = super().generate(request)
        if request.json_schema_name != "language_pack_candidates_v1":
            return response
        value = json.loads(response.output_text)
        for sentence in value["candidates"]:
            sentence["romanization"] = [
                dict(native=match.group(), latin=match.group())
                for match in re.finditer(r"\s*\S+", sentence["text"])
            ]
        data = json.loads(request.user_content)
        texts = set()
        vocabulary = data.get("candidate_vocabulary", data.get("approved_vocabulary"))
        for term in vocabulary["terms"]:
            texts.update(term["forms"])
        for entry in data["guidance"]:
            texts.update(label["text"] for label in entry["labels"])
        value["support_romanizations"] = [dict(native=text, latin=text) for text in texts]
        return replace(response, output_text=json.dumps(value, ensure_ascii=False))


def test_required_aligned_romanization_uses_generated_spanish_sentences(runtime, monkeypatch):
    import app.language_packs.context as module
    from app.language_packs.loader import PackSet

    original = module.load_packs

    def required(*args):
        pack = original(*args).get("es", "everyday")
        return PackSet((pack.model_copy(
            update={"language": pack.language.model_copy(update={"romanization_required": True})}
        ),))

    monkeypatch.setattr(module, "load_packs", required)
    (task,) = dispatch("A0", runtime, MockRomanizedSpanishProvider())
    for question in task.public_content.questions:
        assert question.prompt in question.romanizations
    assert all(card.romanization for card in task.public_content.prep)
    answer = task.answer_key.correct_option_ids["buildIdentify-1"]
    assert _lesson_answer_is_correct(task, "buildIdentify-1", answer)
    # New unseen sentences must have aligned spelling; no finite example lookup.
    runtime[3].objects[0].translation = "tacita"
    (task,) = dispatch("A0", runtime, MockRomanizedSpanishProvider())
    assert "tacita" in task.answer_key.correct_option_ids["buildIdentify-1"]
    assert "tacita." in task.public_content.questions[2].romanizations
    with pytest.raises(LearningTaskGenerationError, match="romanization"):
        dispatch("A0", runtime, MockSpanishProvider())


def test_generator_validator_and_pack_versions_invalidate_runtime_cache(runtime, monkeypatch):
    import app.language_packs.context as module
    from app.language_packs.loader import PackSet
    from app.language_packs.validators.es import SpanishM01Validator

    provider = MockSpanishProvider()
    cache = ResultCache()
    dispatch("A0", runtime, provider, cache=cache)
    monkeypatch.setattr(ModelSource, "source_id", ModelSource.source_id + ".test-change")
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 2
    monkeypatch.setattr(SpanishM01Validator, "validator_id", "es-targeted-test-version")
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 3
    original = module.load_packs

    def changed(*args):
        pack = original(*args).get("es", "everyday")
        return PackSet((pack.model_copy(update={"pack_version": pack.pack_version + 1}),))

    monkeypatch.setattr(module, "load_packs", changed)
    dispatch("A0", runtime, provider, cache=cache)
    assert len(provider.requests) == 4


def test_spanish_a1_option_order_is_session_seeded(runtime):
    ids = set()
    for session in (100, 101, 102, 103):
        task, = dispatch("A1", runtime, MockSpanishProvider(), sid=session)
        ids.add(task.answer_key.correct_option_ids["confirm-first"])
    assert ids == {"confirm-1", "confirm-2"}
