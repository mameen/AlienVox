"""System tray icon and context menu.

Reactive View in the MVC split (see app_state.py/app_controller.py): reads
AppState directly, subscribes to its signals to stay in sync with changes
from any source (the main window, Load Settings, ...), and calls
AppController methods in response to user input.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFileDialog, QMenu, QSystemTrayIcon

from ..control.app_controller import AppController
from ..model.app_state import AppState

_ICONS_DIR = Path(__file__).parent.parent / "resources" / "icons"
_APP_ICON = _ICONS_DIR / "icon_32x32.png"  # official AlienVox icon — see docs/img/icons


def _status_icon(dot_color: str | None) -> QIcon:
    """Build a tray icon from the official app icon, optionally with a small
    colored status dot in the bottom-right corner.

    Currently always called with dot_color=None — every state (idle/
    speaking/error) shows the plain official icon unmodified, by request
    (dynamic per-state dots — idle/playing/exporting — are a nice future
    idea, parked for now). The dot-compositing code is kept working and
    ready: flip _DOT_COLORS below to re-enable it later.
    """
    base = QPixmap(str(_APP_ICON)) if _APP_ICON.exists() else QPixmap(32, 32)
    if base.isNull():
        base = QPixmap(32, 32)
        base.fill(Qt.GlobalColor.transparent)

    if dot_color is None:
        return QIcon(base)

    pix = QPixmap(base)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    size = pix.width()
    dot_d = max(8, size // 3)
    rect = QRect(size - dot_d - 1, size - dot_d - 1, dot_d, dot_d)
    painter.setPen(QPen(QColor("#ffffff"), 1))
    painter.setBrush(QBrush(QColor(dot_color)))
    painter.drawEllipse(rect)
    painter.end()
    return QIcon(pix)


# Set to e.g. {"idle": None, "speaking": "#3fb950", "error": "#e5484d"} to
# re-enable per-state status dots later.
_DOT_COLORS: dict[str, str | None] = {"idle": None, "speaking": None, "error": None}


class AlienVoxTray:
    def __init__(
        self,
        state: AppState,
        controller: AppController,
        on_quit: Callable[[], None],
        on_window_toggle: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._controller = controller

        self._tray = QSystemTrayIcon()
        self._icons = {
            s: _status_icon(color) for s, color in _DOT_COLORS.items()
        }
        self._tray.setIcon(self._icons["idle"])
        self._tray.setToolTip("AlienVox — idle")

        self._on_window_toggle = on_window_toggle or (lambda: None)

        menu = QMenu()
        self._act_speak = menu.addAction("Speak Selection")
        self._act_stop  = menu.addAction("Stop")
        self._act_stop.setEnabled(False)
        menu.addSeparator()
        self._voice_menu = menu.addMenu("Voice ▸")
        menu.addSeparator()
        menu.addAction("Settings…", self._on_window_toggle)
        menu.addAction("Save Settings…", self._on_save_settings)
        menu.addAction("Load Settings…", self._on_load_settings)
        menu.addAction("About",     self._on_about)
        menu.addSeparator()
        menu.addAction("Quit",      on_quit)

        # Use lambda to discard the 'checked' bool that triggered() always passes.
        self._act_speak.triggered.connect(lambda _: controller.speak_async())
        self._act_stop.triggered.connect(lambda _: controller.stop())
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

        # Reactive subscriptions — keeps the tray in sync with state changes
        # from any source (main window combos, Load Settings, ...), not just
        # its own menu actions.
        state.speaking_changed.connect(self._on_state_speaking_changed)
        state.error_changed.connect(self._on_state_error_changed)
        state.catalog_changed.connect(self._rebuild_voice_menu)
        state.stack_changed.connect(lambda _v: self._rebuild_voice_menu())
        state.model_changed.connect(lambda _v: self._rebuild_voice_menu())
        state.voice_changed.connect(lambda _v: self._rebuild_voice_menu())

        self._rebuild_voice_menu()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    # ── AppState reactive handlers ───────────────────────────────────────────

    def _on_state_speaking_changed(self, speaking: bool) -> None:
        if speaking:
            self._tray.setIcon(self._icons["speaking"])
            self._tray.setToolTip("AlienVox — speaking")
            self._act_speak.setEnabled(False)
            self._act_stop.setEnabled(True)
        else:
            self._tray.setIcon(self._icons["idle"])
            self._tray.setToolTip("AlienVox — idle")
            self._act_speak.setEnabled(True)
            self._act_stop.setEnabled(False)

    def _on_state_error_changed(self, message: str) -> None:
        if not message:
            return
        self._tray.setIcon(self._icons["error"])
        tip = f"AlienVox — error: {message}"
        self._tray.setToolTip(tip[:127])  # Windows tooltip length limit

    # ── Voice submenu (data-driven, two-level) ───────────────────────────────

    def _rebuild_voice_menu(self) -> None:
        """Rebuild the Voice ▸ submenu from AppState's catalog + live voices
        and the current active stack/model/voice — called on construction
        and whenever any of those signals fire, so the menu (and its
        checkmarks) never drift from what's actually active."""
        self._voice_menu.clear()
        has_any = False
        current_voice_id = self._state.voice

        for stack in self._state.stacks:
            if not stack.available:
                continue
            stack_id = stack.id
            stack_label = stack.name

            if stack.models:
                # ML-style: Stack ▸ Models ▸ [model] ▸ Voice (4 levels)
                models_menu = self._voice_menu.addMenu(f"{stack_label} · Models")
                for model in stack.models:
                    voices = model.voices
                    if not voices:
                        continue
                    has_any = True
                    model_submenu = models_menu.addMenu(model.name)
                    for v in voices:
                        act = model_submenu.addAction(v.get("label", v["id"]))
                        act.setCheckable(True)
                        act.setChecked(v["id"] == current_voice_id)
                        _sid, _mid, _vid = stack_id, model.id, v["id"]
                        act.triggered.connect(
                            lambda _, _sid=_sid, _mid=_mid, _vid=_vid:
                                self._on_voice_selected(_sid, _mid, _vid)
                        )
            else:
                # SAPI-style: Stack ▸ Voice — sourced from live_voices, since
                # non-ML stacks enumerate voices from the OS/engine at runtime.
                voices = self._state.live_voices_for(stack_id)
                if not voices:
                    continue
                has_any = True
                stack_menu = self._voice_menu.addMenu(stack_label)
                for v in voices:
                    act = stack_menu.addAction(v.get("label", v["id"]))
                    act.setCheckable(True)
                    act.setChecked(v["id"] == current_voice_id)
                    _sid, _vid = stack_id, v["id"]
                    act.triggered.connect(
                        lambda _, _sid=_sid, _vid=_vid:
                            self._on_voice_selected(_sid, "", _vid)
                    )

        if not has_any:
            self._voice_menu.addAction("(no voices installed)").setEnabled(False)

    def _on_voice_selected(self, stack_id: str, model_id: str, voice_id: str) -> None:
        if stack_id != self._state.active_stack:
            self._controller.select_stack(stack_id, voice_id)
            if model_id:
                self._controller.select_model(model_id, voice_id)
        elif model_id and model_id != self._state.active_model:
            self._controller.select_model(model_id, voice_id)
        else:
            self._controller.select_voice(voice_id)

    # ── Settings menu actions ────────────────────────────────────────────────

    def _on_save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            None, "Save Settings", "alienvox-settings.yaml", "YAML Files (*.yaml *.yml)"
        )
        if path:
            self._controller.save_settings_to(Path(path))

    def _on_load_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            None, "Load Settings", "", "YAML Files (*.yaml *.yml)"
        )
        if path:
            self._controller.load_settings_from(Path(path))

    def _on_about(self) -> None:
        from .about import AboutDialog
        AboutDialog().exec()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click → speak selection (primary action)
            self._controller.speak_async()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Double click → toggle main window
            self._on_window_toggle()
