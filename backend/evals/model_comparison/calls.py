"""One runner per AI call: build the production adapter, call it, score it.

Each ``run_<call>`` returns a flat result row. ``ok`` means the production
adapter accepted the output (what the learner would actually get); quality
metrics are computed from the raw provider output so a rejected answer can
still be diagnosed. ``primary`` is a 0-1 composite used only for ranking; the
component metrics are kept beside it and are what the report quotes.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.enums import MediaSource
from evals.scene_analysis import scoring as scene_scoring
from evals.scene_analysis.ground_truth import EvalCase
from evals.scene_analysis.ground_truth import load_cases as load_scene_cases
from evals.scene_translation import scoring as translation_scoring
from evals.scene_translation.ground_truth import TranslationCase
from evals.scene_translation.ground_truth import load_cases as load_translation_cases

from . import cjk_lexicon
from .providers import (
    JUDGE,
    TIMEOUTS,
    Candidate,
    openai_sdk_client,
    recording_text_client,
    recording_vision_client,
    text_config,
    vision_config,
)
from .recording import CallRecord, Overrides, RecordingResponsesClient

EVALS = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
SCENE_ROOT = EVALS / "scene_analysis"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


# --------------------------------------------------------------------------- cases


@cache
def scenes() -> dict[str, dict[str, Any]]:
    rows = json.loads((HERE / "cases" / "scenes.json").read_text(encoding="utf-8"))
    return {row["scene_id"]: row for row in rows}


def translation_payload(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "targetLanguage": scene["targetLanguage"],
        "sceneTitle": scene["sceneTitle"],
        "sceneSummary": scene["sceneSummary"],
    }


def learning_payload(scene: dict[str, Any]) -> dict[str, Any]:
    """Mirror ``workflow._learning_task_payload`` for a fixture scene."""
    from app.ai.features.learning_tasks import required_task_focuses

    payload = {
        **translation_payload(scene),
        "objects": [
            {k: v for k, v in {
                "key": o["key"], "source": o["source"], "translation": o["translation"],
                "article": o.get("article"), "gender": o.get("gender"),
            }.items() if v is not None}
            for o in scene["objects"]
        ],
        "attributes": [
            {"key": a["key"], "source": a["source"], "translation": a["translation"],
             "objectKey": a["key"].rsplit(":", 1)[0]}
            for a in scene["attributes"]
        ],
        "relationships": [
            {"key": r["key"], "source": r["source"], "translation": r["translation"],
             "subjectObjectKey": r["subject"], "referenceObjectKey": r["reference"]}
            for r in scene["relationships"]
        ],
    }
    payload["requiredTaskFocuses"] = list(required_task_focuses(payload))
    return payload


def clue_payload(scene: dict[str, Any]) -> dict[str, Any]:
    """Mirror ``workflow._ispy_clue_payload``: anchor point = box centre."""
    payload = learning_payload(scene)
    boxes = {o["key"]: o["box"] for o in scene["objects"]}
    for item in payload["objects"]:
        box = boxes[item["key"]]
        item["anchorPoint"] = {
            "x": round(box["x"] + box["width"] / 2, 3),
            "y": round(box["y"] + box["height"] / 2, 3),
        }
    payload.pop("requiredTaskFocuses", None)
    return payload


def guess_context(scene: dict[str, Any]) -> dict[str, Any]:
    """Mirror ``workflow._ispy_guess_context``."""
    payload = clue_payload(scene)
    return {
        "targetLanguage": payload["targetLanguage"],
        "sceneObjects": {
            "objects": payload["objects"],
            "attributes": payload["attributes"],
            "relations": payload["relationships"],
        },
    }


class CjkCase(BaseModel):
    case_id: str
    target_language: str
    scene_title: str
    scene_summary: str
    objects: list[dict[str, str]]
    attributes: list[dict[str, str]] = []
    relationships: list[dict[str, str]] = []

    def payload(self) -> dict[str, Any]:
        return {
            "targetLanguage": self.target_language, "sceneTitle": self.scene_title,
            "sceneSummary": self.scene_summary, "objects": self.objects,
            "attributes": self.attributes, "relationships": self.relationships,
        }


def load_cases(call: str) -> list[Any]:
    if call == "scene_analysis":
        return load_scene_cases(SCENE_ROOT / "cases")
    if call == "translation":
        cjk = json.loads((HERE / "cases" / "translation_cjk.json").read_text(encoding="utf-8"))
        return [
            *load_translation_cases(EVALS / "scene_translation" / "cases"),
            *(CjkCase.model_validate(row) for row in cjk),
        ]
    if call == "learning_tasks":
        return [s for s in scenes().values() if s["targetLanguage"] in ("es", "fr")]
    if call == "ispy_clues":
        return list(scenes().values())
    if call == "ispy_guess":
        return json.loads((HERE / "cases" / "ispy_guess.json").read_text(encoding="utf-8"))
    raise ValueError(call)


def case_id(case: Any) -> str:
    if isinstance(case, dict):
        return case.get("case_id") or case["scene_id"]
    return case.case_id


def case_language(call: str, case: Any) -> str:
    if call == "scene_analysis":
        return "n/a"
    if call == "ispy_guess":
        return scenes()[case["scene_id"]]["targetLanguage"]
    if isinstance(case, dict):
        return case["targetLanguage"]
    return case.target_language


# ------------------------------------------------------------------------ helpers


def _row(record: CallRecord, **extra: Any) -> dict[str, Any]:
    row = asdict(record)
    row.update(extra)
    return row


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


# ----------------------------------------------------------------- scene analysis


class _FileStorage:
    """Stands in for Supabase storage: the eval images are local files."""

    def download(self, key: str) -> bytes:
        return Path(key).read_bytes()


def run_scene_analysis(cand: Candidate, overrides: Overrides, case: EvalCase) -> dict:
    from app.ai.features.scene_analysis import UploadedSceneAnalyzer
    from app.ai.observability import NoOpAITracer

    config = vision_config("scene_analysis", cand, overrides)
    client = recording_vision_client(cand, config)
    analyzer = UploadedSceneAnalyzer(
        _FileStorage(), client, config,
        tracer=NoOpAITracer(), provider=cand.provider, object_grounder=None,
    )
    path = case.image_path(SCENE_ROOT)
    asset = SimpleNamespace(
        storage_key=str(path),
        mime_type=MIME[path.suffix.lower()],
        source=MediaSource.USER_UPLOAD,
    )
    session = SimpleNamespace(id=uuid4())
    unusable = case.expectation.mode.value == "empty"
    ok, error, kept = False, None, None
    try:
        result = analyzer.analyze(session, asset, {}, None)
        ok, kept = not unusable, len(result.objects)
    except Exception as exc:  # noqa: BLE001 - the app's refusal is a data point
        error = f"{type(exc).__name__}: {exc}"
        # Refusing an unusable photo is correct app behaviour; an API failure is not.
        ok = unusable and client.record.error is None
    rec = client.record
    score = scene_scoring.score_case(case, rec.raw_text or "")
    if not score.parsed:
        primary = 0.0
    elif unusable:
        primary = 1.0 if score.empty_as_required else 0.0
    else:
        primary = (
            0.5 * (score.anchor_recall or 0)
            + 0.3 * (score.supported_precision or 0)
            + 0.2 * (1.0 if score.violation_count == 0 else 0.0)
        )
    quality = {
        "parsed": score.parsed, "anchor_recall": score.anchor_recall,
        "supported_precision": score.supported_precision, "title_match": score.title_match,
        "mean_iou": score.mean_iou, "boxes_roughly_right": score.boxes_roughly_right,
        "boxes_scored": score.boxes_scored, "relation_recall": score.relation_recall,
        "empty_as_required": score.empty_as_required,
        "hallucinated_objects": len(score.hallucinated_objects),
        "violations": score.violation_count, "object_count": score.object_count,
        "objects_kept_after_confidence_filter": kept, "issue_codes": score.issue_codes,
        "difficulty": case.difficulty.value,
    }
    return _row(rec, ok=ok, adapter_error=error, primary=primary, quality=quality)


# -------------------------------------------------------------------- translation


def run_translation(cand: Candidate, overrides: Overrides, case: Any) -> dict:
    from app.ai.features.translation import SceneTranslationService
    from app.ai.observability import NoOpAITracer

    config = text_config("translation", cand, overrides)
    client = recording_text_client(cand, config)
    service = SceneTranslationService(
        client, config, tracer=NoOpAITracer(), provider=cand.provider
    )
    ok, error = False, None
    try:
        service.translate(case.payload())
        ok = True
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    rec = client.record
    if isinstance(case, TranslationCase):
        score = translation_scoring.score_case(case, rec.raw_text or "")
        parts = [score.noun_accuracy, score.article_accuracy, score.gender_accuracy,
                 score.attribute_accuracy, score.relation_accuracy]
        primary = (_mean(parts) or 0.0) if score.parsed else 0.0
        quality = {
            "parsed": score.parsed, "structurally_valid": score.structurally_valid,
            "noun_accuracy": score.noun_accuracy, "article_accuracy": score.article_accuracy,
            "gender_accuracy": score.gender_accuracy, "elision_accuracy": score.elision_accuracy,
            "attribute_accuracy": score.attribute_accuracy,
            "relation_accuracy": score.relation_accuracy, "clean": score.clean,
            "wrong_nouns": score.wrong_nouns, "wrong_articles": score.wrong_articles,
            "wrong_genders": score.wrong_genders,
            "articles_in_translation": score.articles_in_translation,
        }
    else:
        quality = _score_cjk(case, rec.raw_text)
        primary = quality.get("term_accuracy") or 0.0
    return _row(rec, ok=ok, adapter_error=error, primary=primary, quality=quality)


def _score_cjk(case: CjkCase, raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "")
    except Exception:  # noqa: BLE001
        return {"parsed": False, "structurally_valid": False}
    results, wrong = [], []
    for field in ("objects", "attributes", "relationships"):
        for term in data.get(field, []):
            good = cjk_lexicon.accepted(
                case.target_language, term.get("source", ""), term.get("translation") or ""
            )
            results.append(good)
            if not good:
                wrong.append(f"{term.get('source')}={term.get('translation')}")
    objects = data.get("objects", [])
    script = re.compile(r"[぀-ヿ一-鿿가-힯]")
    in_script = [bool(script.search(o.get("translation") or "")) for o in objects]
    return {
        "parsed": True,
        "structurally_valid": False,  # the production validator demands an article
        "term_accuracy": sum(results) / len(results) if results else 0.0,
        "wrong_terms": wrong,
        # A correct ja/ko answer has no article; any article here was invented
        # to satisfy the validator.
        "objects_with_invented_article": sum(1 for o in objects if o.get("article")),
        "objects_with_invented_gender": sum(1 for o in objects if o.get("gender")),
        "wrong_language": bool(objects) and not any(in_script),
        "objects": len(objects),
    }


# ----------------------------------------------------------------------- judging


class LessonVerdict(BaseModel):
    reason: str
    wrong_answer_keys: int = Field(description="Questions whose marked answer is not correct.")
    ambiguous_questions: int = Field(description="Questions with more than one defensible answer.")
    invented_facts: int = Field(
        description="Questions using objects/attributes/relations not supplied."
    )
    level_appropriate: bool
    score: int = Field(ge=1, le=5)


class ClueVerdict(BaseModel):
    clue_index: int
    identified_object_key: str | None = Field(
        description="The supplied object the clue most plausibly describes, or null."
    )
    uniquely_identifies: bool
    grounded: bool = Field(description="Uses only supplied attributes, relations and positions.")
    language_score: int = Field(ge=1, le=5, description="Target-language correctness for A1/A2.")


class ClueVerdicts(BaseModel):
    verdicts: list[ClueVerdict]


LESSON_RUBRIC = """You are a strict language teacher auditing auto-generated grammar exercises
for CEFR A1/A2 learners of the target language. You get the approved scene vocabulary
and the generated lesson. Check every question:
- Is the option marked correct (correctOptionId / correctText) actually correct and natural?
- Is exactly one option defensible? Count questions where two or more options are correct.
- Are distractors plausibly wrong (wrong gender, wrong plural, ser vs estar), not absurd?
- Does any question use an object, attribute or relation that is not in the supplied scene?
- Are explanations accurate and prompts free of blanks like ___?
score: 5 = flawless and teachable; 4 = minor stylistic issues; 3 = one real error;
2 = several errors; 1 = unusable. Be exact with the counts."""

CLUE_RUBRIC = """You play I-Spy. For each clue, the app shows the learner "I spy with my little
eye, something that ..." followed by the clue in the target language. Using ONLY the
supplied scene facts (objects with attributes, relations and anchor positions where
x=0 is left, y=0 is top), say which object key the clue describes, whether it points to
exactly one object, whether it only uses supplied facts, and rate its target-language
correctness and A1/A2 suitability (5 = perfect). You are not told the intended answer."""


def _facts_for(cand: Candidate):
    from .providers import facts

    return facts()[cand.catalogue_id]


def _judge(
    system: str, payload: dict[str, Any], schema: type[BaseModel]
) -> tuple[Any, CallRecord]:
    """One judge verdict, through the same text seam the app uses."""
    from app.ai.text_model import TextModelRequest
    from app.services.vision_model import build_strict_json_schema

    config = text_config("judge", JUDGE, Overrides())
    client = recording_text_client(JUDGE, config)
    request = TextModelRequest(
        system_prompt=system,
        user_content=json.dumps(payload, ensure_ascii=False),
        json_schema_name="judge_verdict",
        json_schema=build_strict_json_schema(schema),
        prompt_version="judge-v1",
    )
    try:
        response = client.generate(request)
        return schema.model_validate_json(response.output_text), client.record
    except Exception:  # noqa: BLE001 - a judge failure leaves the judged fields empty
        return None, client.record


# ----------------------------------------------------------------- learning tasks


_SER = re.compile(r"\b(es|son|eres|soy|somos)\b", re.IGNORECASE)
_ESTAR = re.compile(r"\b(est[áa]n?|estoy|est[áa]s|estamos)\b", re.IGNORECASE)


def _lesson_from_raw(payload: dict[str, Any], raw: str | None) -> dict[str, Any] | None:
    """The model's lesson as plain JSON, whether or not the app accepted it."""
    try:
        data = json.loads(raw or "")
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return data
    if not isinstance(data, dict):
        return None
    tasks = []
    for focus in payload["requiredTaskFocuses"]:
        task = data.get(focus)
        if isinstance(task, dict):
            tasks.append({**task, "focus": focus})
    return {"tasks": tasks} if tasks else None


