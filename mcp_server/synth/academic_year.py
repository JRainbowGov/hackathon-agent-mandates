"""Academic-year value object, labelled ``"2021/22"`` (NPD convention)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SLASH = re.compile(r"^(\d{4})[/-](\d{2})$")
_SIX = re.compile(r"^(\d{4})(\d{2})$")
_FOUR = re.compile(r"^\d{4}$")


@dataclass(frozen=True, order=True)
class AcademicYear:
    """An academic year running 1 September ``start_year`` to 31 August ``start_year + 1``."""

    start_year: int

    @classmethod
    def parse(cls, value: object) -> AcademicYear:
        if isinstance(value, AcademicYear):
            return value
        text = str(value).strip()
        for pattern in (_SLASH, _SIX):
            match = pattern.match(text)
            if match:
                start, end2 = int(match.group(1)), int(match.group(2))
                if (start + 1) % 100 != end2:
                    msg = f"Academic year label {text!r} is not consecutive"
                    raise ValueError(msg)
                return cls(start)
        if _FOUR.match(text):
            return cls(int(text))
        msg = f"Cannot parse academic year {value!r}"
        raise ValueError(msg)

    @property
    def label(self) -> str:
        return f"{self.start_year}/{(self.start_year + 1) % 100:02d}"

    def offset(self, years: int) -> AcademicYear:
        return AcademicYear(self.start_year + years)

    @property
    def previous(self) -> AcademicYear:
        return self.offset(-1)

    def __str__(self) -> str:
        return self.label
