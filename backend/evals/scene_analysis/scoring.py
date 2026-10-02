"""Scoring for the scene-analysis evaluation dataset.

Schema validity is not re-implemented here. The scorer calls
``app.services.scene_analysis_validation.parse_scene_analysis`` -- the same
function the API uses -- so "valid" in an eval report means exactly "production
would have accepted this response", and the two can never drift apart.

Accuracy is reported as two numbers rather than one, because they fail
differently and the fix differs too:

``anchor_recall``
    Did it find the things that are definitely there? Low recall is usually a
    capability problem: a weaker vision encoder.

``supported_precision``
    Of what it returned, how much is actually in the photo? Low precision is
    hallucination, and for a vocabulary app that is the worse failure: a
    confidently mislabelled object teaches a learner a word for something that
    was never in front of them.

Rule violations are counted separately from both. A model that scores well on
accuracy while naming a child or a brand has not "mostly passed" -- it has
failed a requirement, and averaging that into an accuracy score would hide it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.features.scene_analysis.schemas import SceneAnalysisModelResult
from app.ai.features.scene_analysis.validation import (
    SceneAnalysisValidationError,
    parse_scene_analysis,
)

from .ground_truth import EvalCase, ExpectationMode, ExpectedObject

IOU_MATCH_THRESHOLD = 0.3
"""Vision models place boxes loosely and our reference boxes are hand-drawn, so
a box is called "roughly right" well below the 0.5 a detection benchmark uses.
Mean IoU is reported alongside it as the finer-grained signal."""

ADJECTIVES = frozenset({
    "red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "black",
    "white", "grey", "gray", "silver", "gold", "golden", "beige", "cream", "dark",
    "light", "pale", "bright", "big", "large", "small", "tiny", "little", "huge",
    "long", "short", "tall", "wide", "narrow", "thin", "thick", "round", "square",
    "rectangular", "oval", "curved", "flat", "wooden", "metal", "metallic", "steel",
    "plastic", "glass", "paper", "cardboard", "leather", "fabric", "cloth", "ceramic",
    "striped", "spotted", "patterned", "checkered", "plain", "floral", "open", "closed",
    "empty", "full", "broken", "clean", "dirty", "old", "new", "worn", "shiny", "dull",
    "stacked", "folded", "hanging", "wet", "dry", "fresh", "ripe",
})

INHERENTLY_PLURAL = frozenset({
    "glasses", "scissors", "trousers", "jeans", "shorts", "pliers", "headphones",
    "tongs", "binoculars", "pyjamas", "sunglasses", "goods", "stairs",
})

BRANDS = frozenset({
    "coca-cola", "coca cola", "coke", "pepsi", "nestle", "kelloggs", "kellogg's",
    "heinz", "nike", "adidas", "apple inc", "samsung", "sony", "lego", "ikea",
    "starbucks", "mcdonalds", "mcdonald's", "tesco", "walmart", "carrefour",
    "colgate", "dove", "lipton", "nescafe", "oreo", "pringles", "fanta", "sprite",
    "cadbury", "danone", "unilever", "maggi", "haribo", "redbull", "red bull",
})
"""Deliberately short. Brand naming is caught mainly by a human skim of the
per-case output; this list exists so the obvious cases fail automatically."""


def normalize(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).casefold().strip()
    text = re.sub(r"[^a-z0-9\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def singularize(label: str) -> str | None:
    """Naive singular form, or None when the label is already singular."""
    if label in INHERENTLY_PLURAL or not label.endswith("s") or label.endswith("ss"):
        return None
    if label.endswith("ies") and len(label) > 4:
        return label[:-3] + "y"
    if label.endswith(("ches", "shes", "xes", "zes", "ses")):
        return label[:-2]
    return label[:-1]


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two (x, y, width, height) boxes."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1, bx1, by1 = ax0 + aw, ay0 + ah, bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class LabelMatch:
    """How one returned label relates to the case's expected vocabulary."""

    raw: str
    normalized: str
    expected: ExpectedObject | None = None
    is_anchor: bool = False
    via_singularization: bool = False
    stripped_adjective: str | None = None

    @property
    def supported(self) -> bool:
        return self.expected is not None


