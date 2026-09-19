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


class ClipboardTransactionError(RuntimeError):
    def __init__(self, *, paste_succeeded: bool) -> None:
        super().__init__("The clipboard transaction could not restore the prior contents")
        self.paste_succeeded = paste_succeeded


class PartialUnicodeInputError(RuntimeError):
    def __init__(self, *, remaining_text: str) -> None:
        super().__init__("Windows stopped accepting Unicode input")
        self.remaining_text = remaining_text


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
        except ClipboardTransactionError as error:
            if error.paste_succeeded:
                return DeliveryResult.failed(
                    DeliveryMethod.CLIPBOARD_PASTE,
                    error_code="clipboard_restore_failed_after_paste",
                    recoverable=True,
                )
            pasted = False
        except Exception:
            pasted = False
        else:
            if pasted:
                return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

        remaining_text = text
        try:
            if self._keyboard.send_unicode(text):
                return DeliveryResult.ok(DeliveryMethod.UNICODE_INPUT)
        except PartialUnicodeInputError as error:
            remaining_text = error.remaining_text
        except Exception:
            pass

        try:
            self._clipboard.copy_text(remaining_text)
        except Exception:
            return DeliveryResult.failed(
                DeliveryMethod.CLIPBOARD_COPY,
                error_code="insertion_and_copy_failed",
                recoverable=True,
            )
        if remaining_text != text:
            return DeliveryResult.failed(
                DeliveryMethod.CLIPBOARD_COPY,
                error_code="partial_insertion_remaining_copied",
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
