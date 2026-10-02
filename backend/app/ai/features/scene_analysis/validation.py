"""Deterministic semantic validation for raw scene-analysis model output."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from app.ai.features.scene_analysis.schemas import (
    SceneAnalysisIssue,
    SceneAnalysisIssueCode,
    SceneAnalysisModelResult,
)
from app.schemas.enums import (
    INVERSE_SCENE_RELATION_TYPES,
    SYMMETRIC_SCENE_RELATION_TYPES,
    SceneRelationType,
)
from app.services.scene_analysis import SceneAnalysisError


class SceneAnalysisValidationError(SceneAnalysisError):
    def __init__(self, issues: Sequence[SceneAnalysisIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{issue.code.value}: {issue.message}" for issue in self.issues
        )
        super().__init__(summary)


def _error_path(location: tuple[Any, ...]) -> str:
    path = ""
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path


def _issue(
    code: SceneAnalysisIssueCode, message: str, path: str | None = None
) -> SceneAnalysisIssue:
    return SceneAnalysisIssue(code=code, message=message, path=path)


def _check_confidence(
    issues: list[SceneAnalysisIssue],
    value: float,
    subject: str,
    path: str,
) -> None:
    if not math.isfinite(value):
        issues.append(
            _issue(
                SceneAnalysisIssueCode.NON_FINITE_CONFIDENCE,
                f"{subject} has non-finite confidence {value!r}",
                path,
            )
        )
    elif not 0 <= value <= 1:
        issues.append(
            _issue(
                SceneAnalysisIssueCode.CONFIDENCE_OUT_OF_RANGE,
                f"{subject} has confidence {value!r}, expected 0..1",
                path,
            )
        )


def validate_scene_analysis(
    result: SceneAnalysisModelResult,
) -> SceneAnalysisModelResult:
    issues: list[SceneAnalysisIssue] = []

    object_keys: set[str] = set()
    for index, scene_object in enumerate(result.objects):
        if scene_object.object_key in object_keys:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.DUPLICATE_OBJECT_KEY,
                    f"duplicate object key {scene_object.object_key!r}",
                    f"objects[{index}].objectKey",
                )
            )
        object_keys.add(scene_object.object_key)

    relation_keys: set[str] = set()
    for index, relation in enumerate(result.relations):
        if relation.relation_key in relation_keys:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.DUPLICATE_RELATION_KEY,
                    f"duplicate relation key {relation.relation_key!r}",
                    f"relations[{index}].relationKey",
                )
            )
        relation_keys.add(relation.relation_key)

    box_fields = ("x", "y", "width", "height")
    for index, scene_object in enumerate(result.objects):
        box = scene_object.bounding_box
        non_finite = [
            field for field in box_fields if not math.isfinite(getattr(box, field))
        ]
        if non_finite:
            for field in non_finite:
                value = getattr(box, field)
                issues.append(
                    _issue(
                        SceneAnalysisIssueCode.NON_FINITE_BOUNDING_BOX,
                        f"object {scene_object.object_key!r} has non-finite {field}={value!r}",
                        f"objects[{index}].boundingBox.{field}",
                    )
                )
            continue

        for field in box_fields:
            value = getattr(box, field)
            if not 0 <= value <= 1:
                issues.append(
                    _issue(
                        SceneAnalysisIssueCode.BOUNDING_BOX_OUT_OF_RANGE,
                        f"object {scene_object.object_key!r} has {field}={value!r}, expected 0..1",
                        f"objects[{index}].boundingBox.{field}",
                    )
                )

        for field in ("width", "height"):
            value = getattr(box, field)
            if value <= 0:
                issues.append(
                    _issue(
                        SceneAnalysisIssueCode.NON_POSITIVE_BOUNDING_BOX_SIZE,
                        f"object {scene_object.object_key!r} has non-positive {field}={value!r}",
                        f"objects[{index}].boundingBox.{field}",
                    )
                )

        if box.x + box.width > 1 + 1e-9:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.BOUNDING_BOX_OUTSIDE_IMAGE,
                    f"object {scene_object.object_key!r} has x + width={box.x + box.width!r}",
                    f"objects[{index}].boundingBox",
                )
            )
        if box.y + box.height > 1 + 1e-9:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.BOUNDING_BOX_OUTSIDE_IMAGE,
                    f"object {scene_object.object_key!r} has y + height={box.y + box.height!r}",
                    f"objects[{index}].boundingBox",
                )
            )

        _check_confidence(
            issues,
            scene_object.confidence_score,
            f"object {scene_object.object_key!r}",
            f"objects[{index}].confidenceScore",
        )

        anchor = scene_object.anchor_point
        if anchor is not None:
            anchor_path = f"objects[{index}].anchorPoint"
            non_finite_anchor = [
                field for field in ("x", "y") if not math.isfinite(getattr(anchor, field))
            ]
            for field in non_finite_anchor:
                issues.append(
                    _issue(
                        SceneAnalysisIssueCode.NON_FINITE_ANCHOR_POINT,
                        f"object {scene_object.object_key!r} has non-finite "
                        f"anchor {field}={getattr(anchor, field)!r}",
                        f"{anchor_path}.{field}",
                    )
                )
            if not non_finite_anchor:
                for field in ("x", "y"):
                    value = getattr(anchor, field)
                    if not 0 <= value <= 1:
                        issues.append(
                            _issue(
                                SceneAnalysisIssueCode.ANCHOR_POINT_OUT_OF_RANGE,
                                f"object {scene_object.object_key!r} has anchor "
                                f"{field}={value!r}, expected 0..1",
                                f"{anchor_path}.{field}",
                            )
                        )

    seen_relations: set[tuple[SceneRelationType, str, str]] = set()
    for index, relation in enumerate(result.relations):
        relation_path = f"relations[{index}]"
        if relation.subject_object_key not in object_keys:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.UNKNOWN_RELATION_OBJECT,
                    f"relation {relation.relation_key!r} has unknown subject object key "
                    f"{relation.subject_object_key!r}",
                    f"{relation_path}.subjectObjectKey",
                )
            )
        if relation.reference_object_key not in object_keys:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.UNKNOWN_RELATION_OBJECT,
                    f"relation {relation.relation_key!r} has unknown reference object key "
                    f"{relation.reference_object_key!r}",
                    f"{relation_path}.referenceObjectKey",
                )
            )

        _check_confidence(
            issues,
            relation.confidence_score,
            f"relation {relation.relation_key!r}",
            f"{relation_path}.confidenceScore",
        )

        is_self_relation = relation.subject_object_key == relation.reference_object_key
        if is_self_relation:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.SELF_RELATION,
                    f"relation {relation.relation_key!r} connects object "
                    f"{relation.subject_object_key!r} to itself",
                    relation_path,
                )
            )
            continue

        relation_tuple = (
            relation.relation,
            relation.subject_object_key,
            relation.reference_object_key,
        )
        if relation_tuple in seen_relations:
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.DUPLICATE_RELATION,
                    f"relation {relation.relation_key!r} duplicates an earlier "
                    f"{relation.relation.value} relation from "
                    f"{relation.subject_object_key!r}"
                    f"->{relation.reference_object_key!r}",
                    relation_path,
                )
            )
        elif (
            relation.relation in SYMMETRIC_SCENE_RELATION_TYPES
            and (
                relation.relation,
                relation.reference_object_key,
                relation.subject_object_key,
            )
            in seen_relations
        ):
            issues.append(
                _issue(
                    SceneAnalysisIssueCode.SYMMETRIC_DUPLICATE_RELATION,
                    f"relation {relation.relation_key!r} reverses an earlier "
                    f"{relation.relation.value} relation",
                    relation_path,
                )
            )
        else:
            inverse = INVERSE_SCENE_RELATION_TYPES.get(relation.relation)
            if (
                inverse is not None
                and (
                    inverse,
                    relation.reference_object_key,
                    relation.subject_object_key,
                )
                in seen_relations
            ):
                issues.append(
                    _issue(
                        SceneAnalysisIssueCode.INVERSE_DUPLICATE_RELATION,
                        f"relation {relation.relation_key!r} inverts an earlier "
                        f"{inverse.value} relation",
                        relation_path,
                    )
                )
        seen_relations.add(relation_tuple)

    if issues:
        raise SceneAnalysisValidationError(issues)
    return result


def parse_scene_analysis(
    payload: Mapping[str, Any] | str | bytes,
) -> SceneAnalysisModelResult:
    try:
        if isinstance(payload, (str, bytes)):
            result = SceneAnalysisModelResult.model_validate_json(payload)
        else:
            result = SceneAnalysisModelResult.model_validate(payload)
    except ValidationError as exc:
        issues = [
            _issue(
                SceneAnalysisIssueCode.INVALID_SCHEMA,
                error["msg"],
                _error_path(error["loc"]),
            )
            for error in exc.errors()
        ]
        raise SceneAnalysisValidationError(issues) from exc
    return validate_scene_analysis(result)
