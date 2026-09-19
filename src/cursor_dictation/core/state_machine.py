from __future__ import annotations

from cursor_dictation.core.events import Event
from cursor_dictation.core.models import AppState


class InvalidTransition(ValueError):
    pass


_TRANSITIONS: dict[tuple[AppState, Event], AppState] = {
    (AppState.STARTING, Event.FIRST_RUN_REQUIRED): AppState.FIRST_RUN_SETUP,
    (AppState.STARTING, Event.MODEL_LOAD_REQUESTED): AppState.LOADING_MODEL,
    (AppState.FIRST_RUN_SETUP, Event.SETUP_COMPLETED): AppState.LOADING_MODEL,
    (AppState.FIRST_RUN_SETUP, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.LOADING_MODEL, Event.MODEL_LOADED): AppState.IDLE,
    (AppState.LOADING_MODEL, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.IDLE, Event.START_RECORDING): AppState.RECORDING,
    (AppState.IDLE, Event.SETTINGS_OPENED): AppState.SETTINGS_OPEN,
    (AppState.IDLE, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.SETTINGS_OPEN, Event.SETTINGS_CLOSED): AppState.IDLE,
    (AppState.SETTINGS_OPEN, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.RECORDING, Event.RECORDING_COMPLETED): AppState.TRANSCRIBING,
    (AppState.RECORDING, Event.CANCEL_REQUESTED): AppState.IDLE,
    (AppState.RECORDING, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.TRANSCRIBING, Event.TRANSCRIPT_COMPLETED): AppState.DELIVERING,
    (AppState.TRANSCRIBING, Event.OPERATION_FAILED): AppState.ERROR,
    (AppState.DELIVERING, Event.DELIVERY_COMPLETED): AppState.IDLE,
    (AppState.DELIVERING, Event.OPERATION_FAILED): AppState.ERROR_WITH_TRANSCRIPT,
    (AppState.ERROR, Event.RESET): AppState.IDLE,
    (AppState.ERROR_WITH_TRANSCRIPT, Event.RESET): AppState.IDLE,
}


def transition(state: AppState, event: Event) -> AppState:
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError as error:
        raise InvalidTransition(f"State {state.value} cannot handle {event.value}.") from error
