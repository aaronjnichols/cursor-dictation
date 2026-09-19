from __future__ import annotations

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
