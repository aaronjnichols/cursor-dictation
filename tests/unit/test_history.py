from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from cursor_dictation.core.models import DeliveryMode
from cursor_dictation.settings.history import HistoryRecord, JsonlHistoryStore


def make_record(number: int, *, text: str | None = None) -> HistoryRecord:
    return HistoryRecord(
        timestamp=datetime(2026, 9, 19, 12, number, tzinfo=UTC),
        text=text if text is not None else f"transcript {number}",
        delivery_mode=DeliveryMode.INSERT,
    )


def test_history_is_disabled_by_default_and_does_not_create_a_file(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    store = JsonlHistoryStore(path)

    assert store.enabled is False
    assert store.append_record(make_record(0)) is False
    assert store.load() == ()
    assert not path.exists()


def test_history_round_trip_preserves_copy_text_and_only_allowed_fields(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    transcript = 'First line.\nSecond line with "quotes", café, and a Unicode separator\u2028here.'
    record = make_record(0, text=transcript)
    store = JsonlHistoryStore(path, enabled=True)

    assert store.append_record(record) is True

    loaded = store.load()
    assert loaded == (record,)
    assert loaded[0].copy_text == transcript
    raw_record = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw_record) == {"timestamp", "text", "delivery_mode"}
    assert raw_record["text"] == transcript


def test_history_keeps_only_the_newest_records(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    store = JsonlHistoryStore(path, enabled=True, max_records=3)

    for number in range(5):
        store.append_record(make_record(number))

    assert [record.text for record in store.load()] == [
        "transcript 2",
        "transcript 3",
        "transcript 4",
    ]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_clear_removes_only_the_history_file_even_when_history_is_disabled(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    path.write_text("old history", encoding="utf-8")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("keep me", encoding="utf-8")

    JsonlHistoryStore(path).clear()

    assert not path.exists()
    assert settings_path.read_text(encoding="utf-8") == "keep me"


def test_text_append_matches_the_application_history_contract(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    store = JsonlHistoryStore(path, enabled=True)

    store.append("Copied words", "copy")

    record = store.load()[0]
    assert record.copy_text == "Copied words"
    assert record.delivery_mode is DeliveryMode.COPY
    assert record.timestamp.utcoffset() is not None


def test_concurrent_store_instances_do_not_lose_records(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    stores = [JsonlHistoryStore(path, enabled=True, max_records=50) for _ in range(4)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(stores[number % len(stores)].append_record, make_record(number))
            for number in range(20)
        ]
        assert all(future.result() for future in futures)

    loaded = stores[0].load()
    assert len(loaded) == 20
    assert {record.text for record in loaded} == {f"transcript {number}" for number in range(20)}
