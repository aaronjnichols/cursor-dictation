from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from cursor_dictation.core.models import DeliveryMethod, DeliveryResult


class ClipboardPort(Protocol):
    def copy_text(self, text: str) -> None: ...

    def paste_transaction(self, text: str, send_paste: Callable[[], bool]) -> bool: ...


class KeyboardPort(Protocol):
    def send_paste(self) -> bool: ...

    def send_unicode(self, text: str) -> bool: ...


class ForegroundPort(Protocol):
    def belongs_to_current_process(self) -> bool: ...


class WindowsTextDelivery:
    def __init__(
        self,
        clipboard: ClipboardPort,
        keyboard: KeyboardPort,
        foreground: ForegroundPort,
    ) -> None:
        self._clipboard = clipboard
        self._keyboard = keyboard
        self._foreground = foreground

    def insert_at_cursor(self, text: str) -> DeliveryResult:
        if self._foreground.belongs_to_current_process():
            return self._copy_as_safe_fallback(text)

        try:
            pasted = self._clipboard.paste_transaction(text, self._keyboard.send_paste)
        except Exception:
            pasted = False
        else:
            if pasted:
                return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

        try:
            if self._keyboard.send_unicode(text):
                return DeliveryResult.ok(DeliveryMethod.UNICODE_INPUT)
        except Exception:
            pass

        try:
            self._clipboard.copy_text(text)
        except Exception:
            return DeliveryResult.failed(
                DeliveryMethod.CLIPBOARD_COPY,
                error_code="insertion_and_copy_failed",
                recoverable=True,
            )
        return DeliveryResult.failed(
            DeliveryMethod.CLIPBOARD_COPY,
            error_code="insertion_failed_copied",
            recoverable=True,
        )

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        try:
            self._clipboard.copy_text(text)
        except Exception:
            return DeliveryResult.failed(
                DeliveryMethod.CLIPBOARD_COPY,
                error_code="copy_failed",
                recoverable=True,
            )
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_COPY)

    def _copy_as_safe_fallback(self, text: str) -> DeliveryResult:
        result = self.copy_to_clipboard(text)
        if result.success:
            return result
        return DeliveryResult.failed(
            DeliveryMethod.CLIPBOARD_COPY,
            error_code="cursor_dictation_has_focus",
            recoverable=True,
        )
