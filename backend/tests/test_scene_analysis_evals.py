"""Integrity checks for the scene-analysis eval dataset and its scorer.

The dataset is hand-labelled, so the failure mode is not a crash but a quiet
mislabelling that skews every model comparison drawn from it. These tests pin
the invariants that a labelling mistake would break -- overlapping aliases, one
concept entered twice, a relation naming an object that was never labelled --
and check that the scorer still flags the violations it exists to catch.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from evals.scene_analysis.ground_truth import EvalCase, ExpectationMode, load_cases
from evals.scene_analysis.scoring import normalize, score_case

EVAL_ROOT = Path(__file__).resolve().parents[1] / "evals" / "scene_analysis"
CASES = load_cases(EVAL_ROOT / "cases")


def _entries(case: EvalCase):
    return [*case.expectation.anchors, *case.expectation.acceptable]


def test_dataset_is_not_empty() -> None:
    assert len(CASES) >= 10


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_image_exists(case: EvalCase) -> None:
    assert case.image_path(EVAL_ROOT).is_file()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_no_alias_is_claimed_by_two_objects(case: EvalCase) -> None:
    """A shared alias silently attributes one label to the wrong object."""
    owners: dict[str, set[str]] = {}
    for entry in _entries(case):
        for alias in entry.aliases():
            owners.setdefault(normalize(alias), set()).add(entry.canonical)
    collisions = {alias: sorted(names) for alias, names in owners.items() if len(names) > 1}
    assert collisions == {}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_each_concept_appears_once(case: EvalCase) -> None:
    """One concept listed twice makes a single correct answer look duplicated."""
    counts = Counter(entry.canonical for entry in _entries(case))
    assert [name for name, count in counts.items() if count > 1] == []


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_reference_boxes_are_inside_the_image(case: EvalCase) -> None:
    for entry in _entries(case):
        if entry.box is None:
            continue
        assert entry.box.x + entry.box.width <= 1 + 1e-9, entry.canonical
        assert entry.box.y + entry.box.height <= 1 + 1e-9, entry.canonical


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_relations_reference_labelled_objects(case: EvalCase) -> None:
    known = {entry.canonical for entry in _entries(case)}
    for relation in case.expectation.relations:
        assert relation.subject in known, relation.subject
        assert relation.reference in known, relation.reference


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_anchors_fit_within_the_prompt_object_cap(case: EvalCase) -> None:
    """The prompt allows at most six objects; more anchors than that would
    penalise a model for obeying it."""
    assert len(case.expectation.anchors) <= case.expectation.max_objects


def _case(case_id: str) -> EvalCase:
    return next(case for case in CASES if case.case_id == case_id)


def _object(key: str, label: str, box: tuple[float, float, float, float],
            confidence: float = 0.9) -> dict:
    x, y, width, height = box
    return {
        "objectKey": key,
        "label": label,
        "boundingBox": {"x": x, "y": y, "width": width, "height": height},
        "attributes": [],
        "confidenceScore": confidence,
    }


def test_a_correct_response_scores_clean() -> None:
    case = _case("classroom-clean")
    payload = {
        "suggestedSceneTitle": "Classroom",
        "objects": [
            _object("object_1", "desk", (0.07, 0.45, 0.30, 0.20)),
            _object("object_2", "chair", (0.16, 0.61, 0.08, 0.24)),
            _object("object_3", "globe", (0.291, 0.359, 0.058, 0.091)),
        ],
        "relations": [{
            "relationKey": "relation_1",
            "subjectObjectKey": "object_3",
            "relation": "on",
            "referenceObjectKey": "object_1",
        }],
    }
    score = score_case(case, payload)

    assert score.parsed
    assert score.clean
    assert score.anchor_recall == 1.0
    assert score.supported_precision == 1.0
    assert score.title_match is True
    assert score.relation_recall == 1.0
    assert score.mean_iou is not None and score.mean_iou > 0.9


def test_rule_violations_are_each_reported() -> None:
    case = _case("classroom-clean")
    payload = {
        "suggestedSceneTitle": "Children In Class",
        "objects": [
            _object("object_1", "wooden desk", (0.07, 0.45, 0.30, 0.20)),
            _object("object_2", "chairs", (0.16, 0.61, 0.08, 0.24)),
            _object("object_3", "teacher", (0.15, 0.30, 0.12, 0.25)),
            _object("object_4", "desk", (0.07, 0.45, 0.30, 0.20)),
        ],
        "relations": [],
    }
    score = score_case(case, payload)

    assert score.parsed
    assert not score.clean
    assert score.adjective_labels == ["wooden desk"]
    assert score.plural_labels == ["chairs"]
    assert score.person_labels == ["teacher"]
    assert score.duplicate_labels == ["desk"]
    assert score.title_match is False


def test_a_genuine_compound_is_not_mistaken_for_an_adjective() -> None:
    """"green bean" is one word for one thing, unlike "wooden spoon"."""
    case = _case("grocery-crop-produce")
    payload = {
        "suggestedSceneTitle": "Grocery Store",
        "objects": [
            _object("object_1", "crate", (0.1, 0.1, 0.2, 0.2)),
            _object("object_2", "green bean", (0.4, 0.1, 0.2, 0.2)),
        ],
        "relations": [],
    }
    score = score_case(case, payload)

    assert score.adjective_labels == []
    assert score.unsupported_labels == []


def test_an_unusable_image_must_return_no_objects() -> None:
    case = _case("classroom-unusable")
    assert case.expectation.mode is ExpectationMode.EMPTY

    empty = score_case(case, {"suggestedSceneTitle": "Unclear", "objects": [], "relations": []})
    assert empty.empty_as_required is True
    assert empty.clean

    invented = score_case(case, {
        "suggestedSceneTitle": "Classroom",
        "objects": [_object("object_1", "desk", (0.1, 0.1, 0.2, 0.2), confidence=0.4)],
        "relations": [],
    })
    assert invented.empty_as_required is False
    assert invented.hallucinated_objects == ["desk"]
    assert not invented.clean


def test_invalid_geometry_is_rejected_by_the_production_validator() -> None:
    case = _case("classroom-clean")
    score = score_case(case, {
        "suggestedSceneTitle": "Classroom",
        "objects": [_object("object_1", "desk", (0.8, 0.8, 0.5, 0.5))],
        "relations": [],
    })

    assert not score.parsed
    assert "boundingBoxOutsideImage" in score.issue_codes


def test_unparseable_output_fails_the_case_rather_than_the_run() -> None:
    score = score_case(_case("classroom-clean"), "Here is the JSON you asked for: {oops")
    assert not score.parsed
    assert score.issue_codes
