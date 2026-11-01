from app.repositories.postgres.gamification import _badge_level


def _batch(photo, scenario, independent=True):
    return {"photo_identity": photo, "scenario_identity": scenario, "lower_assistance": independent}


def test_no_successful_batch_earns_no_badge():
    assert _badge_level([]) is None


def test_one_successful_batch_earns_taster():
    assert _badge_level([_batch("a", "x")]) == "Taster"


def test_cook_needs_three_photos_two_scenarios_and_two_independent_photos():
    assert _badge_level([_batch("a", "x"), _batch("b", "y"), _batch("c", "y")]) == "Cook"
    assert _badge_level([_batch("a", "x"), _batch("b", "y"), _batch("b", "y")]) == "Taster"
    assert _badge_level(
        [_batch("a", "x"), _batch("b", "y", False), _batch("c", "y", False)]
    ) == "Taster"