def _lesson_checks(payload: dict[str, Any], lesson: dict[str, Any]) -> dict[str, bool]:
    """Rules the prompt states, checked on the lesson as returned."""
    tasks = lesson["tasks"]
    questions = [q for t in tasks for q in t.get("questions", [])]
    checks: dict[str, bool] = {}
    checks["focus_order"] = [t.get("focus") for t in tasks] == payload["requiredTaskFocuses"]
    checks["two_to_four_questions"] = all(
        2 <= len(t.get("questions", [])) <= 4 for t in tasks
    )
    objects_used = {k for q in questions for k in q.get("objectKeys", [])}
    checks["covers_3_objects"] = len(objects_used) >= min(3, len(payload["objects"]))
    checks["no_blanks"] = not any("___" in (q.get("prompt") or "") for q in questions)
    checks["prompts_present"] = all((q.get("prompt") or "").strip() for q in questions)
    checks["short_explanations"] = all(
        len([s for s in re.split(r"[.!?]+", t.get("explanation") or "") if s.strip()]) <= 2
        for t in tasks
    )
    choice_questions = [
        q for q in questions if q.get("interactionType", "multipleChoice") == "multipleChoice"
    ]
    checks["four_options_one_answer"] = all(
        len(q.get("options") or []) == 4
        and q.get("correctOptionId") in {o.get("optionId") for o in q.get("options") or []}
        for q in choice_questions
    )
    builders = [q for q in questions if q.get("interactionType") == "sentenceBuilding"]
    checks["builder_tokens_complete"] = all(
        set(re.findall(r"[\w'’À-ÿ-]+", q.get("correctText") or ""))
        <= set(q.get("tokenBank") or [])
        for q in builders
    ) if builders else True
    if payload["targetLanguage"] == "es":
        scene_questions = [
            q for t in tasks if t.get("focus") == "sceneDescription"
            for q in t.get("questions", [])
        ]
        ok_estar, ok_ser = True, True
        for q in scene_questions:
            options = {o.get("optionId"): o.get("label", "") for o in q.get("options") or []}
            correct = options.get(q.get("correctOptionId"), "")
            ok_estar &= bool(_ESTAR.search(correct)) and not _SER.search(correct)
            ok_ser &= any(
                _SER.search(label) for oid, label in options.items()
                if oid != q.get("correctOptionId")
            )
        checks["es_correct_uses_estar"] = ok_estar
        checks["es_has_ser_distractor"] = ok_ser
    return checks


