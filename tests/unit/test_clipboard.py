from __future__ import annotations

from contextlib import suppress

import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QColor, QGuiApplication, QImage

from cursor_dictation.output.clipboard import MimeSnapshot, QtClipboard
from cursor_dictation.output.delivery import ClipboardTransactionError


@pytest.fixture
def system_clipboard(qtbot):  # type: ignore[no-untyped-def]
    application = QGuiApplication.instance()
    assert isinstance(application, QGuiApplication)
    clipboard = application.clipboard()
    clipboard.clear(QClipboard.Mode.Clipboard)
    yield clipboard
    clipboard.clear(QClipboard.Mode.Clipboard)
    application.processEvents()


def test_mime_snapshot_round_trips_text_html_and_files() -> None:
    source = QMimeData()
    source.setText("plain text")
    source.setHtml("<b>rich text</b>")
    source.setUrls([QUrl.fromLocalFile("C:/Temp/example.txt")])

    restored = MimeSnapshot.capture(source).to_mime_data()

    assert restored.text() == "plain text"
    assert restored.html() == "<b>rich text</b>"
    assert restored.urls() == [QUrl.fromLocalFile("C:/Temp/example.txt")]


def test_mime_snapshot_round_trips_qt_image_data() -> None:
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("#2ea043"))
    source = QMimeData()
    source.setImageData(image)

    restored = MimeSnapshot.capture(source).to_mime_data()

    restored_image = restored.imageData()
    assert isinstance(restored_image, QImage)
    assert restored_image.size() == image.size()
    assert restored_image.pixelColor(0, 0) == QColor("#2ea043")


def test_empty_clipboard_snapshot_round_trips() -> None:
    restored = MimeSnapshot.capture(None).to_mime_data()

    assert restored.formats() == []


def test_failed_paste_restores_the_original_clipboard(system_clipboard) -> None:  # type: ignore[no-untyped-def]
    clipboard = system_clipboard
    original = QMimeData()
    original.setText("original text")
    original.setHtml("<b>original text</b>")
    clipboard.setMimeData(original, QClipboard.Mode.Clipboard)
    adapter = QtClipboard(clipboard, restore_delay_ms=0)

    pasted = adapter.paste_transaction("dictated text", lambda: False)

    assert not pasted
    assert clipboard.text(QClipboard.Mode.Clipboard) == "original text"
    assert clipboard.mimeData(QClipboard.Mode.Clipboard).html() == "<b>original text</b>"


def test_paste_exception_restores_the_original_clipboard(system_clipboard) -> None:  # type: ignore[no-untyped-def]
    clipboard = system_clipboard
    clipboard.setText("keep", QClipboard.Mode.Clipboard)
    adapter = QtClipboard(clipboard, restore_delay_ms=0)

    def failed_paste() -> bool:
        raise RuntimeError("injection failed")

    with suppress(RuntimeError):
        adapter.paste_transaction("temporary", failed_paste)

    assert clipboard.text(QClipboard.Mode.Clipboard) == "keep"


def test_restore_failure_preserves_whether_paste_succeeded() -> None:
    class FailingRestoreClipboard:
        def __init__(self) -> None:
            self.mime_data = QMimeData()
            self.mime_data.setText("original")
            self.set_count = 0

        def mimeData(self, _mode: QClipboard.Mode) -> QMimeData:
            return self.mime_data

        def setMimeData(self, mime_data: QMimeData, _mode: QClipboard.Mode) -> None:
            self.set_count += 1
            if self.set_count == 2:
                raise RuntimeError("clipboard owner disappeared")
            self.mime_data = mime_data

    clipboard = FailingRestoreClipboard()
    adapter = QtClipboard(clipboard, restore_delay_ms=0)  # type: ignore[arg-type]

    with pytest.raises(ClipboardTransactionError) as captured:
        adapter.paste_transaction("dictated", lambda: True)

    assert captured.value.paste_succeeded


def test_owner_query_failure_after_paste_preserves_success() -> None:
    class FailingOwnerQueryClipboard:
        def __init__(self) -> None:
            self.mime_data = QMimeData()
            self.mime_data.setText("original")
            self.read_count = 0

        def mimeData(self, _mode: QClipboard.Mode) -> QMimeData:
            self.read_count += 1
            if self.read_count == 2:
                raise RuntimeError("clipboard became unavailable")
            return self.mime_data

        def setMimeData(self, mime_data: QMimeData, _mode: QClipboard.Mode) -> None:
            self.mime_data = mime_data

    clipboard = FailingOwnerQueryClipboard()
    adapter = QtClipboard(clipboard, restore_delay_ms=0)  # type: ignore[arg-type]

    with pytest.raises(ClipboardTransactionError) as captured:
        adapter.paste_transaction("dictated", lambda: True)

    assert captured.value.paste_succeeded
