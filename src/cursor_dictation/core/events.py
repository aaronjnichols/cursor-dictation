from enum import StrEnum


class Event(StrEnum):
    FIRST_RUN_REQUIRED = "first_run_required"
    MODEL_LOAD_REQUESTED = "model_load_requested"
    SETUP_COMPLETED = "setup_completed"
    MODEL_LOADED = "model_loaded"
    START_RECORDING = "start_recording"
    RECORDING_COMPLETED = "recording_completed"
    CANCEL_REQUESTED = "cancel_requested"
    TRANSCRIPT_COMPLETED = "transcript_completed"
    DELIVERY_COMPLETED = "delivery_completed"
    SETTINGS_OPENED = "settings_opened"
    SETTINGS_CLOSED = "settings_closed"
    OPERATION_FAILED = "operation_failed"
    RESET = "reset"
