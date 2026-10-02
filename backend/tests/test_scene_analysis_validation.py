import copy
import math

import pytest
from pydantic import ValidationError

from app.ai.features.scene_analysis.schemas import (
    ModelAnchorPoint,
    ModelBoundingBox,
    ModelSceneObject,
    ModelSceneRelation,
    SceneAnalysisIssueCode,
    SceneAnalysisModelResult,
)
from app.ai.features.scene_analysis.validation import (
    SceneAnalysisValidationError,
    parse_scene_analysis,
    validate_scene_analysis,
)
from app.schemas.enums import SceneRelationType


def object_payload(key: str = "chair", **box: float) -> dict:
    return {
        "objectKey": key,
        "label": key,
        "boundingBox": {
            "x": box.get("x", 0.1),
            "y": box.get("y", 0.1),
            "width": box.get("width", 0.2),
            "height": box.get("height", 0.2),
        },
        "anchorPoint": {"x": box.get("anchor_x", 0.2), "y": box.get("anchor_y", 0.2)},
        "attributes": [],
        "confidenceScore": 0.9,
    }


def relation_payload(
    key: str = "near-1",
    relation: str = "next_to",
    subject: str = "chair",
    reference: str = "table",
) -> dict:
    return {
        "relationKey": key,
        "subjectObjectKey": subject,
        "relation": relation,
        "referenceObjectKey": reference,
    }


def valid_payload() -> dict:
    return {
        "suggestedSceneTitle": "Kitchen",
        "objects": [object_payload(), object_payload("table", x=0.4)],
        "relations": [relation_payload()],
    }


def valid_result(
    *,
    objects: list[ModelSceneObject] | None = None,
    relations: list[ModelSceneRelation] | None = None,
) -> SceneAnalysisModelResult:
    return SceneAnalysisModelResult(
        suggested_scene_title="Kitchen",
        objects=objects
        if objects is not None
        else [
            ModelSceneObject(
                object_key="chair",
                label="chair",
                bounding_box=ModelBoundingBox(x=0.1, y=0.1, width=0.2, height=0.2),
                anchor_point={"x": 0.2, "y": 0.2},
                attributes=[],
                confidence_score=0.9,
            ),
            ModelSceneObject(
                object_key="table",
                label="table",
                bounding_box=ModelBoundingBox(x=0.4, y=0.1, width=0.2, height=0.2),
                anchor_point={"x": 0.5, "y": 0.2},
                attributes=[],
                confidence_score=0.9,
            ),
        ],
        relations=relations or [],
    )


def model_relation(
    *,
    key: str = "relation-1",
    relation: SceneRelationType = SceneRelationType.NEXT_TO,
    subject: str = "chair",
    reference: str = "table",
) -> ModelSceneRelation:
    return ModelSceneRelation(
        relation_key=key,
        subject_object_key=subject,
        relation=relation,
        reference_object_key=reference,
    )


def issue_codes(error: SceneAnalysisValidationError) -> set[SceneAnalysisIssueCode]:
    return {issue.code for issue in error.issues}


def test_valid_payload_round_trips_with_camel_case_aliases() -> None:
    parsed = parse_scene_analysis(valid_payload())
    dumped = parsed.model_dump(mode="json")

    assert parse_scene_analysis(dumped) == parsed
    assert "boundingBox" in dumped["objects"][0]
    assert "subjectObjectKey" in dumped["relations"][0]
    assert "relation" in dumped["relations"][0]


def test_empty_objects_array_is_accepted() -> None:
    payload = {"suggestedSceneTitle": "Blurry Photo", "objects": [], "relations": []}

    parsed = parse_scene_analysis(payload)

    assert parsed.objects == []
    assert parsed.relations == []


