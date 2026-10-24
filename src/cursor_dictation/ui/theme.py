from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleOption, QWidget


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
_PALETTE_ACCENTS = {
    "warm_white": "#DEDAD0",
    "chamber": COLORS.primary,
}


def palette_accent(palette: str) -> str:
    try:
        return _PALETTE_ACCENTS[palette]
    except KeyError as error:
        raise ValueError(f"Unknown theme palette: {palette}") from error


def _active_palette() -> str:
    application = QApplication.instance()
    if isinstance(application, QApplication):
        palette = application.property("cursorDictationPalette")
        if isinstance(palette, str) and palette in _PALETTE_ACCENTS:
            return palette
    return "warm_white"


class ThemeStyle(QProxyStyle):
    """Small custom-drawing additions that Qt stylesheets cannot express."""

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    @staticmethod
    def _draw_checkbox(option: QStyleOption, painter: QPainter) -> None:
        rect = option.rect
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        checked = bool(option.state & QStyle.StateFlag.State_On)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        accent = palette_accent(_active_palette())
        border_color = accent if checked or hovered else COLORS.border
        fill_color = COLORS.active if checked else COLORS.raised
        if not enabled:
            border_color = COLORS.inactive

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(border_color), 1.6))
        fill = QColor(fill_color)
        if not enabled:
            fill.setAlpha(100)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 4, 4)

        if checked:
            check_color = accent if enabled else COLORS.inactive
            check_pen = QPen(QColor(check_color), 1.8)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            path = QPainterPath()
            path.moveTo(rect.left() + 4, rect.center().y())
            path.lineTo(rect.left() + 7, rect.bottom() - 4)
            path.lineTo(rect.right() - 3, rect.top() + 4)
            painter.drawPath(path)
        painter.restore()


def apply_theme(application: QApplication, palette: str = "warm_white") -> None:
    """Install the shared theme once, including custom checkbox drawing."""
    palette_accent(palette)
    if not bool(application.property("cursorDictationThemeInstalled")):
        application.setStyle(ThemeStyle(application.style()))
        application.setProperty("cursorDictationThemeInstalled", True)
    application.setProperty("cursorDictationPalette", palette)
    application.setStyleSheet(build_stylesheet(palette))


def build_stylesheet(palette: str = "warm_white") -> str:
    accent = palette_accent(palette)
    return f"""
    * {{
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
        color: {COLORS.foreground};
    }}
    QWidget {{
        background-color: transparent;
    }}
    QWidget#statusOverlay, QWidget#overlayPanel, QWidget#overlayVisual,
    QWidget#overlayVisualHost, QStackedWidget#overlayVisualStack {{
        background-color: transparent;
    }}
    QMainWindow, QDialog {{
        background-color: {COLORS.background};
    }}
    QMainWindow#settingsWindow, QWidget#settingsRoot {{
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
        color: {accent};
        font-size: 15px;
        font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
    }}
    QLabel#overlayCode, QLabel#overlayStatus, QLabel#overlayDetail,
    QLabel#overlayFooter, QLabel#overlaySymbol {{
        background-color: transparent;
        font-family: "Cascadia Mono", "Consolas", monospace;
    }}
    QLabel#overlayCode {{
        color: {accent};
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
        background-color: {accent};
        border-color: {accent};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QTextEdit, QListWidget {{
        background-color: {COLORS.raised};
        border: 1px solid {COLORS.border};
        border-radius: 7px;
        padding: 6px;
        selection-background-color: {accent};
        selection-color: {COLORS.background};
    }}
    QComboBox QAbstractItemView {{
        background-color: {COLORS.raised};
        color: {COLORS.foreground};
        border: 1px solid {COLORS.border};
        selection-background-color: {COLORS.active};
        selection-color: {COLORS.foreground};
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
        color: {accent};
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
        background-color: {accent};
    }}
    QCheckBox {{
        spacing: 9px;
        min-height: 24px;
    }}
    QCheckBox:hover {{
        color: {COLORS.foreground};
    }}
    QCheckBox:disabled {{
        color: {COLORS.muted};
    }}
    """
