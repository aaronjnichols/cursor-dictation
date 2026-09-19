from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cursor_dictation.audio.recorder import AudioDevice
from cursor_dictation.settings.history import HistoryRecord
from cursor_dictation.settings.schema import AppSettings, ModelSource
from cursor_dictation.settings.vocabulary import parse_vocabulary
from cursor_dictation.ui.icons import make_app_icon


class SettingsWindow(QMainWindow):
    save_requested = Signal()
    close_requested = Signal()
    clear_history_requested = Signal()
    copy_history_requested = Signal(str)
    microphone_test_requested = Signal()

    page_names = (
        "General",
        "Hotkeys",
        "Audio",
        "Model",
        "Vocabulary",
        "History",
        "About",
    )

    def __init__(self) -> None:
        super().__init__()
        self._model_source = ModelSource.RECOMMENDED
        self._editing_enabled = True
        self.setWindowTitle("Cursor Dictation settings")
        self.setWindowIcon(make_app_icon())
        self.resize(760, 540)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 20, 20, 16)

        heading = QLabel("Cursor Dictation")
        heading.setObjectName("heading")
        root_layout.addWidget(heading)

        body = QHBoxLayout()
        body.setSpacing(22)
        self.navigation = QListWidget()
        self.navigation.setObjectName("settingsNavigation")
        self.navigation.setFixedWidth(145)
        self.navigation.addItems(self.page_names)
        self.navigation.setCurrentRow(0)
        body.addWidget(self.navigation)

        self.stack = QStackedWidget()
        self._add_pages()
        body.addWidget(self.stack, 1)
        root_layout.addLayout(body, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("settingsStatus")
        footer.addWidget(self.status_label)
        footer.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.save_requested.emit)
        footer.addWidget(self.close_button)
        footer.addWidget(self.save_button)
        root_layout.addLayout(footer)

        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.setCentralWidget(root)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._editing_enabled:
            event.ignore()
            return
        self.close_requested.emit()
        super().closeEvent(event)

    def apply_settings(
        self,
        settings: AppSettings,
        *,
        vocabulary: tuple[str, ...],
        devices: tuple[AudioDevice, ...],
    ) -> None:
        self.hold_hotkey.setText(settings.hold_to_talk_hotkey)
        self.toggle_hotkey.setText(settings.toggle_recording_hotkey)
        self.copy_hotkey.setText(settings.record_and_copy_hotkey)
        self.cancel_hotkey.setText(settings.cancel_hotkey)
        self.sound_cues.setChecked(settings.sound_cues_enabled)
        self.history_enabled.setChecked(settings.history_enabled)
        self.launch_at_sign_in.setChecked(settings.launch_at_sign_in)
        self.model_path.setText(settings.model_path or "")
        self._model_source = settings.model_source
        self.vocabulary_editor.setPlainText("\n".join(vocabulary))

        self.microphone.clear()
        self.microphone.addItem("Windows default", None)
        selected_index = 0
        for device in devices:
            label = f"{device.name} (default)" if device.is_default else device.name
            self.microphone.addItem(label, device.id)
            if device.id == settings.microphone_device_id:
                selected_index = self.microphone.count() - 1
        self.microphone.setCurrentIndex(selected_index)

    def collect_settings(self) -> tuple[AppSettings, tuple[str, ...]]:
        raw_device_id = self.microphone.currentData()
        device_id = cast(str | None, raw_device_id) if raw_device_id is not None else None
        model_path = self.model_path.text().strip() or None
        settings = AppSettings(
            hold_to_talk_hotkey=self.hold_hotkey.text().strip(),
            toggle_recording_hotkey=self.toggle_hotkey.text().strip(),
            record_and_copy_hotkey=self.copy_hotkey.text().strip(),
            cancel_hotkey=self.cancel_hotkey.text().strip(),
            microphone_device_id=device_id,
            model_path=model_path,
            model_source=self._model_source,
            sound_cues_enabled=self.sound_cues.isChecked(),
            history_enabled=self.history_enabled.isChecked(),
            launch_at_sign_in=self.launch_at_sign_in.isChecked(),
        )
        vocabulary = parse_vocabulary(self.vocabulary_editor.toPlainText())
        return settings, vocabulary

    @property
    def status_text(self) -> str:
        return self.status_label.text()

    def set_status(self, message: str, *, error: bool = False) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("error", error)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_microphone_test_status(self, message: str, *, error: bool = False) -> None:
        self.set_status(message, error=error)

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self.navigation.setEnabled(enabled)
        self.stack.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.close_button.setEnabled(enabled)

    @property
    def selected_microphone_id(self) -> str | None:
        value = self.microphone.currentData()
        return cast(str, value) if value is not None else None

    def set_microphone_test_active(self, active: bool) -> None:
        self.test_microphone_button.setText("Stop test" if active else "Test microphone")
        self.microphone.setEnabled(not active)
        if not active:
            self.input_level.setValue(0)

    def set_input_level(self, level: float) -> None:
        self.input_level.setValue(round(max(0.0, min(1.0, level)) * 100))

    @property
    def history_record_count(self) -> int:
        return self.history_list.count()

    def apply_history(self, records: tuple[HistoryRecord, ...]) -> None:
        self.history_list.clear()
        for record in reversed(records):
            timestamp = record.timestamp.astimezone().strftime("%b %d, %Y %I:%M %p")
            preview = " ".join(record.text.splitlines())
            if len(preview) > 120:
                preview = preview[:117] + "..."
            item = QListWidgetItem(f"{timestamp} · {record.delivery_mode.value}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, record.copy_text)
            self.history_list.addItem(item)
        self.copy_history_button.setEnabled(self.history_list.count() > 0)

    def _copy_selected_history(self) -> None:
        selected = self.history_list.selectedItems()
        if not selected:
            return
        text = selected[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(text, str):
            self.copy_history_requested.emit(text)

    def _choose_model(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose local CTranslate2 model",
            self.model_path.text(),
        )
        if directory:
            self.set_custom_model_path(Path(directory))

    def set_custom_model_path(self, path: Path) -> None:
        self.model_path.setText(str(path))
        self._model_source = ModelSource.CUSTOM

    def _use_default_model(self) -> None:
        self.model_path.clear()
        self._model_source = ModelSource.RECOMMENDED

    def _add_pages(self) -> None:
        self.launch_at_sign_in = QCheckBox("Launch Cursor Dictation when I sign in")
        self.sound_cues = QCheckBox("Play recording and completion sounds")
        self.stack.addWidget(
            self._page(
                "General",
                "Cursor Dictation runs in the Windows notification area.",
                (self.launch_at_sign_in, self.sound_cues),
            )
        )

        self.hold_hotkey = QLineEdit("Ctrl+Alt+Space")
        self.toggle_hotkey = QLineEdit("Ctrl+Alt+D")
        self.copy_hotkey = QLineEdit("Ctrl+Alt+C")
        self.cancel_hotkey = QLineEdit("Ctrl+Alt+Escape")
        hotkey_form = QFormLayout()
        hotkey_form.addRow("Hold to talk", self.hold_hotkey)
        hotkey_form.addRow("Toggle recording", self.toggle_hotkey)
        hotkey_form.addRow("Record and copy", self.copy_hotkey)
        hotkey_form.addRow("Cancel", self.cancel_hotkey)
        self.stack.addWidget(
            self._page("Hotkeys", "Shortcuts work across Windows.", (hotkey_form,))
        )

        self.microphone = QComboBox()
        self.microphone.addItem("Windows default", None)
        self.test_microphone_button = QPushButton("Test microphone")
        self.test_microphone_button.clicked.connect(self.microphone_test_requested.emit)
        self.input_level = QProgressBar()
        self.input_level.setRange(0, 100)
        audio_form = QFormLayout()
        audio_form.addRow("Input device", self.microphone)
        audio_form.addRow("Input level", self.input_level)
        self.stack.addWidget(
            self._page(
                "Audio",
                "Audio remains in memory and is never saved.",
                (audio_form, self.test_microphone_button),
            )
        )

        self.model_path = QLineEdit()
        self.model_path.setReadOnly(True)
        self.choose_model_button = QPushButton("Choose local model folder")
        self.choose_model_button.clicked.connect(self._choose_model)
        self.use_default_model_button = QPushButton("Use recommended model")
        self.use_default_model_button.clicked.connect(self._use_default_model)
        model_form = QFormLayout()
        model_form.addRow("Active model", QLabel("Whisper small.en"))
        model_form.addRow("Local path", self.model_path)
        self.stack.addWidget(
            self._page(
                "Model",
                "Models run locally through CTranslate2 using CPU int8 inference.",
                (model_form, self.choose_model_button, self.use_default_model_button),
            )
        )

        self.vocabulary_editor = QTextEdit()
        self.vocabulary_editor.setPlaceholderText("One term or short phrase per line")
        self.stack.addWidget(
            self._page(
                "Vocabulary",
                "These terms guide Whisper. Cursor Dictation does not replace words "
                "after transcription.",
                (self.vocabulary_editor,),
            )
        )

        self.history_enabled = QCheckBox("Keep local transcript history")
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(150)
        self.copy_history_button = QPushButton("Copy selected transcript")
        self.copy_history_button.setEnabled(False)
        self.copy_history_button.clicked.connect(self._copy_selected_history)
        self.clear_history_button = QPushButton("Clear history")
        self.clear_history_button.clicked.connect(self.clear_history_requested.emit)
        self.stack.addWidget(
            self._page(
                "History",
                "History is off by default and never contains audio or target-window details.",
                (
                    self.history_enabled,
                    self.history_list,
                    self.copy_history_button,
                    self.clear_history_button,
                ),
            )
        )

        version = QLabel("Version 0.1.0")
        version.setObjectName("muted")
        self.stack.addWidget(
            self._page(
                "About",
                "Local speech-to-text for Windows. No accounts, telemetry, or cloud fallback.",
                (version,),
            )
        )

    @staticmethod
    def _page(title: str, help_text: str, items: Iterable[object]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("sectionHeading")
        helper = QLabel(help_text)
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(helper)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        for item in items:
            if isinstance(item, QWidget):
                card_layout.addWidget(item)
            elif isinstance(item, QFormLayout):
                card_layout.addLayout(item)
            else:
                raise TypeError(f"Unsupported settings item: {type(item).__name__}")
        layout.addWidget(card)
        layout.addStretch(1)
        return page
