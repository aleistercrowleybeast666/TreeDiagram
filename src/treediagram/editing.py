"""Private parameter drafts, model-owned defaults and explicit numeric validation."""
from PySide6.QtCore import QObject, QSignalBlocker
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QDoubleSpinBox, QSpinBox


class _NumericDraft:
    def Draft_Start(self, value):
        self._original_value = value
        self._draft_text = None
        self._value_edited = False
        self.lineEdit().textEdited.connect(self._Draft_TextEdit)
        self.valueChanged.connect(self._Draft_ValueEdit)

    def _Draft_TextEdit(self, text):
        # Keep the user's intermediate text even if focus-out invokes Qt fixup.
        self._draft_text = text

    def _Draft_ValueEdit(self, _value):
        self._value_edited = True

    def stepBy(self, steps):
        self._draft_text = None
        super().stepBy(steps)
        self._value_edited = True

    def Draft_Value(self):
        """Read current text without changing focus, fixup or the applied model."""
        text = self._draft_text if self._draft_text is not None else self.lineEdit().text()
        if self.validate(text, len(text))[0] != QValidator.State.Acceptable:
            raise ValueError("incomplete numeric draft")
        if not self._value_edited and self._draft_text is None:
            return self._original_value
        return self.valueFromText(text)

    def Draft_Replace(self, value):
        """An explicit reset replaces even invalid text, retaining exact defaults."""
        with QSignalBlocker(self), QSignalBlocker(self.lineEdit()):
            self.setValue(value)
            self.lineEdit().setText(self.textFromValue(self.value()))
            self._original_value = value
            self._draft_text = None
            self._value_edited = False

    def Value_Collect(self):
        text = self._draft_text if self._draft_text is not None else self.lineEdit().text()
        if self.validate(text, len(text))[0] != QValidator.State.Acceptable:
            self.lineEdit().setText(text)
            self.setFocus()
            self.lineEdit().selectAll()
            label = self.accessibleName() or self.objectName() or "数值"
            raise ValueError(f"{label}：请输入范围内的完整数值；当前草稿尚未应用。")
        if not self._value_edited and self._draft_text is None:
            # An untouched editor must not round an existing high precision value.
            return self._original_value
        self.lineEdit().setText(text)
        self.interpretText()
        return self.value()


class DecimalInput(_NumericDraft, QDoubleSpinBox):
    def __init__(self, value, minimum=0., maximum=1e6, decimals=5):
        super().__init__()
        self.setRange(minimum, maximum)
        self.setDecimals(decimals)
        self.setValue(value)
        self.Draft_Start(value)


class IntegerInput(_NumericDraft, QSpinBox):
    def __init__(self, value, minimum=0, maximum=1000000):
        super().__init__()
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.Draft_Start(value)

    def validate(self, text, position):
        # Keep a typed/pasted fractional draft visible for an explicit error;
        # do not let the integer widget drop the decimal separator character.
        if self.locale().decimalPoint() in text:
            return QValidator.State.Intermediate, text, position
        return super().validate(text, position)


class ParameterDraft(QObject):
    """Reset only this editor's parameters; Apply remains the sole commit path."""

    def __init__(self, dialog, original, editors, buttons, status, error, reset_keys=None):
        super().__init__(dialog)
        self.original = original
        self.defaults = type(original)()
        self.editors = editors
        self.reset_keys = tuple(editors if reset_keys is None else reset_keys)
        self.status = status
        self.error = error
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("应用并关闭")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.reset_button = buttons.addButton(QDialogButtonBox.StandardButton.RestoreDefaults)
        self.reset_button.setText("恢复参数默认")
        self.reset_button.setObjectName("restore_defaults")
        self.reset_button.setToolTip("仅替换本窗口说明范围内的参数草稿；点击应用后才修改工程，取消可放弃。")
        self.reset_button.clicked.connect(self.Defaults_Restore)
        status.setObjectName("draft_status")
        for key, editor in editors.items():
            for widget in editor if isinstance(editor, list) else (editor,):
                if key in self.reset_keys:
                    widget.setToolTip(f"模型默认：{getattr(self.defaults, key)}\n恢复默认只修改草稿，应用后生效。")
                else:
                    widget.setToolTip("恢复参数默认会保留此项；可单独编辑后应用。")
                if isinstance(widget, QComboBox):
                    widget.currentIndexChanged.connect(self.Status_Refresh)
                else:
                    widget.lineEdit().textEdited.connect(self.Status_Refresh)
                    widget.valueChanged.connect(self.Status_Refresh)
        self.Status_Refresh()

    def _Value_Read(self, key):
        editor = self.editors[key]
        if isinstance(editor, list):
            return tuple(widget.Draft_Value() for widget in editor)
        if isinstance(editor, QComboBox):
            return editor.currentData()
        return editor.Draft_Value()

    def _Label_Read(self, key):
        editor = self.editors[key]
        widget = editor[0] if isinstance(editor, list) else editor
        return widget.accessibleName().removesuffix(" [1]")

    def Status_Refresh(self, *_):
        changed, custom, invalid = [], [], []
        for key in self.editors:
            try:
                value = self._Value_Read(key)
            except ValueError:
                invalid.append(key)
                continue
            original = getattr(self.original, key)
            if value != (tuple(original) if isinstance(original, list) else original):
                changed.append(key)
            if key in self.reset_keys and value != getattr(self.defaults, key):
                custom.append(key)
        if invalid:
            state = "待应用 · 请补全：" + self._Label_Read(invalid[0])
        elif changed:
            state = f"待应用 · {len(changed)} 项已修改；应用后再运行或保存。"
        else:
            state = "与已应用配置一致 · 取消可关闭。"
        if set(invalid).intersection(self.reset_keys):
            parameters = "默认状态待确认 · 可恢复参数默认或补全输入。"
        else:
            parameters = (f"{len(custom)} 项参数偏离默认" if custom else "可恢复的参数均为默认值")
        self.status.setText(state + "\n" + parameters)
        self.status.setToolTip("\n".join(self._Label_Read(key) for key in custom))
        self.reset_button.setEnabled(bool(custom or set(invalid).intersection(self.reset_keys)))

    def Defaults_Restore(self):
        for key in self.reset_keys:
            editor, value = self.editors[key], getattr(self.defaults, key)
            if isinstance(editor, list):
                for widget, component in zip(editor, value, strict=True):
                    widget.Draft_Replace(component)
            else:
                editor.Draft_Replace(value)
        self.error.clear()
        self.Status_Refresh()