def run_learning_tasks(
    cand: Candidate, overrides: Overrides, scene: dict[str, Any], judge: bool
) -> dict:
    from app.ai.features.learning_tasks import LearningTaskService
    from app.ai.observability import NoOpAITracer

    config = text_config("learning_tasks", cand, overrides)
    client = recording_text_client(cand, config)
    adapter = LearningTaskService(
        client, config, tracer=NoOpAITracer(), provider=cand.provider
    )
    payload = learning_payload(scene)
    result, error = None, None
    try:
        result = adapter.generate(payload)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    rec = client.record
    quality: dict[str, Any] = {"validator_pass": result is not None}
    # Quality is scored from the lesson the model returned, so a model is not
    # ranked zero purely because the app's schema rejected it.
    lesson = (
        result.model_dump(mode="json", by_alias=True) if result is not None
        else _lesson_from_raw(payload, rec.raw_text)
    )
    judge_cost = None
    if lesson is not None:
        checks = _lesson_checks(payload, lesson)
        quality["checks"] = checks
        quality["check_pass_rate"] = sum(checks.values()) / len(checks)
        quality["questions"] = sum(len(t.get("questions", [])) for t in lesson["tasks"])
        quality["tasks"] = len(lesson["tasks"])
        if judge:
            judge_cost = judge_lesson(quality, payload, lesson)
    return _row(rec, ok=result is not None, adapter_error=error,
                primary=lesson_primary(quality), quality=quality, judge_cost_usd=judge_cost)


