from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeColors:
    background: str = "#120F0E"
    raised: str = "#171615"
    popover: str = "#171615"
    active: str = "#25170E"
    foreground: str = "#C9C5BA"
    muted: str = "#898682"
    inactive: str = "#484643"
    primary: str = "#DA7C47"
    border: str = "#302D2B"
    success: str = "#76AD4F"
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
    QWidget#statusOverlay, QWidget#overlayPanel, QWidget#overlayVisual,
    QWidget#overlayVisualHost, QStackedWidget#overlayVisualStack {{
        background-color: transparent;
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
    QLabel#settingsStatus[error="true"] {{
        color: {COLORS.danger};
    }}
    QLabel#statusWaveform {{
        color: {COLORS.primary};
        font-size: 15px;
        font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
    }}
    QLabel#overlayCode, QLabel#overlayStatus, QLabel#overlayDetail,
    QLabel#overlayFooter, QLabel#overlaySymbol {{
        background-color: transparent;
        font-family: "Cascadia Mono", "Consolas", monospace;
    }}
    QLabel#overlayCode {{
        color: {COLORS.primary};
        font-size: 9px;
        font-weight: 600;
    }}
    QLabel#overlayStatus {{
        color: {COLORS.foreground};
        font-size: 10px;
        font-weight: 400;
    }}
    QLabel#overlayDetail {{
        color: {COLORS.muted};
        font-size: 10px;
    }}
    QLabel#overlayFooter {{
        color: {COLORS.muted};
        font-size: 8px;
    }}
    QLabel#overlaySymbol {{
        color: {COLORS.danger};
        font-size: 16px;
        font-weight: 700;
    }}
    QPushButton#overlayDismiss {{
        min-width: 24px;
        max-width: 24px;
        min-height: 24px;
        max-height: 24px;
        padding: 0;
        color: {COLORS.muted};
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 0;
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: 16px;
    }}
    QPushButton#overlayDismiss:hover {{
        color: {COLORS.foreground};
        border-color: {COLORS.border};
    }}
    QPushButton#overlayDismiss:pressed {{
        color: {COLORS.background};
        background-color: {COLORS.foreground};
    }}
    QFrame#overlayDivider, QFrame#overlayFooterDivider {{
        background-color: {COLORS.border};
        border: none;
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
