from __future__ import annotations

from dataclasses import dataclass, field

from cursor_dictation.core.models import DeliveryMethod
from cursor_dictation.output.delivery import (
    ClipboardTransactionError,
    PartialUnicodeInputError,
    WindowsTextDelivery,
)


@dataclass
class FakeClipboard:
    copied: list[str] = field(default_factory=list)
    transactions: list[str] = field(default_factory=list)
    fail_transaction: bool = False
    fail_restore_after_paste: bool = False

    def copy_text(self, text: str) -> None:
        self.copied.append(text)

    def paste_transaction(self, text: str, send_paste) -> bool:  # type: ignore[no-untyped-def]
        self.transactions.append(text)
        if self.fail_transaction:
            raise RuntimeError("clipboard unavailable")
        pasted = bool(send_paste())
        if self.fail_restore_after_paste:
            raise ClipboardTransactionError(paste_succeeded=pasted)
        return pasted


@dataclass
class FakeKeyboard:
    paste_result: bool = True
    unicode_result: bool = True
    paste_count: int = 0
    unicode_text: list[str] = field(default_factory=list)
    remaining_after_failure: str | None = None

    def send_paste(self) -> bool:
        self.paste_count += 1
        return self.paste_result

    def send_unicode(self, text: str) -> bool:
        self.unicode_text.append(text)
        if self.remaining_after_failure is not None:
            raise PartialUnicodeInputError(remaining_text=self.remaining_after_failure)
        return self.unicode_result


@dataclass
class FakeForeground:
    own_window: bool = False

    def belongs_to_current_process(self) -> bool:
        return self.own_window


def test_insert_uses_clipboard_transaction() -> None:
    clipboard = FakeClipboard()
    keyboard = FakeKeyboard()
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("hello")

    assert result.success
    assert result.method is DeliveryMethod.CLIPBOARD_PASTE
    assert clipboard.transactions == ["hello"]
    assert keyboard.paste_count == 1


def test_clipboard_failure_falls_back_to_unicode() -> None:
    clipboard = FakeClipboard(fail_transaction=True)
    keyboard = FakeKeyboard()
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("hello\nworld")

    assert result.success
    assert result.method is DeliveryMethod.UNICODE_INPUT
    assert keyboard.unicode_text == ["hello\nworld"]


def test_restore_failure_after_successful_paste_never_replays_unicode() -> None:
    clipboard = FakeClipboard(fail_restore_after_paste=True)
    keyboard = FakeKeyboard()
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("exactly once")

    assert not result.success
    assert result.method is DeliveryMethod.CLIPBOARD_PASTE
    assert result.error_code == "clipboard_restore_failed_after_paste"
    assert keyboard.paste_count == 1
    assert keyboard.unicode_text == []


def test_total_insertion_failure_leaves_text_on_clipboard() -> None:
    clipboard = FakeClipboard(fail_transaction=True)
    keyboard = FakeKeyboard(unicode_result=False)
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("keep me")

    assert not result.success
    assert result.recoverable
    assert result.error_code == "insertion_failed_copied"
    assert clipboard.copied == ["keep me"]


def test_partial_unicode_failure_copies_only_the_remaining_text() -> None:
    clipboard = FakeClipboard(fail_transaction=True)
    keyboard = FakeKeyboard(remaining_after_failure="remaining")
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("already typed remaining")

    assert not result.success
    assert result.error_code == "partial_insertion_remaining_copied"
    assert clipboard.copied == ["remaining"]


def test_own_window_never_receives_injected_text() -> None:
    clipboard = FakeClipboard()
    keyboard = FakeKeyboard()
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground(own_window=True))

    result = delivery.insert_at_cursor("safe")

    assert result.success
    assert result.method is DeliveryMethod.CLIPBOARD_COPY
    assert clipboard.copied == ["safe"]
    assert keyboard.paste_count == 0


def test_copy_mode_intentionally_leaves_text_on_clipboard() -> None:
    clipboard = FakeClipboard()
    delivery = WindowsTextDelivery(clipboard, FakeKeyboard(), FakeForeground())

    result = delivery.copy_to_clipboard("copied")

    assert result.success
    assert result.method is DeliveryMethod.CLIPBOARD_COPY
    assert clipboard.copied == ["copied"]
