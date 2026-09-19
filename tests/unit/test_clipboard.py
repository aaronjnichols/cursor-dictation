from __future__ import annotations

from PySide6.QtCore import QMimeData, QUrl

from cursor_dictation.output.clipboard import MimeSnapshot


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
