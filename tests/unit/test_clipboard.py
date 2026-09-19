from __future__ import annotations

from contextlib import suppress

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QGuiApplication

from cursor_dictation.output.clipboard import MimeSnapshot, QtClipboard


def test_mime_snapshot_round_trips_text_html_and_files() -> None:
    source = QMimeData()
    source.setText("plain text")
    source.setHtml("<b>rich text</b>")
    source.setUrls([QUrl.fromLocalFile("C:/Temp/example.txt")])

    restored = MimeSnapshot.capture(source).to_mime_data()

    assert restored.text() == "plain text"
    assert restored.html() == "<b>rich text</b>"
    assert restored.urls() == [QUrl.fromLocalFile("C:/Temp/example.txt")]


def test_empty_clipboard_snapshot_round_trips() -> None:
    restored = MimeSnapshot.capture(None).to_mime_data()

    assert restored.formats() == []


def test_failed_paste_restores_the_original_clipboard(qtbot) -> None:  # type: ignore[no-untyped-def]
    application = QGuiApplication.instance()
    assert isinstance(application, QGuiApplication)
    clipboard = application.clipboard()
    original = QMimeData()
    original.setText("original text")
    original.setHtml("<b>original text</b>")
    clipboard.setMimeData(original, QClipboard.Mode.Clipboard)
    adapter = QtClipboard(clipboard, restore_delay_ms=0)

    pasted = adapter.paste_transaction("dictated text", lambda: False)

    assert not pasted
    assert clipboard.text(QClipboard.Mode.Clipboard) == "original text"
    assert clipboard.mimeData(QClipboard.Mode.Clipboard).html() == "<b>original text</b>"


def test_paste_exception_restores_the_original_clipboard(qtbot) -> None:  # type: ignore[no-untyped-def]
    application = QGuiApplication.instance()
    assert isinstance(application, QGuiApplication)
    clipboard = application.clipboard()
    clipboard.setText("keep", QClipboard.Mode.Clipboard)
    adapter = QtClipboard(clipboard, restore_delay_ms=0)

    def failed_paste() -> bool:
        raise RuntimeError("injection failed")

    with suppress(RuntimeError):
        adapter.paste_transaction("temporary", failed_paste)

    assert clipboard.text(QClipboard.Mode.Clipboard) == "keep"
