from __future__ import annotations

from dataclasses import dataclass, field

from cursor_dictation.core.models import DeliveryMethod
from cursor_dictation.output.delivery import WindowsTextDelivery


@dataclass
class FakeClipboard:
    copied: list[str] = field(default_factory=list)
    transactions: list[str] = field(default_factory=list)
    fail_transaction: bool = False

    def copy_text(self, text: str) -> None:
        self.copied.append(text)

    def paste_transaction(self, text: str, send_paste) -> bool:  # type: ignore[no-untyped-def]
        self.transactions.append(text)
        if self.fail_transaction:
            raise RuntimeError("clipboard unavailable")
        return bool(send_paste())


@dataclass
class FakeKeyboard:
    paste_result: bool = True
    unicode_result: bool = True
    paste_count: int = 0
    unicode_text: list[str] = field(default_factory=list)

    def send_paste(self) -> bool:
        self.paste_count += 1
        return self.paste_result

    def send_unicode(self, text: str) -> bool:
        self.unicode_text.append(text)
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


def test_total_insertion_failure_leaves_text_on_clipboard() -> None:
    clipboard = FakeClipboard(fail_transaction=True)
    keyboard = FakeKeyboard(unicode_result=False)
    delivery = WindowsTextDelivery(clipboard, keyboard, FakeForeground())

    result = delivery.insert_at_cursor("keep me")

    assert not result.success
    assert result.recoverable
    assert result.error_code == "insertion_failed_copied"
    assert clipboard.copied == ["keep me"]


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
