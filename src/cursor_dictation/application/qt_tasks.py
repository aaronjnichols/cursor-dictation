from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Qt, QThread, QThreadPool, Signal, Slot

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]
TaskFunction = Callable[[ProgressCallback, CancelCheck], object]


class _TaskSignals(QObject):
    progressed = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(object)


class _TaskWorker(QRunnable):
    def __init__(self, task: TaskFunction, cancelled: Event, signals: _TaskSignals) -> None:
        super().__init__()
        self._task = task
        self._cancelled = cancelled
        self._signals = signals

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(self._report_progress, self._cancelled.is_set)
        except Exception as error:
            self._signals.failed.emit(error)
            return
        self._signals.succeeded.emit(result)

    def _report_progress(self, percent: int, message: str) -> None:
        self._signals.progressed.emit(max(0, min(100, percent)), message)


class QtTaskRunner(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, *, thread_pool: QThreadPool | None = None) -> None:
        super().__init__()
        self._thread_pool = thread_pool or QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._signals = _TaskSignals(self)
        self._cancelled = Event()
        self._running = False
        queued = Qt.ConnectionType.QueuedConnection
        self._signals.progressed.connect(self.progress.emit, queued)
        self._signals.succeeded.connect(self._on_succeeded, queued)
        self._signals.failed.connect(self._on_failed, queued)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, task: TaskFunction) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("Background tasks must be started from the Qt owner thread.")
        if self._running:
            raise RuntimeError("A background task is already running.")
        self._cancelled.clear()
        self._running = True
        self._thread_pool.start(_TaskWorker(task, self._cancelled, self._signals))

    def cancel(self) -> None:
        self._cancelled.set()

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        self.cancel()
        return self._thread_pool.waitForDone(timeout_ms)

    @Slot(object)
    def _on_succeeded(self, result: object) -> None:
        self._running = False
        self.succeeded.emit(result)

    @Slot(object)
    def _on_failed(self, error: object) -> None:
        self._running = False
        self.failed.emit(error)
