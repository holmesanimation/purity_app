import time
from types import SimpleNamespace

from services.diet_state import DietState, calories_today_from_notes
from shane_common.notes.model import NoteRow


def test_diet_state_round_trip(tmp_path):
    state = DietState(tmp_path)

    assert state.get_today()["water_count"] == 0
    state.set_water_count(5)
    state.set_vitamins_taken(True)

    reloaded = DietState(tmp_path)
    day = reloaded.get_today()
    assert day["water_count"] == 5
    assert day["vitamins_taken"] is True


def _row(ts, note_id, rev, calories, wall_ts=None):
    ctx = {}
    if calories is not None:
        ctx["calories"] = calories
    return NoteRow(
        ts=ts, wall_ts=time.time() if wall_ts is None else wall_ts,
        context=ctx, note_id=note_id, revision_num=rev, op="create" if rev == 1 else "edit",
    )


def test_calories_today_from_notes_dedups_revisions():
    rows = [
        _row(1, "a", 1, 300.0),
        _row(2, "a", 2, 450.0),  # edit supersedes revision 1
        _row(3, "b", 1, 100.0),
        _row(4, "c", 1, None),  # no calories
        _row(5, "d", 1, 999.0, wall_ts=time.time() - 3 * 86400),  # not today
    ]
    repo = SimpleNamespace(rows_for_owner=lambda owner: rows)
    assert calories_today_from_notes(repo) == 550.0


def test_calories_today_ignores_cleared_calories():
    rows = [_row(1, "a", 1, 300.0), _row(2, "a", 2, None)]
    rows[1].context["calories"] = None
    repo = SimpleNamespace(rows_for_owner=lambda owner: rows)
    assert calories_today_from_notes(repo) == 0.0
