from __future__ import annotations

import threading

from cursor_dictation.application.qt_tasks import QtTaskRunner


def test_task_runs_off_ui_thread_and_signals_return_on_owner_thread(qtbot) -> None:  # type: ignore[no-untyped-def]
    owner_thread = threading.get_ident()
    runner = QtTaskRunner()
    progress_threads: list[int] = []
    results: list[tuple[object, int]] = []
    runner.progress.connect(lambda _percent, _text: progress_threads.append(threading.get_ident()))
    runner.succeeded.connect(lambda value: results.append((value, threading.get_ident())))

    def task(progress, cancelled):  # type: ignore[no-untyped-def]
        assert threading.get_ident() != owner_thread
        assert not cancelled()
        progress(50, "Working...")
        return "done"

    runner.start(task)
    qtbot.waitUntil(lambda: bool(results), timeout=3_000)

    assert results == [("done", owner_thread)]
    assert progress_threads == [owner_thread]
    assert not runner.is_running
    runner.shutdown()


def test_cancel_flag_is_visible_to_worker(qtbot) -> None:  # type: ignore[no-untyped-def]
    runner = QtTaskRunner()
    started = threading.Event()
    release = threading.Event()
    results: list[bool] = []

    def task(_progress, cancelled):  # type: ignore[no-untyped-def]
        started.set()
        release.wait(timeout=2)
        return cancelled()

    runner.succeeded.connect(results.append)
    runner.start(task)
    assert started.wait(timeout=1)
    runner.cancel()
    release.set()
    qtbot.waitUntil(lambda: bool(results), timeout=3_000)

    assert results == [True]
    runner.shutdown()