@pytest.mark.parametrize(
    "extra",
    [
        {"unexpected": True},
        {"objects": [{**object_payload(), "unexpected": True}, object_payload("table")]},
        {
            "objects": [
                {
                    **object_payload(),
                    "boundingBox": {**object_payload()["boundingBox"], "unexpected": True},
                },
                object_payload("table"),
            ]
        },
        {
            "objects": [object_payload(), object_payload("table")],
            "relations": [{**relation_payload(), "unexpected": True}],
        },
    ],
)
def test_extra_properties_are_reported_as_invalid_schema(extra: dict) -> None:
    payload = valid_payload()
    payload.update(extra)

    with pytest.raises(SceneAnalysisValidationError) as raised:
        parse_scene_analysis(payload)

    assert issue_codes(raised.value) == {SceneAnalysisIssueCode.INVALID_SCHEMA}
    assert not isinstance(raised.value, ValidationError)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [("objects", "confidenceScore", 1.1), ("relations", "relation", "holding")],
)
def test_out_of_range_values_are_rejected_at_schema_level(
    section: str, field: str, value: float
) -> None:
    payload = valid_payload()
    payload[section][0][field] = value

    with pytest.raises(SceneAnalysisValidationError) as raised:
        parse_scene_analysis(payload)

    assert issue_codes(raised.value) == {SceneAnalysisIssueCode.INVALID_SCHEMA}


def test_duplicate_object_key() -> None:
    result = valid_result(
        objects=[
            valid_result().objects[0],
            valid_result().objects[0],
        ]
    )

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(result)

    assert SceneAnalysisIssueCode.DUPLICATE_OBJECT_KEY in issue_codes(raised.value)


def test_duplicate_relation_key() -> None:
    relations = [
        model_relation(key="same", relation=SceneRelationType.ABOVE),
        model_relation(key="same", relation=SceneRelationType.BELOW),
    ]

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=relations))

    assert SceneAnalysisIssueCode.DUPLICATE_RELATION_KEY in issue_codes(raised.value)


def test_non_finite_bounding_box() -> None:
    scene_object = valid_result().objects[0]
    scene_object.bounding_box.x = math.inf

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))

    assert SceneAnalysisIssueCode.NON_FINITE_BOUNDING_BOX in issue_codes(raised.value)


def test_bounding_box_out_of_range() -> None:
    scene_object = valid_result().objects[0]
    scene_object.bounding_box.x = -0.1

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))

    assert SceneAnalysisIssueCode.BOUNDING_BOX_OUT_OF_RANGE in issue_codes(raised.value)


def test_non_positive_bounding_box_size() -> None:
    scene_object = valid_result().objects[0]
    scene_object.bounding_box.width = 0

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))

    assert SceneAnalysisIssueCode.NON_POSITIVE_BOUNDING_BOX_SIZE in issue_codes(raised.value)


def test_bounding_box_outside_image() -> None:
    scene_object = valid_result().objects[0]
    scene_object.bounding_box.x = 0.9
    scene_object.bounding_box.width = 0.2

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))

    assert SceneAnalysisIssueCode.BOUNDING_BOX_OUTSIDE_IMAGE in issue_codes(raised.value)


def test_unknown_relation_object() -> None:
    relation = model_relation(subject="missing", reference="also-missing")

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=[relation]))

    assert SceneAnalysisIssueCode.UNKNOWN_RELATION_OBJECT in issue_codes(raised.value)
    assert len(
        [
            issue
            for issue in raised.value.issues
            if issue.code is SceneAnalysisIssueCode.UNKNOWN_RELATION_OBJECT
        ]
    ) == 2


def test_self_relation() -> None:
    relation = model_relation(subject="chair", reference="chair")

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=[relation]))

    assert SceneAnalysisIssueCode.SELF_RELATION in issue_codes(raised.value)


def test_duplicate_relation() -> None:
    relations = [
        model_relation(key="first", relation=SceneRelationType.ABOVE),
        model_relation(key="second", relation=SceneRelationType.ABOVE),
    ]

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=relations))

    assert SceneAnalysisIssueCode.DUPLICATE_RELATION in issue_codes(raised.value)


def test_symmetric_duplicate_relation_but_not_non_symmetric_reverse() -> None:
    symmetric = [
        model_relation(key="first"),
        model_relation(key="second", subject="table", reference="chair"),
    ]
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=symmetric))
    assert SceneAnalysisIssueCode.SYMMETRIC_DUPLICATE_RELATION in issue_codes(raised.value)

    non_symmetric = [
        model_relation(key="first", relation=SceneRelationType.ABOVE),
        model_relation(
            key="second",
            relation=SceneRelationType.ABOVE,
            subject="table",
            reference="chair",
        ),
    ]
    validate_scene_analysis(valid_result(relations=non_symmetric))