def lesson_primary(quality: dict[str, Any]) -> float:
    """Half the prompt's own rules, half the judge; zero only if nothing parsed."""
    if "check_pass_rate" not in quality:
        return 0.0
    judged = quality.get("judge")
    if judged:
        return 0.5 * quality["check_pass_rate"] + 0.5 * (judged["score"] - 1) / 4
    return quality["check_pass_rate"]


def judge_lesson(
    quality: dict[str, Any], payload: dict[str, Any], lesson: dict[str, Any]
) -> float | None:
    verdict, record = _judge(
        LESSON_RUBRIC, {"scene": payload, "lesson": lesson}, LessonVerdict
    )
    if verdict is not None:
        quality["judge"] = verdict.model_dump()
    return record.cost_usd


def rebuild_lesson(scene: dict[str, Any], raw: str) -> tuple[dict[str, Any], Any]:
    """Recover the lesson from a saved raw response, for later judging."""
    payload = learning_payload(scene)
    return payload, _lesson_from_raw(payload, raw)


# --------------------------------------------------------------------- I-Spy clues


def run_ispy_clues(
    cand: Candidate, overrides: Overrides, scene: dict[str, Any], judge: bool
) -> dict:
    from app.ai.features.ispy_clues import ISpyClueService
    from app.ai.observability import NoOpAITracer

    config = text_config("ispy_clues", cand, overrides)
    client = recording_text_client(cand, config)
    adapter = ISpyClueService(
        client, config, tracer=NoOpAITracer(), provider=cand.provider
    )
    payload = clue_payload(scene)
    result, error = None, None
    try:
        result = adapter.generate(payload)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    rec = client.record
    quality: dict[str, Any] = {"validator_pass": result is not None}
    judge_cost = None
    if result is not None:
        names = {o["key"]: o["translation"].casefold() for o in payload["objects"]}
        leaks = [c.answer_object_key for c in result.clues
                 if names[c.answer_object_key] in c.clue.casefold()]
        quality.update(clues=len(result.clues), name_leaks=len(leaks),
                       leaked=leaks, texts=[c.clue for c in result.clues],
                       answers=[c.answer_object_key for c in result.clues])
        if judge:
            judge_cost = judge_clues(quality, payload, result)
    return _row(rec, ok=result is not None, adapter_error=error,
                primary=clue_primary(quality), quality=quality, judge_cost_usd=judge_cost)


