from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from cursor_dictation.ui.icons import make_app_icon


class SetupWindow(QDialog):
    install_requested = Signal()
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Set up Cursor Dictation")
        self.setWindowIcon(make_app_icon())
        self.setModal(False)
        self.resize(610, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)

        heading = QLabel("Set up local dictation")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self._explanation = QLabel(
            "Speech recognition runs on this computer. Audio is not uploaded or saved."
        )
        self._explanation.setObjectName("helperText")
        self._explanation.setWordWrap(True)
        layout.addWidget(self._explanation)

        model_heading = QLabel("Recommended model")
        model_heading.setObjectName("sectionHeading")
        layout.addWidget(model_heading)
        self._model_name = QLabel("Whisper small.en · CPU int8")
        layout.addWidget(self._model_name)

        location_row = QHBoxLayout()
        self.install_location = QLineEdit()
        self.install_location.setReadOnly(True)
        choose_button = QPushButton("Choose folder")
        choose_button.clicked.connect(self._choose_location)
        location_row.addWidget(self.install_location, 1)
        location_row.addWidget(choose_button)
        layout.addLayout(location_row)

        microphone_heading = QLabel("Microphone")
        microphone_heading.setObjectName("sectionHeading")
        layout.addWidget(microphone_heading)
        self.microphone = QComboBox()
        self.microphone.addItem("Windows default", None)
        layout.addWidget(self.microphone)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("Ready to download")
        self.progress_label.setObjectName("muted")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.cancel_requested.emit)
        cancel_button.clicked.connect(self.close)
        self.install_button = QPushButton("Download and continue")
        self.install_button.setObjectName("primaryButton")
        self.install_button.clicked.connect(self.install_requested.emit)
        buttons.addWidget(cancel_button)
        buttons.addWidget(self.install_button)
        layout.addLayout(buttons)

    @property
    def explanation_text(self) -> str:
        return self._explanation.text()

    @property
    def model_name(self) -> str:
        return self._model_name.text()

    @property
    def progress_text(self) -> str:
        return self.progress_label.text()

    def set_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_label.setText(message)
        self.install_button.setEnabled(False)

    def set_error(self, message: str) -> None:
        self.progress_label.setText(message)
        self.install_button.setEnabled(True)

    def set_complete(self) -> None:
        self.progress_bar.setValue(100)
        self.progress_label.setText("Model verified")
        self.install_button.setText("Finish")
        self.install_button.setEnabled(True)

    def _choose_location(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose model folder")
        if directory:
            self.install_location.setText(directory)
