from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class AssemblerErrorKind(str, Enum):
    UNKNOWN_MNEMONIC = "unknown_mnemonic"
    BAD_OPERAND = "bad_operand"
    UNDEFINED_LABEL = "undefined_label"
    DUPLICATE_LABEL = "duplicate_label"
    RANGE_ERROR = "range_error"
    INVALID_DIRECTIVE = "invalid_directive"


class AssemblerError(Exception):
    """Assembler failure with machine-readable location and classification."""

    def __init__(
        self,
        message: str,
        line_number: Optional[int] = None,
        line_text: Optional[str] = None,
        *,
        kind: AssemblerErrorKind = AssemblerErrorKind.BAD_OPERAND,
        column: Optional[int] = None,
        token: Optional[str] = None,
        hint: Optional[str] = None,
    ):
        self.kind = kind
        self.line_number = line_number
        self.line_text = line_text
        self.column = column if column is not None else self._infer_column(line_text, token)
        self.token = token or self._infer_token(message)
        self.message = message
        self.hint = hint
        human = message
        if line_number is not None and line_text is not None:
            human = f"Line {line_number}: {message}\n\t{line_text}"
        super().__init__(human)

    @staticmethod
    def _infer_column(line_text: Optional[str], token: Optional[str]) -> Optional[int]:
        if line_text is None or token is None:
            return None
        position = line_text.find(token)
        return position + 1 if position >= 0 else None

    @staticmethod
    def _infer_token(message: str) -> Optional[str]:
        if ": " in message:
            return message.rsplit(": ", 1)[-1].strip()
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "line": self.line_number,
            "column": self.column,
            "token": self.token,
            "message": self.message,
            "hint": self.hint,
        }
