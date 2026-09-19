from __future__ import annotations

import pytest

from cursor_dictation.core.events import Event
from cursor_dictation.core.models import AppState
from cursor_dictation.core.state_machine import InvalidTransition, transition


@pytest.mark.parametrize(
    ("state", "event", "expected"),
    [
        (AppState.STARTING, Event.FIRST_RUN_REQUIRED, AppState.FIRST_RUN_SETUP),
        (AppState.STARTING, Event.MODEL_LOAD_REQUESTED, AppState.LOADING_MODEL),
        (AppState.FIRST_RUN_SETUP, Event.SETUP_COMPLETED, AppState.LOADING_MODEL),
        (AppState.LOADING_MODEL, Event.MODEL_LOADED, AppState.IDLE),
        (AppState.IDLE, Event.START_RECORDING, AppState.RECORDING),
        (AppState.RECORDING, Event.RECORDING_COMPLETED, AppState.TRANSCRIBING),
        (AppState.RECORDING, Event.CANCEL_REQUESTED, AppState.IDLE),
        (AppState.TRANSCRIBING, Event.TRANSCRIPT_COMPLETED, AppState.DELIVERING),
        (AppState.DELIVERING, Event.DELIVERY_COMPLETED, AppState.IDLE),
        (AppState.IDLE, Event.SETTINGS_OPENED, AppState.SETTINGS_OPEN),
        (AppState.SETTINGS_OPEN, Event.SETTINGS_CLOSED, AppState.IDLE),
        (AppState.ERROR, Event.RESET, AppState.IDLE),
        (AppState.ERROR_WITH_TRANSCRIPT, Event.RESET, AppState.IDLE),
    ],
)
def test_valid_transition(state: AppState, event: Event, expected: AppState) -> None:
    assert transition(state, event) is expected


@pytest.mark.parametrize(
    "state",
    [AppState.RECORDING, AppState.TRANSCRIBING, AppState.DELIVERING],
)
def test_operation_failure_selects_error_state(state: AppState) -> None:
    expected = AppState.ERROR_WITH_TRANSCRIPT if state is AppState.DELIVERING else AppState.ERROR
    assert transition(state, Event.OPERATION_FAILED) is expected


def test_invalid_transition_raises_with_context() -> None:
    with pytest.raises(InvalidTransition, match=r"idle.*recording_completed"):
        transition(AppState.IDLE, Event.RECORDING_COMPLETED)
