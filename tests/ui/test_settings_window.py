from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from cursor_dictation.core.models import DeliveryMode
from cursor_dictation.settings.history import HistoryRecord
from cursor_dictation.settings.schema import ModelSource
from cursor_dictation.ui.settings_window import SettingsWindow


def test_settings_window_has_all_agreed_pages(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)

    assert window.page_names == (
        "General",
        "Hotkeys",
        "Audio",
        "Model",
        "Vocabulary",
        "History",
        "About",
    )


def test_settings_window_emits_save_and_close_requests(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.save_requested):
        window.save_button.click()

    window.show()
    with qtbot.waitSignal(window.close_requested):
        window.close()


def test_model_picker_and_recommended_model_controls(qtbot, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)
    model_path = tmp_path / "model"
    model_path.mkdir()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(model_path),
    )

    window.choose_model_button.click()
    assert Path(window.model_path.text()) == model_path
    selected, _ = window.collect_settings()
    assert selected.model_source is ModelSource.CUSTOM

    window.use_default_model_button.click()
    assert window.model_path.text() == ""
    selected, _ = window.collect_settings()
    assert selected.model_source is ModelSource.RECOMMENDED


def test_history_clear_signal_and_inline_status(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.clear_history_requested):
        window.clear_history_button.click()

    window.set_status("Saved")
    assert window.status_text == "Saved"
    window.set_status("Could not save", error=True)
    assert window.status_text == "Could not save"
    assert window.status_label.property("error") is True


def test_history_records_can_be_selected_and_copied(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)
    records = (
        HistoryRecord(
            timestamp=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
            text="First transcript",
            delivery_mode=DeliveryMode.INSERT,
        ),
        HistoryRecord(
            timestamp=datetime(2026, 9, 19, 12, 1, tzinfo=UTC),
            text="Most recent transcript",
            delivery_mode=DeliveryMode.COPY,
        ),
    )

    window.apply_history(records)
    window.history_list.setCurrentRow(0)

    with qtbot.waitSignal(
        window.copy_history_requested,
        check_params_cb=lambda text: text == "Most recent transcript",
    ):
        window.copy_history_button.click()
    assert window.history_record_count == 2


def test_settings_form_can_be_locked_during_model_validation(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)

    window.set_editing_enabled(False)
    assert not window.stack.isEnabled()
    assert not window.navigation.isEnabled()
    assert not window.save_button.isEnabled()
    assert not window.close_button.isEnabled()
    window.show()
    window.close()
    assert window.isVisible()

    window.set_editing_enabled(True)
    assert window.stack.isEnabled()
    assert window.navigation.isEnabled()
    assert window.save_button.isEnabled()
    assert window.close_button.isEnabled()


def test_microphone_test_control_emits_and_displays_input_level(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = SettingsWindow()
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.microphone_test_requested):
        window.test_microphone_button.click()

    window.set_microphone_test_active(True)
    window.set_input_level(0.42)
    assert window.test_microphone_button.text() == "Stop test"
    assert window.input_level.value() == 42

    window.set_microphone_test_active(False)
    assert window.test_microphone_button.text() == "Test microphone"
    assert window.input_level.value() == 0
