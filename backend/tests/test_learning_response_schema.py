"""Provider schemas must express requirements before a paid generation happens."""

import json

import httpx
import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from app.ai.features.learning_tasks import (
    LearningTaskService,
    scene_generation_response_model,
)
from app.ai.observability import NoOpAITracer
from app.ai.text_model import TextModelConfig
from app.ai.text_openai import OpenAITextClient
from app.services.vision_model import build_strict_json_schema
from tests.test_learning_task_service import INPUT, tasks


def test_outgoing_provider_schema_preserves_question_and_reference_counts():
    # Test our actual wire schema, not the SDK's separate schema converter.
    schema = build_strict_json_schema(scene_generation_response_model(INPUT))
    for focus, task in schema["properties"].items():
        questions = task["properties"]["questions"]
        assert questions["minItems"] == 2
        assert questions["maxItems"] == 4
        fields = questions["items"]["properties"]
        assert fields["objectKeys"]["minItems"] == 1
        if focus == "chainedDescription":
            assert fields["tokenBank"]["minItems"] == 1
            assert fields["options"]["maxItems"] == 0
        else:
            assert fields["options"]["minItems"] == 4
            assert fields["options"]["maxItems"] == 4


@pytest.mark.parametrize("focus", ["sceneDescription", "chainedDescription"])
def test_provider_schema_requires_nonnullable_english_translation(focus):
    model = scene_generation_response_model(INPUT)
    schema = to_strict_json_schema(model)
    task_ref = schema["properties"][focus]["$ref"].split("/")[-1]
    task = schema["$defs"][task_ref]
    question_ref = task["properties"]["questions"]["items"]["$ref"].split("/")[-1]
    question = schema["$defs"][question_ref]
    assert "translation" in question["required"]
    assert question["properties"]["translation"]["type"] == "string"
    assert question["properties"]["translation"]["minLength"] == 1


@pytest.mark.parametrize("focus", ["sceneDescription", "chainedDescription"])
@pytest.mark.parametrize("translation", [None, "", "   "])
def test_description_cannot_parse_without_usable_translation(focus, translation):
    model = scene_generation_response_model(INPUT)
    payload = {task["focus"]: task for task in tasks()["tasks"]}
    payload[focus]["questions"][0]["translation"] = translation
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("focus", [
    "genderNumberAgreement", "pluralNounForm", "sceneDescription", "chainedDescription"
])
def test_empty_scene_references_are_forbidden_in_provider_schema(focus):
    model = scene_generation_response_model(INPUT)
    schema = to_strict_json_schema(model)
    task = schema["$defs"][schema["properties"][focus]["$ref"].split("/")[-1]]
    question = schema["$defs"][
        task["properties"]["questions"]["items"]["$ref"].split("/")[-1]
    ]
    assert question["properties"]["objectKeys"]["minItems"] == 1
    assert question["properties"]["objectKeys"]["items"]["enum"] == ["object_1", "object_2"]
    payload = {task["focus"]: task for task in tasks()["tasks"]}
    payload[focus]["questions"][0]["objectKeys"] = []
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_schema_rejects_ids_from_another_scene():
    model = scene_generation_response_model(INPUT)
    payload = {task["focus"]: task for task in tasks()["tasks"]}
    payload["genderNumberAgreement"]["questions"][0]["objectKeys"] = ["unrelated-object"]
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_strict_schema_parsing_preserves_translations_through_provider():
    """Exercise the real adapter + service end to end without network/credits."""
    calls = []
    lesson = {
        task["focus"]: {key: value for key, value in task.items() if key != "focus"}
        for task in tasks()["tasks"]
    }

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "status": "completed", "model": "test-model", "error": None,
            "incomplete_details": None, "instructions": None,
            "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "output": [{
                "id": "msg_test", "type": "message", "role": "assistant",
                "status": "completed", "content": [{
                    "type": "output_text", "text": json.dumps(lesson), "annotations": [],
                }],
            }],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        })

    client = OpenAITextClient(
        "not-a-real-key",
        TextModelConfig(model_name="test-model"),
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    result = LearningTaskService(
        client,
        TextModelConfig(model_name="test-model"),
        tracer=NoOpAITracer(),
        provider="openai",
    ).generate(INPUT)

    assert len(calls) == 1
    sent_format = calls[0]["text"]["format"]
    sent_questions = sent_format["schema"]["properties"]["chainedDescription"][
        "properties"
    ]["questions"]
    assert sent_questions["minItems"] == 2
    assert sent_questions["maxItems"] == 4
    assert sent_format["strict"] is True
    assert sent_format["schema"] == build_strict_json_schema(
        scene_generation_response_model(INPUT)
    )
    assert result.tasks[2].questions[0].translation == "The cup is red."
    assert result.tasks[3].questions[0].translation == "The red cup is on the table."
    assert result.tasks[3].questions[0].token_bank