def clue_primary(quality: dict[str, Any]) -> float:
    """Per clue: 0 if it names its answer; otherwise judge-weighted when judged."""
    if not quality.get("validator_pass"):
        return 0.0
    per_clue = [0.0 if a in quality["leaked"] else 1.0 for a in quality["answers"]]
    for i, verdict in enumerate(quality.get("judge", {}).get("per_clue", [])):
        if verdict is not None:
            per_clue[i] *= (
                0.5 * verdict["solved"] + 0.25 * verdict["grounded"]
                + 0.25 * (verdict["language_score"] - 1) / 4
            )
    return _mean(per_clue) or 0.0


def judge_clues(quality: dict[str, Any], payload: dict[str, Any], result: Any) -> float | None:
    verdicts, record = _judge(
        CLUE_RUBRIC,
        {"scene": payload, "clues": [
            {"clue_index": i, "clue": c.clue} for i, c in enumerate(result.clues)
        ]},
        ClueVerdicts,
    )
    if verdicts is not None:
        by_index = {v.clue_index: v for v in verdicts.verdicts}
        per_clue = []
        for i, clue in enumerate(result.clues):
            v = by_index.get(i)
            per_clue.append(None if v is None else {
                "solved": v.identified_object_key == clue.answer_object_key
                and v.uniquely_identifies,
                "identified": v.identified_object_key,
                "grounded": v.grounded, "language_score": v.language_score,
            })
        present = [p for p in per_clue if p]
        quality["judge"] = {
            "per_clue": per_clue,
            "solved_rate": _mean([float(p["solved"]) for p in present]),
            "grounded_rate": _mean([float(p["grounded"]) for p in present]),
            "language_score": _mean([float(p["language_score"]) for p in present]),
        }
    return record.cost_usd


