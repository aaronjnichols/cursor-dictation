from __future__ import annotations

from cursor_dictation.core.models import AppState, DeliveryMode
from cursor_dictation.ui.tray import TrayIcon


def test_tray_emits_each_user_command(qtbot) -> None:  # type: ignore[no-untyped-def]
    tray = TrayIcon()

    with qtbot.waitSignal(tray.start_insert_requested):
        tray.start_action.trigger()
    with qtbot.waitSignal(tray.start_copy_requested):
        tray.copy_action.trigger()
    tray.set_state(AppState.RECORDING)
    with qtbot.waitSignal(tray.cancel_requested):
        tray.cancel_action.trigger()
    with qtbot.waitSignal(tray.settings_requested):
        tray.settings_action.trigger()
    with qtbot.waitSignal(tray.quit_requested):
        tray.quit_action.trigger()


def test_tray_actions_follow_application_state() -> None:
    tray = TrayIcon()

    tray.set_state(AppState.IDLE)
    assert tray.start_action.isEnabled()
    assert tray.copy_action.isEnabled()
    assert not tray.cancel_action.isEnabled()

    tray.set_state(AppState.RECORDING)
    assert tray.start_action.isEnabled()
    assert tray.start_action.text() == "Stop dictation"
    assert not tray.copy_action.isEnabled()
    assert tray.cancel_action.isEnabled()

    tray.set_recording_mode(DeliveryMode.COPY)
    assert not tray.start_action.isEnabled()
    assert tray.copy_action.isEnabled()
    assert tray.copy_action.text() == "Stop and copy"

    tray.set_state(AppState.TRANSCRIBING)
    assert not tray.start_action.isEnabled()
    assert not tray.copy_action.isEnabled()
    assert not tray.cancel_action.isEnabled()
