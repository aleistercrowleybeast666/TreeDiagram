"""Numeric draft text is validated before Qt can restore a previous value."""
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


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
