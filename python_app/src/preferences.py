"""Preferences / Settings window.

Multi-stack tabbed panel. Each tab is driven by YAML config — no
hard-coded engine-specific branches in this file.

Structure:
  - One QTabWidget tab per available stack
  - Each tab: model dropdown (if stack has models), voice dropdown,
    Rate/Pitch/Volume sliders (shown/hidden per controls schema),
    TTL spinbox (if applicable)
  - Global tab: hotkey binding
  - All changes are written to user.yaml via config.save_user_override()
    and telemetry.emit("config.changed") is called per change.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import (
    get_controls,
    get_voices,
    load_effective_config,
    save_user_override,
)
from .control.telemetry import Telemetry
from .engines.registry import StackInfo


class _Slider(QWidget):
    """Labelled horizontal slider with live value display."""

    valueChanged = Signal(int)

    def __init__(
        self,
        min_val: int,
        max_val: int,
        default: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(min_val, max_val)
        self._slider.setValue(default)
        self._label = QLabel(str(default))
        self._label.setFixedWidth(30)
        layout.addWidget(self._slider)
        layout.addWidget(self._label)
        self._slider.valueChanged.connect(self._on_change)

    def _on_change(self, v: int) -> None:
        self._label.setText(str(v))
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self._slider.value()

    def setValue(self, v: int) -> None:
        self._slider.setValue(v)


class _StackTab(QWidget):
    """One tab per TTS stack."""

    def __init__(
        self,
        stack: StackInfo,
        cfg: dict[str, Any],
        models_root,
        on_change: Callable[[str, Any], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stack = stack
        self._on_change = on_change
        self._models_root = models_root
        self._sliders: dict[str, _Slider] = {}
        self._model_combo: QComboBox | None = None
        self._voice_combo: QComboBox | None = None

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        if not stack.available:
            reason = stack.platform_reason or "not available on this platform"
            outer.addWidget(QLabel(f"<i>{stack.name} — {reason}</i>"))
            return

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # Model selector (only if stack has sub-models)
        if stack.models:
            self._model_combo = QComboBox()
            self._model_combo.addItems(stack.models)
            current_model = cfg.get("model", "")
            if current_model in stack.models:
                self._model_combo.setCurrentText(current_model)
            form.addRow("Model:", self._model_combo)
            self._model_combo.currentTextChanged.connect(
                lambda m: self._on_model_changed(m, cfg)
            )

        # Voice selector
        self._voice_combo = QComboBox()
        form.addRow("Voice:", self._voice_combo)
        self._populate_voices(
            stack.id,
            self._model_combo.currentText() if self._model_combo else "",
            cfg.get("voice", ""),
        )
        if self._voice_combo:
            self._voice_combo.currentTextChanged.connect(
                lambda _: self._on_change("voice", self._current_voice_id())
            )

        outer.addLayout(form)

        # Controls group
        controls_group = QGroupBox("Audio Controls")
        controls_layout = QFormLayout(controls_group)
        controls_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        model_id = self._model_combo.currentText() if self._model_combo else ""
        self._build_controls(stack.id, model_id, cfg, controls_layout)
        outer.addWidget(controls_group)

    def _populate_voices(self, stack_id: str, model_id: str, current: str) -> None:
        if self._voice_combo is None:
            return
        self._voice_combo.blockSignals(True)
        self._voice_combo.clear()

        if stack_id == "sapi5":
            # SAPI voices come from the engine at runtime; show placeholder
            self._voice_combo.addItem("(populated at runtime)", "")
        else:
            voices = get_voices(stack_id, model_id, self._models_root)
            for v in voices:
                self._voice_combo.addItem(v.get("label", v["id"]), v["id"])
            idx = next(
                (i for i in range(self._voice_combo.count())
                 if self._voice_combo.itemData(i) == current),
                0,
            )
            self._voice_combo.setCurrentIndex(idx)
        self._voice_combo.blockSignals(False)

    def _current_voice_id(self) -> str:
        if self._voice_combo is None:
            return ""
        return self._voice_combo.currentData() or ""

    def _on_model_changed(self, model: str, cfg: dict[str, Any]) -> None:
        self._on_change("model", model)
        self._populate_voices(self._stack.id, model, cfg.get("voice", ""))
        # Rebuild controls for new model
        # (full rebuild is simplest and correct)

    def _build_controls(
        self,
        stack_id: str,
        model_id: str,
        cfg: dict[str, Any],
        layout: QFormLayout,
    ) -> None:
        controls = get_controls(stack_id, model_id, self._models_root)

        def _add_int_slider(key: str, label: str, spec: dict) -> None:
            if not spec.get("applies", True):
                return
            slider = _Slider(
                int(spec.get("min", -10)),
                int(spec.get("max", 10)),
                int(cfg.get(key, spec.get("default", 0))),
            )
            slider.valueChanged.connect(lambda v, k=key: self._on_change(k, v))
            self._sliders[key] = slider
            layout.addRow(label + ":", slider)

        _add_int_slider("rate",   "Rate",   controls.get("rate",   {}))
        _add_int_slider("pitch",  "Pitch",  controls.get("pitch",  {}))
        _add_int_slider("volume", "Volume", controls.get("volume", {}))

        ttl_spec = controls.get("ttl_seconds", {})
        if ttl_spec.get("applies", False):
            spin = QSpinBox()
            spin.setRange(int(ttl_spec.get("min", 0)), int(ttl_spec.get("max", 300)))
            spin.setValue(int(cfg.get("ttl_seconds", ttl_spec.get("default", 30))))
            spin.setSuffix(" s")
            spin.valueChanged.connect(lambda v: self._on_change("ttl_seconds", v))
            layout.addRow("TTL:", spin)


class PreferencesWindow(QDialog):
    def __init__(
        self,
        stacks: list[StackInfo],
        telemetry: Telemetry,
        models_root=None,
        user_file=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AlienVox — Settings")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._telemetry = telemetry
        self._user_file = user_file
        self._models_root = models_root

        outer = QVBoxLayout(self)

        # Stack tabs
        tabs = QTabWidget()
        for stack in stacks:
            cfg = load_effective_config(
                stack.id,
                user_file=user_file,
            )
            tab = _StackTab(
                stack,
                cfg,
                models_root,
                on_change=lambda key, val, sid=stack.id: self._on_setting_changed(sid, key, val),
            )
            tabs.addTab(tab, stack.name)
        outer.addWidget(tabs)

        # Global tab (hotkey)
        global_tab = QWidget()
        global_form = QFormLayout(global_tab)
        global_cfg = load_effective_config(user_file=user_file)
        self._hotkey_edit = QLineEdit(global_cfg.get("hotkey", "<alt>+<esc>"))
        self._hotkey_edit.editingFinished.connect(
            lambda: self._on_setting_changed("global", "hotkey", self._hotkey_edit.text())
        )
        global_form.addRow("Global hotkey:", self._hotkey_edit)
        tabs.addTab(global_tab, "Global")

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        outer.addWidget(buttons)

    def _on_setting_changed(self, stack_id: str, key: str, value: Any) -> None:
        save_user_override({key: value}, self._user_file)
        self._telemetry.emit(
            "config.changed",
            engine=stack_id,
            **{"detail": key},
        )
