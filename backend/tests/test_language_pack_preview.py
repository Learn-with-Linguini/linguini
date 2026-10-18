import json
from pathlib import Path

from app.language_packs.preview import main

PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


def test_validate_and_capability_cli(capsys):
    assert main(["validate", "--pack-dir", str(PACK)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated == {
        "valid": True,
        "pack_id": "es-es-everyday",
        "language": "es",
        "evaluation_cases": 19,
    }

    assert main([
        "capability",
        "--pack-dir", str(PACK),
        "--language", "es",
        "--register", "everyday",
    ]) == 0
    capabilities = json.loads(capsys.readouterr().out)
    assert all(item["supported"] for item in capabilities["levels"].values())
    assert all(not item["release_enabled"] for item in capabilities["levels"].values())


def test_plan_cli_preserves_mission_slot_order(tmp_path, capsys):
    scene = tmp_path / "scene.json"
    scene.write_text(json.dumps({"slot_bindings": {}}), encoding="utf-8")
    expected = {
        "A0": [
            "matchName-1", "confirmName-1", "buildIdentify-1",
            "matchName-2", "confirmName-2", "buildIdentify-2",
        ],
        "A1": [
            "confirmObject-1", "confirmObject-2", "chooseAttribute",
            "describeObject",
        ],
        "A2": [
            "chooseSceneMarker", "buildSceneFact", "chooseSceneDescription",
            "buildSceneDescription", "followUpSceneFact",
        ],
    }
    for level, slot_ids in expected.items():
        assert main([
            "plan",
            "--pack-dir", str(PACK),
            "--language", "es",
            "--register", "everyday",
            "--level", level,
            "--scene", str(scene),
        ]) == 0
        output = json.loads(capsys.readouterr().out)
        assert [slot["slot_id"] for slot in output["plan"]["slots"]] == slot_ids
