from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeColors:
    background: str = "#151313"
    raised: str = "#211E1D"
    popover: str = "#2B2725"
    foreground: str = "#CECDC3"
    muted: str = "#9F9A92"
    primary: str = "#EDB449"
    border: str = "#49413F"
    success: str = "#78A978"
    danger: str = "#D87872"


COLORS = ThemeColors()


def build_stylesheet() -> str:
    return f"""
    * {{
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
        color: {COLORS.foreground};
    }}
    QWidget {{
        background-color: {COLORS.background};
    }}
    QMainWindow, QDialog {{
        background-color: {COLORS.background};
    }}
    QFrame#card, QFrame#overlayCard {{
        background-color: {COLORS.raised};
        border: 1px solid {COLORS.border};
        border-radius: 9px;
    }}
    QFrame#overlayCard {{
        background-color: {COLORS.popover};
    }}
    QLabel#heading {{
        font-size: 20px;
        font-weight: 600;
        color: {COLORS.foreground};
    }}
    QLabel#sectionHeading {{
        font-size: 15px;
        font-weight: 600;
        color: {COLORS.foreground};
    }}
    QLabel#muted, QLabel#helperText {{
        color: {COLORS.muted};
    }}
    QLabel#statusDot {{
        color: {COLORS.primary};
        font-size: 18px;
    }}
    QPushButton {{
        min-height: 30px;
        padding: 2px 12px;
        background-color: {COLORS.raised};
        border: 1px solid {COLORS.border};
        border-radius: 7px;
    }}
    QPushButton:hover {{
        border-color: {COLORS.muted};
    }}
    QPushButton:pressed {{
        background-color: {COLORS.popover};
    }}
    QPushButton:disabled {{
        color: {COLORS.muted};
        border-color: {COLORS.raised};
    }}
    QPushButton#primaryButton {{
        color: {COLORS.background};
        background-color: {COLORS.primary};
        border-color: {COLORS.primary};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QTextEdit, QListWidget {{
        background-color: {COLORS.raised};
        border: 1px solid {COLORS.border};
        border-radius: 7px;
        padding: 6px;
        selection-background-color: {COLORS.primary};
        selection-color: {COLORS.background};
    }}
    QListWidget#settingsNavigation {{
        background-color: transparent;
        border: none;
        padding: 0;
    }}
    QListWidget#settingsNavigation::item {{
        min-height: 32px;
        padding-left: 10px;
        border-radius: 7px;
    }}
    QListWidget#settingsNavigation::item:selected {{
        color: {COLORS.primary};
        background-color: {COLORS.raised};
    }}
    QProgressBar {{
        min-height: 7px;
        max-height: 7px;
        border: none;
        border-radius: 3px;
        background-color: {COLORS.raised};
        text-align: center;
    }}
    QProgressBar::chunk {{
        border-radius: 3px;
        background-color: {COLORS.primary};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QCheckBox::indicator:unchecked {{
        background-color: {COLORS.raised};
        border: 1px solid {COLORS.border};
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{
        background-color: {COLORS.primary};
        border: 1px solid {COLORS.primary};
        border-radius: 4px;
    }}
    """
