from services.diet_state import DietState


def test_diet_state_round_trip(tmp_path):
    state = DietState(tmp_path)

    assert state.get_today()["water_count"] == 0
    state.set_water_count(5)
    state.set_vitamins_taken(True)

    entry_id = state.add_calorie_entry("2 eggs and toast")
    assert state.pending_or_failed_entries_today()[0]["entry_id"] == entry_id
    assert state.total_calories_today() == 0

    state.resolve_calorie_entry(entry_id, 350.0)
    assert state.total_calories_today() == 350.0
    assert not state.has_failed_entries_today()

    entry_id_2 = state.add_calorie_entry("a burger")
    state.fail_calorie_entry(entry_id_2)
    assert state.has_failed_entries_today()
    assert [e["entry_id"] for e in state.pending_or_failed_entries_today()] == [entry_id_2]

    # Reload from disk to confirm persistence.
    reloaded = DietState(tmp_path)
    day = reloaded.get_today()
    assert day["water_count"] == 5
    assert day["vitamins_taken"] is True
    assert reloaded.total_calories_today() == 350.0
