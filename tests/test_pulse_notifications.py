from services.pulse_models import PulseSliders
from services.pulse_notifications import render_pulse_reach_out_details


def test_render_pulse_reach_out_details_includes_negative_sliders_and_message() -> None:
    details = render_pulse_reach_out_details(
        PulseSliders(energy=-3, faith=1, encouragement=-2, temptation=-4),
        "Hey guys, I feel discouraged and tired tonight.",
    )

    assert "Pulse:" in details
    assert "Energy: -3" in details
    assert "Encouragement: -2" in details
    assert "Temptation: -4" in details
    assert "Faith:" not in details
    assert "Shane submitted a pulse check and may need encouragement." in details
    assert "Hey guys, I feel discouraged and tired tonight." in details