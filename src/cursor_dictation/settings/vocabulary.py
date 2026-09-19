from __future__ import annotations

import os
import tempfile
import unicodedata
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

MAX_VOCABULARY_ENTRIES = 200
MAX_VOCABULARY_PROMPT_CHARACTERS = 4_000


class VocabularyError(ValueError):
    """Vocabulary text cannot be used as Whisper context."""


def parse_vocabulary(
    text: str,
    *,
    max_entries: int = MAX_VOCABULARY_ENTRIES,
    max_prompt_characters: int = MAX_VOCABULARY_PROMPT_CHARACTERS,
) -> tuple[str, ...]:
    if not isinstance(text, str):
        raise TypeError("vocabulary text must be a string")
    _validate_positive_limit("max_entries", max_entries)
    _validate_positive_limit("max_prompt_characters", max_prompt_characters)

    entries: list[str] = []
    seen: set[str] = set()
    for line_number, source_line in enumerate(text.split("\n"), start=1):
        line = source_line[:-1] if source_line.endswith("\r") else source_line
        if any(unicodedata.category(character).startswith("C") for character in line):
            raise VocabularyError(
                f"Vocabulary line {line_number} contains a control or format character"
            )
        term = line.strip()
        if not term:
            continue
        if term in seen:
            continue
        seen.add(term)
        entries.append(term)
        if len(entries) > max_entries:
            raise VocabularyError(f"Vocabulary may contain at most {max_entries} entries")

    result = tuple(entries)
    build_vocabulary_prompt(result, max_characters=max_prompt_characters)
    return result


def build_vocabulary_prompt(
    entries: Sequence[str],
    *,
    max_entries: int = MAX_VOCABULARY_ENTRIES,
    max_characters: int = MAX_VOCABULARY_PROMPT_CHARACTERS,
) -> str:
    _validate_positive_limit("max_entries", max_entries)
    _validate_positive_limit("max_characters", max_characters)
    if len(entries) > max_entries:
        raise VocabularyError(f"Vocabulary may contain at most {max_entries} entries")
    validated: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, str):
            raise TypeError("vocabulary entries must be strings")
        if not entry or entry != entry.strip() or "\n" in entry or "\r" in entry:
            raise VocabularyError(f"Vocabulary entry {index} must be one trimmed non-empty line")
        if any(unicodedata.category(character).startswith("C") for character in entry):
            raise VocabularyError(
                f"Vocabulary entry {index} contains a control or format character"
            )
        validated.append(entry)
    prompt = ", ".join(validated)
    if len(prompt) > max_characters:
        raise VocabularyError(f"Vocabulary prompt may contain at most {max_characters} characters")
    return prompt


def load_vocabulary(
    path: Path,
    *,
    max_entries: int = MAX_VOCABULARY_ENTRIES,
    max_prompt_characters: int = MAX_VOCABULARY_PROMPT_CHARACTERS,
) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeDecodeError) as error:
        raise VocabularyError(f"Could not read vocabulary from {path}: {error}") from error
    return parse_vocabulary(
        text,
        max_entries=max_entries,
        max_prompt_characters=max_prompt_characters,
    )


class VocabularyStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[str, ...]:
        return load_vocabulary(self.path)

    def save(self, entries: Sequence[str]) -> None:
        validated = parse_vocabulary("\n".join(_single_line_entries(entries)))
        payload = "".join(f"{entry}\n" for entry in validated)
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
                    temporary_path.unlink(missing_ok=True)
            raise VocabularyError(f"Could not save vocabulary to {self.path}: {error}") from error


def _single_line_entries(entries: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, str):
            raise TypeError("vocabulary entries must be strings")
        if "\n" in entry or "\r" in entry:
            raise VocabularyError(f"Vocabulary entry {index} must fit on one line")
        result.append(entry)
    return tuple(result)


def _validate_positive_limit(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
