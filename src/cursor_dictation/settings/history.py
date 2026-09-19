from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, RLock

from cursor_dictation.core.models import DeliveryMode

DEFAULT_MAX_HISTORY_RECORDS = 500
_PATH_LOCKS: dict[Path, RLock] = {}
_PATH_LOCKS_GUARD = Lock()


class HistoryError(RuntimeError):
    """Transcript history could not be read or changed safely."""


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    timestamp: datetime
    text: str
    delivery_mode: DeliveryMode

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC-aware")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.delivery_mode, DeliveryMode):
            raise TypeError("delivery_mode must be a DeliveryMode")

    @property
    def copy_text(self) -> str:
        return self.text

    def to_dict(self) -> dict[str, str]:
        timestamp = self.timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "timestamp": timestamp,
            "text": self.text,
            "delivery_mode": self.delivery_mode.value,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, object]) -> HistoryRecord:
        expected_fields = {"timestamp", "text", "delivery_mode"}
        if set(values) != expected_fields:
            raise ValueError("history record must contain timestamp, text, and delivery_mode")
        raw_timestamp = values["timestamp"]
        raw_text = values["text"]
        raw_delivery_mode = values["delivery_mode"]
        if not isinstance(raw_timestamp, str):
            raise TypeError("history timestamp must be a string")
        if not isinstance(raw_text, str):
            raise TypeError("history text must be a string")
        if not isinstance(raw_delivery_mode, str):
            raise TypeError("history delivery_mode must be a string")
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        return cls(
            timestamp=timestamp,
            text=raw_text,
            delivery_mode=DeliveryMode(raw_delivery_mode),
        )


class JsonlHistoryStore:
    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = False,
        max_records: int = DEFAULT_MAX_HISTORY_RECORDS,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        if type(max_records) is not int or max_records <= 0:
            raise ValueError("max_records must be a positive integer")
        self.path = path
        self._lock = _path_lock(path)
        self.enabled = enabled
        self.max_records = max_records

    def load(self) -> tuple[HistoryRecord, ...]:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> tuple[HistoryRecord, ...]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeDecodeError) as error:
            raise HistoryError(
                f"Could not read transcript history from {self.path}: {error}"
            ) from error

        records: list[HistoryRecord] = []
        try:
            lines = text.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            for line_number, line in enumerate(lines, start=1):
                if not line:
                    raise ValueError(f"line {line_number} is blank")
                decoded = json.loads(line)
                if not isinstance(decoded, dict):
                    raise ValueError(f"line {line_number} is not a JSON object")
                records.append(HistoryRecord.from_dict(decoded))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise HistoryError(
                f"Could not read transcript history from {self.path}. "
                f"The file was left unchanged. Details: {error}"
            ) from error
        return tuple(records[-self.max_records :])

    def append(self, text: str, mode: str) -> None:
        if not self.enabled:
            return
        self.append_record(
            HistoryRecord(
                timestamp=datetime.now(UTC),
                text=text,
                delivery_mode=DeliveryMode(mode),
            )
        )

    def append_record(self, record: HistoryRecord) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            records = (*self._load_unlocked(), record)
            self._write(records[-self.max_records :])
        return True

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError as error:
                raise HistoryError(
                    f"Could not clear transcript history at {self.path}: {error}"
                ) from error

    def _write(self, records: tuple[HistoryRecord, ...]) -> None:
        payload = "".join(
            f"{json.dumps(record.to_dict(), ensure_ascii=False, separators=(',', ':'))}\n"
            for record in records
        )
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.write_bytes(b"")
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
            raise HistoryError(
                f"Could not write transcript history to {self.path}: {error}"
            ) from error


def _path_lock(path: Path) -> RLock:
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(resolved)
        if lock is None:
            lock = RLock()
            _PATH_LOCKS[resolved] = lock
        return lock
