from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cursor_dictation.ui.icons import make_app_icon


class SettingsWindow(QMainWindow):
    save_requested = Signal()
    close_requested = Signal()

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
        footer.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.save_requested.emit)
        footer.addWidget(close_button)
        footer.addWidget(self.save_button)
        root_layout.addLayout(footer)

        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.setCentralWidget(root)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_requested.emit()
        super().closeEvent(event)

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
        model_form = QFormLayout()
        model_form.addRow("Active model", QLabel("Whisper small.en"))
        model_form.addRow("Local path", self.model_path)
        self.stack.addWidget(
            self._page(
                "Model",
                "Models run locally through CTranslate2 using CPU int8 inference.",
                (model_form, self.choose_model_button),
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
        self.clear_history_button = QPushButton("Clear history")
        self.stack.addWidget(
            self._page(
                "History",
                "History is off by default and never contains audio or target-window details.",
                (self.history_enabled, self.clear_history_button),
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