def test_validator_collects_violations_across_the_whole_payload() -> None:
    duplicate_object = valid_result().objects[0]
    duplicate_object.bounding_box.x = math.nan
    relations = [
        model_relation(key="same", subject="missing"),
        model_relation(key="same", subject="chair", reference="chair"),
    ]

    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(
            valid_result(
                objects=[duplicate_object, duplicate_object],
                relations=relations,
            )
        )

    assert issue_codes(raised.value) >= {
        SceneAnalysisIssueCode.DUPLICATE_OBJECT_KEY,
        SceneAnalysisIssueCode.DUPLICATE_RELATION_KEY,
        SceneAnalysisIssueCode.NON_FINITE_BOUNDING_BOX,
        SceneAnalysisIssueCode.UNKNOWN_RELATION_OBJECT,
        SceneAnalysisIssueCode.SELF_RELATION,
    }


def test_relation_aliases_resolve_to_canonical_types() -> None:
    for alias, expected in [
        ("in", SceneRelationType.INSIDE),
        ("insideOf", SceneRelationType.INSIDE),
        ("inside_of", SceneRelationType.INSIDE),
        ("beside", SceneRelationType.NEXT_TO),
        ("leftOf", SceneRelationType.LEFT_OF),
        ("rightOf", SceneRelationType.RIGHT_OF),
        ("inFrontOf", SceneRelationType.IN_FRONT_OF),
        ("nextTo", SceneRelationType.NEXT_TO),
    ]:
        payload = valid_payload()
        payload["relations"][0]["relation"] = alias
        assert parse_scene_analysis(payload).relations[0].relation is expected


def test_non_finite_and_out_of_range_anchor_points() -> None:
    scene_object = valid_result().objects[0]
    scene_object.anchor_point = ModelAnchorPoint(x=math.nan, y=0.5)
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))
    assert (
        SceneAnalysisIssueCode.NON_FINITE_ANCHOR_POINT in issue_codes(raised.value)
    )

    scene_object.anchor_point = ModelAnchorPoint(x=1.5, y=0.5)
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))
    assert (
        SceneAnalysisIssueCode.ANCHOR_POINT_OUT_OF_RANGE in issue_codes(raised.value)
    )


def test_in_box_anchor_outside_image_bounds_is_out_of_range() -> None:
    scene_object = valid_result().objects[0]
    scene_object.anchor_point = ModelAnchorPoint(x=-0.2, y=0.5)
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))
    assert (
        SceneAnalysisIssueCode.ANCHOR_POINT_OUT_OF_RANGE in issue_codes(raised.value)
    )


def test_non_finite_confidence_is_reported() -> None:
    scene_object = valid_result().objects[0]
    object.__setattr__(scene_object, "confidence_score", math.nan)
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(objects=[scene_object]))
    assert SceneAnalysisIssueCode.NON_FINITE_CONFIDENCE in issue_codes(raised.value)


def test_inverse_duplicate_relation() -> None:
    relations = [
        model_relation(key="first", relation=SceneRelationType.LEFT_OF),
        model_relation(
            key="second",
            relation=SceneRelationType.RIGHT_OF,
            subject="table",
            reference="chair",
        ),
    ]
    with pytest.raises(SceneAnalysisValidationError) as raised:
        validate_scene_analysis(valid_result(relations=relations))
    assert (
        SceneAnalysisIssueCode.INVERSE_DUPLICATE_RELATION
        in issue_codes(raised.value)
    )


def test_non_inverse_reversed_relation_is_allowed() -> None:
    relations = [
        model_relation(key="first", relation=SceneRelationType.LEFT_OF),
        model_relation(
            key="second",
            relation=SceneRelationType.LEFT_OF,
            subject="table",
            reference="chair",
        ),
    ]
    validate_scene_analysis(valid_result(relations=relations))


def test_invalid_result_is_rejected_without_repairing_or_mutating_it() -> None:
    result = valid_result()
    result.objects[0].bounding_box.x = 2
    before = copy.deepcopy(result)

    with pytest.raises(SceneAnalysisValidationError):
        validate_scene_analysis(result)

    assert result == before
    assert result.objects[0].bounding_box.x == 2
