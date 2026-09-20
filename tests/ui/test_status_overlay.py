from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QPushButton, QWidget

from cursor_dictation.core.models import AppState
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.theme import build_stylesheet


def test_overlay_maps_runtime_states_to_short_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.set_state(AppState.RECORDING)
    assert overlay.status_text == "LISTENING"
    assert overlay.state_code == "[REC]"
    assert overlay.visual_mode == "audio"
    assert overlay.is_active

    overlay.set_state(AppState.TRANSCRIBING)
    assert overlay.status_text == "TRANSCRIBING"
    assert overlay.state_code == "[TX]"
    assert overlay.visual_mode == "progress"
    assert overlay.is_active

    overlay.set_state(AppState.LOADING_MODEL)
    assert overlay.status_text == "LOADING MODEL"
    assert overlay.is_active

    overlay.set_state(AppState.IDLE)
    assert overlay.status_text == "Ready"
    assert not overlay.is_active


def test_overlay_can_show_busy_copy_and_error_feedback(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.show_busy()
    assert overlay.status_text == "WORKING"

    overlay.show_copied()
    assert overlay.status_text == "COPIED"
    assert overlay.visual_mode == "check"

    overlay.show_error("Microphone unavailable")
    assert overlay.status_text == "MICROPHONE UNAVAILABLE"
    assert overlay.detail_text == "TRY AGAIN"


def test_error_feedback_dismisses_without_clearing_recovery_state(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    overlay.set_state(AppState.ERROR_WITH_TRANSCRIPT)

    overlay.show_error("Copy or discard the transcript")
    overlay._dismiss_feedback()  # type: ignore[attr-defined]

    assert not overlay.isVisible()
    assert not overlay.is_active


def test_empty_transcript_error_has_compact_copy_and_close_button(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    overlay.setStyleSheet(build_stylesheet())
    qtbot.addWidget(overlay)

    overlay.show_error("The recording did not produce any text")

    assert overlay.status_text == "NO SPEECH DETECTED"
    assert overlay.detail_text == "TRY AGAIN"
    assert overlay._dismiss_timer.isActive()  # type: ignore[attr-defined]
    assert overlay._dismiss_timer.interval() == 5000  # type: ignore[attr-defined]
    dismiss = overlay.findChild(QPushButton, "overlayDismiss")
    assert dismiss is not None
    assert dismiss.isVisible()

    qtbot.mouseClick(dismiss, Qt.MouseButton.LeftButton)
    assert not overlay.isVisible()
    assert not overlay.is_active


def test_recording_warns_with_one_minute_left(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    overlay.set_state(AppState.RECORDING)

    overlay._display_recording_time(9 * 60)  # type: ignore[attr-defined]

    assert overlay.status_text == "1 MINUTE LEFT"


def test_recording_waveform_reflects_input_level(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.set_input_level(1.0)

    assert len(overlay.audio_block_heights) == 24
    assert max(overlay.audio_block_heights) == 14
    assert "█" in overlay.waveform_text


def test_overlay_uses_compact_half_scale_geometry(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.set_state(AppState.RECORDING)
    qtbot.waitUntil(overlay.isVisible)

    assert 220 <= overlay.width() <= 240
    assert 44 <= overlay.height() <= 52


def test_transcription_uses_scattered_indeterminate_activity(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    overlay._random.seed(17)
    qtbot.addWidget(overlay)
    overlay.set_state(AppState.TRANSCRIBING)

    initial = overlay.progress_active_cells
    overlay._advance_activity()  # type: ignore[attr-defined]

    assert overlay.progress_active_cells != initial
    assert initial < overlay.progress_active_cells
    assert len({x for x, _ in initial}) > 8
    assert len({y for _, y in initial}) > 8
    assert overlay.detail_text == "LOCAL MODEL"
    assert "%" not in overlay.detail_text


def test_status_and_detail_stay_anchored_through_delivery(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    overlay.setStyleSheet(build_stylesheet())
    qtbot.addWidget(overlay)
    labels = [
        overlay.findChild(QWidget, name)
        for name in ("overlayStatus", "overlayDetail", "overlayVisual")
    ]
    positions = []
    for state in (AppState.RECORDING, AppState.TRANSCRIBING, AppState.DELIVERING, AppState.IDLE):
        overlay.set_state(state)
        if state is AppState.IDLE:
            overlay.show_inserted(word_count=42)
        qtbot.waitUntil(overlay.isVisible)
        overlay.grab()  # Resolve the layout as it will appear on screen.
        positions.append(
            (
                overlay.geometry(),
                [(label.mapTo(overlay, QPoint()), label.size()) for label in labels],
            )
        )

    assert all(position == positions[0] for position in positions)


def test_inserted_feedback_builds_selected_pixel_check_grid(qtbot) -> None:  # type: ignore[no-untyped-def]
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)

    overlay.show_inserted(word_count=42)
    overlay._finish_completion_animation()  # type: ignore[attr-defined]

    assert overlay.state_code == "[OK]"
    assert overlay.status_text == "INSERTED"
    assert overlay.detail_text == "42 WORDS"
    assert overlay.visual_mode == "check"
    assert overlay.completion_grid_size == (24, 14)
    assert overlay.completion_green_cells == frozenset(
        ((column + 2) * 2 + dx, row * 2 + dy + 1)
        for column, row in {
            (5, 0),
            (6, 0),
            (5, 1),
            (6, 1),
            (4, 2),
            (5, 2),
            (0, 3),
            (1, 3),
            (3, 3),
            (4, 3),
            (1, 4),
            (2, 4),
            (3, 4),
            (2, 5),
        }
        for dx in range(2)
        for dy in range(2)
    )