class _Vocabulary:
    def __init__(self, case: EvalCase) -> None:
        self._entries: list[tuple[ExpectedObject, bool]] = [
            *((anchor, True) for anchor in case.expectation.anchors),
            *((other, False) for other in case.expectation.acceptable),
        ]
        self._index: dict[str, tuple[ExpectedObject, bool]] = {}
        for expected, is_anchor in self._entries:
            for alias in expected.aliases():
                self._index.setdefault(normalize(alias), (expected, is_anchor))

    def match(self, raw_label: str) -> LabelMatch:
        normalized = normalize(raw_label)
        result = LabelMatch(raw=raw_label, normalized=normalized)

        direct = self._index.get(normalized)
        if direct is not None:
            result.expected, result.is_anchor = direct
            return result

        singular = singularize(normalized)
        if singular is not None and (hit := self._index.get(singular)) is not None:
            result.expected, result.is_anchor = hit
            result.via_singularization = True
            return result

        # "wooden spoon" -> "spoon": an adjective smuggled into the label, which
        # the prompt forbids. Only flagged when removing it reveals a real match,
        # so genuine compounds like "green bean" are left alone.
        tokens = normalized.split()
        if len(tokens) > 1 and tokens[0] in ADJECTIVES:
            remainder = " ".join(tokens[1:])
            hit = self._index.get(remainder) or self._index.get(singularize(remainder) or "")
            if hit is not None:
                result.expected, result.is_anchor = hit
                result.stripped_adjective = tokens[0]
        return result


@dataclass
class CaseScore:
    case_id: str
    difficulty: str
    tags: list[str]

    parsed: bool = False
    issue_codes: list[str] = field(default_factory=list)
    error: str | None = None

    object_count: int = 0
    anchor_recall: float | None = None
    anchors_found: list[str] = field(default_factory=list)
    anchors_missed: list[str] = field(default_factory=list)
    supported_precision: float | None = None
    unsupported_labels: list[str] = field(default_factory=list)

    title: str | None = None
    title_match: bool | None = None

    mean_iou: float | None = None
    boxes_roughly_right: int = 0
    boxes_scored: int = 0
    max_pairwise_overlap: float | None = None

    relation_recall: float | None = None
    relations_missed: list[str] = field(default_factory=list)
    relation_count: int = 0

    empty_as_required: bool | None = None
    hallucinated_objects: list[str] = field(default_factory=list)

    max_confidence: float | None = None
    confidence_within_cap: bool | None = None
    count_within_range: bool | None = None

    person_labels: list[str] = field(default_factory=list)
    brand_labels: list[str] = field(default_factory=list)
    adjective_labels: list[str] = field(default_factory=list)
    plural_labels: list[str] = field(default_factory=list)
    duplicate_labels: list[str] = field(default_factory=list)

    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def violation_count(self) -> int:
        return (
            len(self.person_labels) + len(self.brand_labels) + len(self.adjective_labels)
            + len(self.plural_labels) + len(self.duplicate_labels)
            + len(self.hallucinated_objects)
        )

    @property
    def clean(self) -> bool:
        """Valid, rule-abiding output. Says nothing about accuracy."""
        return self.parsed and self.violation_count == 0


def _mean(values: Iterable[float]) -> float | None:
    collected = list(values)
    return sum(collected) / len(collected) if collected else None