# --------------------------------------------------------------------- I-Spy guess


def run_ispy_guess(cand: Candidate, overrides: Overrides, case: dict[str, Any]) -> dict:
    from app.services.openai_ispy_guess import OpenAIISpyGuessGenerator

    # The guess adapter still speaks the OpenAI SDK rather than the text seam.
    timeout = TIMEOUTS.get("ispy_guess", 60)
    client = RecordingResponsesClient(openai_sdk_client(cand, timeout), _facts_for(cand))
    adapter = OpenAIISpyGuessGenerator(
        "unused", cand.model, client=client, timeout_seconds=timeout
    )
    scene = scenes()[case["scene_id"]]
    result, error = None, None
    try:
        result = adapter.guess(guess_context(scene), case["learner_text"])
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    rec = client.record
    expect = case["expect"]
    quality: dict[str, Any] = {"validator_pass": result is not None}
    primary = 0.0
    if result is not None:
        want = expect["object"]
        if want == "any":
            acceptable = set(expect.get("acceptable") or [o["key"] for o in scene["objects"]])
            correct = result.guessed_object_key in acceptable
        else:
            correct = result.guessed_object_key == want
        amb_ok = None if expect["ambiguous"] is None else result.ambiguous == expect["ambiguous"]
        matched = set(result.matched_evidence_keys)
        contradicted = set(result.contradicted_evidence_keys)
        exp_m, exp_c = set(expect["matched"]), set(expect["contradicted"])
        evidence_recall = (
            len(matched & exp_m) / len(exp_m) if exp_m else None
        )
        contradiction_hit = (exp_c <= contradicted) if exp_c else (not contradicted)
        sentences = [s for s in re.split(r"[.!?]+", result.feedback) if s.strip()]
        quality.update(
            guess_correct=correct, ambiguity_correct=amb_ok,
            evidence_recall=evidence_recall, contradiction_correct=contradiction_hit,
            feedback_sentences=len(sentences), feedback=result.feedback,
            feedback_is_english=bool(re.fullmatch(r"[\x00-\x7F’‘“”éèàçñ¡¿—–…]*", result.feedback)),
        )
        primary = (
            0.6 * correct
            + 0.15 * (amb_ok if amb_ok is not None else correct)
            + 0.15 * (evidence_recall if evidence_recall is not None else 1.0)
            + 0.10 * contradiction_hit
        )
    return _row(rec, ok=result is not None, adapter_error=error, primary=primary, quality=quality)


RUNNERS = {
    "scene_analysis": run_scene_analysis,
    "translation": run_translation,
    "learning_tasks": run_learning_tasks,
    "ispy_clues": run_ispy_clues,
    "ispy_guess": run_ispy_guess,
}
JUDGED = {"learning_tasks", "ispy_clues"}
