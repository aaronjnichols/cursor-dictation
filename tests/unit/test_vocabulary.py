from __future__ import annotations

from pathlib import Path

import pytest

from cursor_dictation.settings.vocabulary import (
    VocabularyError,
    VocabularyStore,
    build_vocabulary_prompt,
    load_vocabulary,
    parse_vocabulary,
)


def test_parser_trims_ignores_blanks_and_removes_only_exact_duplicates() -> None:
    text = "  HEC-RAS  \r\n\r\nFloodway\nhec-ras\nHEC-RAS\n  CTranslate2  \n"

    assert parse_vocabulary(text) == ("HEC-RAS", "Floodway", "hec-ras", "CTranslate2")


def test_missing_vocabulary_file_is_an_empty_vocabulary(tmp_path: Path) -> None:
    assert load_vocabulary(tmp_path / "vocabulary.txt") == ()


@pytest.mark.parametrize("term", ["bad\x00term", "bad\tterm", "zero\u200bwidth"])
def test_parser_rejects_control_and_format_characters(term: str) -> None:
    with pytest.raises(VocabularyError, match=r"line 2.*control"):
        parse_vocabulary(f"valid\n{term}\n")


def test_parser_enforces_the_entry_limit() -> None:
    with pytest.raises(VocabularyError, match=r"at most 2 entries"):
        parse_vocabulary("one\ntwo\nthree", max_entries=2)


def test_parser_enforces_the_formatted_prompt_limit() -> None:
    assert parse_vocabulary("one\ntwo", max_prompt_characters=8) == ("one", "two")

    with pytest.raises(VocabularyError, match=r"prompt.*8 characters"):
        parse_vocabulary("one\ntwo!", max_prompt_characters=8)


def test_prompt_preserves_the_first_spelling_and_has_no_hidden_rewriting() -> None:
    entries = parse_vocabulary("HEC-RAS\nCTranslate2\n")

    assert build_vocabulary_prompt(entries) == "HEC-RAS, CTranslate2"


@pytest.mark.parametrize("entries", [("valid\nextra",), ("bad\x00term",)])
def test_prompt_builder_rejects_unvalidated_entries(entries: tuple[str, ...]) -> None:
    with pytest.raises(VocabularyError):
        build_vocabulary_prompt(entries)


def test_vocabulary_store_saves_atomically_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "vocabulary.txt"
    store = VocabularyStore(path)

    store.save(("HEC-RAS", "hec-ras", "FLO-2D"))

    assert store.load() == ("HEC-RAS", "hec-ras", "FLO-2D")
    assert path.read_text(encoding="utf-8") == "HEC-RAS\nhec-ras\nFLO-2D\n"


def test_failed_vocabulary_save_preserves_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "vocabulary.txt"
    path.write_text("existing\n", encoding="utf-8")
    store = VocabularyStore(path)

    def failed_replace(source: object, destination: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr("cursor_dictation.settings.vocabulary.os.replace", failed_replace)

    with pytest.raises(VocabularyError, match="Could not save"):
        store.save(("replacement",))

    assert path.read_text(encoding="utf-8") == "existing\n"
    assert not list(tmp_path.glob("*.tmp"))
