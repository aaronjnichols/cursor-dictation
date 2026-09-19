from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog

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

    window.use_default_model_button.click()
    assert window.model_path.text() == ""


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
