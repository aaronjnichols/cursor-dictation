from __future__ import annotations

from cursor_dictation.core.models import AppState
from cursor_dictation.ui.status_overlay import StatusOverlay


def test_overlay_maps_runtime_states_to_short_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.set_state(AppState.RECORDING)
    assert overlay.status_text == "Recording..."
    assert overlay.is_active

    overlay.set_state(AppState.TRANSCRIBING)
    assert overlay.status_text == "Transcribing locally..."
    assert overlay.is_active

    overlay.set_state(AppState.IDLE)
    assert overlay.status_text == "Ready"
    assert not overlay.is_active


def test_overlay_can_show_busy_copy_and_error_feedback(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.show_busy()
    assert overlay.status_text == "Transcribing..."

    overlay.show_copied()
    assert overlay.status_text == "Copied"

    overlay.show_error("Microphone unavailable")
    assert overlay.status_text == "Microphone unavailable"
