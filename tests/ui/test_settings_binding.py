from __future__ import annotations

from dataclasses import replace

from cursor_dictation.audio.recorder import AudioDevice
from cursor_dictation.settings.schema import AppSettings
from cursor_dictation.ui.settings_window import SettingsWindow


def test_settings_window_round_trips_user_editable_values(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)
    settings = replace(
        AppSettings(),
        hold_to_talk_hotkey="Ctrl+Shift+Space",
        microphone_device_id="wasapi:usb-mic",
        model_path=r"C:\models\small.en",
        sound_cues_enabled=False,
        history_enabled=True,
        launch_at_sign_in=True,
    )
    devices = (
        AudioDevice(
            id="wasapi:default",
            name="Laptop microphone",
            max_input_channels=2,
            default_sample_rate=48_000,
            is_default=True,
        ),
        AudioDevice(
            id="wasapi:usb-mic",
            name="USB microphone",
            max_input_channels=1,
            default_sample_rate=44_100,
        ),
    )

    window.apply_settings(settings, vocabulary=("HEC-RAS", "FLO-2D"), devices=devices)
    collected, vocabulary = window.collect_settings()

    assert collected == settings
    assert vocabulary == ("HEC-RAS", "FLO-2D")
    assert window.microphone.currentText() == "USB microphone"


def test_missing_pinned_microphone_falls_back_to_windows_default(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)
    settings = replace(AppSettings(), microphone_device_id="missing-device")

    window.apply_settings(settings, vocabulary=(), devices=())
    collected, _ = window.collect_settings()

    assert collected.microphone_device_id is None
    assert window.microphone.currentText() == "Windows default"
