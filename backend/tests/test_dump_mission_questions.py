from app.scripts import dump_mission_questions as dump
from app.services.mission_eligibility import IMPLEMENTED_MISSIONS


def test_mock_dump_is_complete_and_deterministic():
    report = dump.dump_questions()
    assert report == dump.dump_questions()
    assert [(m["mission_id"], m["level"], m["version"]) for m in report["missions"]] == [
        key for keys in IMPLEMENTED_MISSIONS.values() for key in keys
    ]
    for mission in report["missions"]:
        assert "error" not in mission, mission
        assert mission["tasks"]
        for task in mission["tasks"]:
            assert task["questions"]
            for question in task["questions"]:
                assert question["purpose"]
                assert question["correct_option_ids"][0]
                if question["interaction_type"] == "sentenceBuilding":
                    assert question["correct_chunks"]
                    assert question["token_bank"]
    assert "**[correct]**" in dump.markdown(report)


def test_empty_report():
    rendered = dump.markdown({"provider": "mock", "missions": []})
    assert "## Question counts" in rendered
    assert "### M01" not in rendered


def test_failed_missions_are_reported_without_stopping(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("example generation failure")

    monkeypatch.setattr(dump, "generate_pilot", fail)
    report = dump.dump_questions()
    assert len(report["missions"]) == sum(map(len, IMPLEMENTED_MISSIONS.values()))
    assert all(m["error"] == "ValueError: example generation failure" for m in report["missions"])
    assert "Could not build: ValueError: example generation failure" in dump.markdown(report)
