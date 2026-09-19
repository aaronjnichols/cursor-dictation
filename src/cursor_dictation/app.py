from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication

from cursor_dictation.application.coordinator import ApplicationCoordinator
from cursor_dictation.application.model_install import DefaultModelInstaller
from cursor_dictation.application.qt_tasks import QtTaskRunner
from cursor_dictation.audio.sounddevice_recorder import SoundDeviceRecorder
from cursor_dictation.diagnostics.logging import SafeEventLogger, configure_logging
from cursor_dictation.output.clipboard import QtClipboard
from cursor_dictation.output.delivery import WindowsTextDelivery
from cursor_dictation.output.keyboard import Win32Keyboard
from cursor_dictation.platform.windows.foreground import Win32Foreground
from cursor_dictation.platform.windows.hotkeys import WindowsHotkeyService
from cursor_dictation.platform.windows.paths import AppPaths
from cursor_dictation.platform.windows.startup import StartupManager, WinRegistry
from cursor_dictation.resources import resource_path
from cursor_dictation.settings.history import JsonlHistoryStore
from cursor_dictation.settings.store import JsonSettingsStore
from cursor_dictation.settings.vocabulary import VocabularyStore
from cursor_dictation.transcription.faster_whisper_engine import FasterWhisperEngine
from cursor_dictation.transcription.model_manager import ModelManager
from cursor_dictation.transcription.model_manifest import load_model_manifest
from cursor_dictation.ui.icons import make_app_icon
from cursor_dictation.ui.theme import build_stylesheet


def main(argv: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    application = QApplication(["cursor-dictation"])
    application.setApplicationName("Cursor Dictation")
    application.setOrganizationName("Cursor Dictation")
    application.setQuitOnLastWindowClosed(False)
    application.setWindowIcon(make_app_icon())
    application.setStyleSheet(build_stylesheet())

    paths = (
        AppPaths.from_root(options.data_root) if options.data_root else AppPaths.from_environment()
    )
    paths.ensure_directories()
    lock = QLockFile(str(paths.root / "cursor-dictation.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return 2

    coordinator: ApplicationCoordinator | None = None
    try:
        coordinator = build_coordinator(application, paths)
        application.aboutToQuit.connect(coordinator.close)
        coordinator.start()
        if options.smoke_test:
            QTimer.singleShot(250, application.quit)
        return application.exec()
    finally:
        if coordinator is not None:
            coordinator.close()
        lock.unlock()


def build_coordinator(application: QApplication, paths: AppPaths) -> ApplicationCoordinator:
    logger = SafeEventLogger(configure_logging(paths.logs_dir), component="application")
    manifest = load_model_manifest(resource_path("assets", "models", "default-small-en.json"))
    model_manager = ModelManager(engine_factory=FasterWhisperEngine)

    def smoke_load(path: Path) -> object:
        engine = FasterWhisperEngine()
        return engine.load(path)

    def installer_factory(models_root: Path) -> DefaultModelInstaller:
        return DefaultModelInstaller(
            manifest=manifest,
            models_root=models_root,
            smoke_load=smoke_load,
        )

    executable, base_arguments = _startup_command()
    return ApplicationCoordinator(
        application=application,
        paths=paths,
        settings_store=JsonSettingsStore(paths.settings_file),
        vocabulary_store=VocabularyStore(paths.vocabulary_file),
        history=JsonlHistoryStore(paths.history_file),
        recorder=SoundDeviceRecorder(),
        model_manager=model_manager,
        installer_factory=installer_factory,
        hotkeys=WindowsHotkeyService(),
        startup_manager=StartupManager(
            WinRegistry(),
            executable,
            base_arguments=base_arguments,
        ),
        task_runner=QtTaskRunner(),
        delivery=WindowsTextDelivery(QtClipboard(), Win32Keyboard(), Win32Foreground()),
        logger=logger,
    )


def _startup_command() -> tuple[str, tuple[str, ...]]:
    if getattr(sys, "frozen", False):
        return sys.executable, ()
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else python
    return str(executable), ("-m", "cursor_dictation")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cursor-dictation")
    parser.add_argument("--startup", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--data-root", type=Path, help=argparse.SUPPRESS)
    return parser