def score_case(
    case: EvalCase,
    payload: Mapping[str, Any] | str | bytes,
    *,
    latency_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> CaseScore:
    score = CaseScore(
        case_id=case.case_id,
        difficulty=case.difficulty.value,
        tags=list(case.tags),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    try:
        result: SceneAnalysisModelResult = parse_scene_analysis(payload)
    except SceneAnalysisValidationError as exc:
        score.issue_codes = sorted({issue.code.value for issue in exc.issues})
        score.error = str(exc)
        return score
    except Exception as exc:  # noqa: BLE001 - any parse failure is a failed case
        score.issue_codes = ["unparseable"]
        score.error = f"{type(exc).__name__}: {exc}"
        return score

    score.parsed = True
    _score_parsed(case, result, score)
    return score


def _score_parsed(
    case: EvalCase, result: SceneAnalysisModelResult, score: CaseScore
) -> None:
    expectation = case.expectation
    vocabulary = _Vocabulary(case)
    objects = result.objects

    score.object_count = len(objects)
    score.title = result.suggested_scene_title
    if expectation.scene_title_accept:
        accepted = {normalize(title) for title in expectation.scene_title_accept}
        score.title_match = normalize(result.suggested_scene_title) in accepted

    confidences = [obj.confidence_score for obj in objects]
    score.max_confidence = max(confidences) if confidences else None
    if expectation.max_confidence is not None and score.max_confidence is not None:
        score.confidence_within_cap = score.max_confidence <= expectation.max_confidence

    matches = [vocabulary.match(obj.label) for obj in objects]

    # An image with nothing legible in it: the only correct answer is no objects.
    if expectation.mode is ExpectationMode.EMPTY:
        score.empty_as_required = not objects
        score.hallucinated_objects = [match.raw for match in matches]
        score.count_within_range = not objects
        _score_violations(case, matches, score)
        return

    score.count_within_range = (
        expectation.min_objects <= len(objects) <= expectation.max_objects
    )

    if expectation.anchors:
        found = {
            match.expected.canonical for match in matches
            if match.is_anchor and match.expected is not None
        }
        score.anchors_found = sorted(found)
        score.anchors_missed = sorted(
            anchor.canonical for anchor in expectation.anchors
            if anchor.canonical not in found
        )
        score.anchor_recall = len(found) / len(expectation.anchors)

    if objects:
        supported = [match for match in matches if match.supported]
        score.supported_precision = len(supported) / len(objects)
        score.unsupported_labels = [
            match.raw for match in matches if not match.supported
        ]

    _score_boxes(case, result, matches, score)
    _score_relations(case, result, vocabulary, score)
    _score_violations(case, matches, score)


def _score_boxes(
    case: EvalCase,
    result: SceneAnalysisModelResult,
    matches: Sequence[LabelMatch],
    score: CaseScore,
) -> None:
    """IoU is scored only for anchors carrying a reference box.

    Reference boxes exist only for objects with a single unambiguous instance:
    scoring a returned "chair" against one of eight chairs would measure luck.
    """
    ious: list[float] = []
    for scene_object, match in zip(result.objects, matches, strict=True):
        expected = match.expected
        if expected is None or expected.box is None:
            continue
        box = scene_object.bounding_box
        ious.append(
            iou(
                (box.x, box.y, box.width, box.height),
                expected.box.as_tuple(),
            )
        )
    if ious:
        score.boxes_scored = len(ious)
        score.mean_iou = _mean(ious)
        score.boxes_roughly_right = sum(1 for value in ious if value >= IOU_MATCH_THRESHOLD)

    # Diagnostic for the overlapping-bubble problem in the UI: how badly do the
    # returned boxes collide with each other?
    boxes = [
        (obj.bounding_box.x, obj.bounding_box.y, obj.bounding_box.width, obj.bounding_box.height)
        for obj in result.objects
    ]
    overlaps = [
        iou(boxes[i], boxes[j])
        for i in range(len(boxes))
        for j in range(i + 1, len(boxes))
    ]
    if overlaps:
        score.max_pairwise_overlap = max(overlaps)


def _score_relations(
    case: EvalCase,
    result: SceneAnalysisModelResult,
    vocabulary: _Vocabulary,
    score: CaseScore,
) -> None:
    score.relation_count = len(result.relations)
    expected_relations = case.expectation.relations
    if not expected_relations:
        return

    # Object keys are assigned per response and mean nothing across models, so
    # relations are compared on canonical labels.
    canonical_by_key: dict[str, str] = {}
    for scene_object in result.objects:
        match = vocabulary.match(scene_object.label)
        if match.expected is not None:
            canonical_by_key[scene_object.object_key] = match.expected.canonical

    produced = {
        (
            canonical_by_key.get(relation.subject_object_key),
            relation.relation.value,
            canonical_by_key.get(relation.reference_object_key),
        )
        for relation in result.relations
    }

    missed = [
        f"{expected.subject} {expected.relation} {expected.reference}"
        for expected in expected_relations
        if (expected.subject, expected.relation, expected.reference) not in produced
    ]
    score.relations_missed = missed
    score.relation_recall = 1 - len(missed) / len(expected_relations)


def _score_violations(
    case: EvalCase, matches: Sequence[LabelMatch], score: CaseScore
) -> None:
    forbidden = {normalize(label) for label in case.expectation.forbidden_labels}
    seen: set[str] = set()

    for match in matches:
        normalized = match.normalized
        if normalized in forbidden or (singularize(normalized) or "") in forbidden:
            score.person_labels.append(match.raw)
        if normalized in BRANDS or any(brand in normalized for brand in BRANDS):
            score.brand_labels.append(match.raw)
        if match.stripped_adjective is not None:
            score.adjective_labels.append(match.raw)
        if match.via_singularization:
            score.plural_labels.append(match.raw)
        # Compared on the canonical label so that "wooden desk" alongside "desk"
        # registers as the duplicate object it is.
        identity = match.expected.canonical if match.expected is not None else normalized
        if identity in seen:
            score.duplicate_labels.append(match.raw)
        seen.add(identity)
