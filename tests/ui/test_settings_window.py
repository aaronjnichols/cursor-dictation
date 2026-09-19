from __future__ import annotations

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
