from __future__ import annotations

import ctypes
import os

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QLineEdit

from cursor_dictation.core.hotkeys import HotkeyBindings
from cursor_dictation.output.clipboard import MimeSnapshot, QtClipboard
from cursor_dictation.output.keyboard import Win32Keyboard
from cursor_dictation.platform.windows.hotkeys import WindowsHotkeyService

pytestmark = [
    pytest.mark.windows_integration,
    pytest.mark.skipif(
        os.environ.get("CURSOR_DICTATION_RUN_WINDOWS_INTEGRATION") != "1",
        reason="set CURSOR_DICTATION_RUN_WINDOWS_INTEGRATION=1 to change desktop state",
    ),
]


def test_default_global_hotkeys_register_and_release(qtbot) -> None:  # type: ignore[no-untyped-def]
    del qtbot
    service = WindowsHotkeyService()
    try:
        service.configure(HotkeyBindings.defaults())
    finally:
        service.close()


def test_sendinput_pastes_and_restores_rich_clipboard(qtbot) -> None:  # type: ignore[no-untyped-def]
    application = QGuiApplication.instance()
    assert isinstance(application, QGuiApplication)
    clipboard = application.clipboard()
    user_clipboard = MimeSnapshot.capture(clipboard.mimeData(QClipboard.Mode.Clipboard))
    target = QLineEdit()
    try:
        original = QMimeData()
        original.setText("original clipboard")
        original.setHtml("<b>original clipboard</b>")
        original_urls = [
            QUrl.fromLocalFile("C:/Temp/cursor-dictation-first.txt"),
            QUrl.fromLocalFile("C:/Temp/cursor-dictation-second.txt"),
        ]
        original.setUrls(original_urls)
        original_image = QImage(2, 2, QImage.Format.Format_ARGB32)
        original_image.fill(QColor("#edb449"))
        original.setImageData(original_image)
        clipboard.setMimeData(original, QClipboard.Mode.Clipboard)
        target.show()
        target.activateWindow()
        target.setFocus()
        assert ctypes.windll.user32.SetForegroundWindow(int(target.winId()))
        qtbot.wait(100)
        adapter = QtClipboard(clipboard)
        assert adapter.paste_transaction("live delivery", Win32Keyboard().send_paste)

        qtbot.waitUntil(lambda: target.text() == "live delivery", timeout=2_000)
        restored = clipboard.mimeData(QClipboard.Mode.Clipboard)
        assert restored.text() == "original clipboard"
        assert restored.html() == "<b>original clipboard</b>"
        assert restored.urls() == original_urls
        restored_image = restored.imageData()
        assert isinstance(restored_image, QImage)
        assert restored_image.size() == original_image.size()
        assert restored_image.pixelColor(0, 0) == QColor("#edb449")
    finally:
        target.close()
        clipboard.setMimeData(user_clipboard.to_mime_data(), QClipboard.Mode.Clipboard)
        application.processEvents()
