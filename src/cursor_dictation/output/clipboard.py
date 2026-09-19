from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QByteArray, QEventLoop, QMimeData, QTimer
from PySide6.QtGui import QClipboard, QGuiApplication


@dataclass(frozen=True, slots=True)
class MimeSnapshot:
    payloads: tuple[tuple[str, bytes], ...]

    @classmethod
    def capture(cls, mime_data: QMimeData | None) -> MimeSnapshot:
        if mime_data is None:
            return cls(payloads=())
        return cls(
            payloads=tuple(
                (mime_type, _copy_bytes(mime_data.data(mime_type).data()))
                for mime_type in mime_data.formats()
            )
        )

    def to_mime_data(self) -> QMimeData:
        mime_data = QMimeData()
        for mime_type, payload in self.payloads:
            mime_data.setData(mime_type, QByteArray(payload))
        return mime_data


class QtClipboard:
    _OWNER_FORMAT = "application/x-cursor-dictation-owner"

    def __init__(
        self,
        clipboard: QClipboard | None = None,
        *,
        restore_delay_ms: int = 140,
    ) -> None:
        if clipboard is None:
            application = QGuiApplication.instance()
            if not isinstance(application, QGuiApplication):
                raise RuntimeError("A Qt application must exist before using the clipboard.")
            clipboard = application.clipboard()
        self._clipboard = clipboard
        self._restore_delay_ms = restore_delay_ms

    def copy_text(self, text: str) -> None:
        self._clipboard.setText(text, QClipboard.Mode.Clipboard)

    def paste_transaction(self, text: str, send_paste: Callable[[], bool]) -> bool:
        snapshot = MimeSnapshot.capture(self._clipboard.mimeData(QClipboard.Mode.Clipboard))
        owner_token = uuid4().hex.encode("ascii")
        payload = QMimeData()
        payload.setText(text)
        payload.setData(self._OWNER_FORMAT, QByteArray(owner_token))
        self._clipboard.setMimeData(payload, QClipboard.Mode.Clipboard)

        try:
            pasted = send_paste()
            if pasted:
                self._wait_for_target()
            return pasted
        finally:
            current = self._clipboard.mimeData(QClipboard.Mode.Clipboard)
            if current is not None and current.data(self._OWNER_FORMAT).data() == owner_token:
                self._clipboard.setMimeData(snapshot.to_mime_data(), QClipboard.Mode.Clipboard)

    def _wait_for_target(self) -> None:
        if self._restore_delay_ms <= 0:
            return
        loop = QEventLoop()
        QTimer.singleShot(self._restore_delay_ms, loop.quit)
        loop.exec()


def _copy_bytes(value: bytes | bytearray | memoryview[int]) -> bytes:
    return value if isinstance(value, bytes) else bytes(value)
