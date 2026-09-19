from __future__ import annotations

from pathlib import Path

from cursor_dictation.audio.recorder import AudioDevice
from cursor_dictation.ui.setup_window import SetupWindow


def test_setup_explains_local_processing_and_requests_install(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SetupWindow()
    qtbot.addWidget(window)

    assert "runs on this computer" in window.explanation_text.lower()
    assert "small.en" in window.model_name.lower()

    with qtbot.waitSignal(window.install_requested):
        window.install_button.click()


def test_setup_progress_disables_install_button(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SetupWindow()
    qtbot.addWidget(window)

    window.set_progress(42, "Verifying files...")

    assert window.progress_bar.value() == 42
    assert window.progress_text == "Verifying files..."
    assert not window.install_button.isEnabled()


def test_setup_binds_install_location_and_microphone_choice(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = SetupWindow()
    qtbot.addWidget(window)
    devices = (
        AudioDevice(
            id="wasapi:built-in",
            name="Built-in microphone",
            max_input_channels=2,
            default_sample_rate=48_000,
            is_default=True,
        ),
        AudioDevice(
            id="wasapi:usb",
            name="USB microphone",
            max_input_channels=1,
            default_sample_rate=48_000,
        ),
    )

    window.set_install_location(tmp_path)
    window.apply_devices(devices, selected_device_id="wasapi:usb")

    assert window.install_root == tmp_path
    assert window.selected_microphone_id == "wasapi:usb"
    assert window.microphone.currentText() == "USB microphone"


def test_title_bar_close_requests_setup_dismissal(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SetupWindow()
    qtbot.addWidget(window)
    window.show()

    with qtbot.waitSignal(window.dismiss_requested):
        window.close()

    assert window.isVisible()
