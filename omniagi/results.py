"""Check results shared by every verification module.

Every check returns a :class:`CheckResult`.  Results carry the *name of the
rule* so a CI failure says exactly which constitutional rule broke rather than
just "RESULT: FAIL".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    """Outcome of a single named check."""

    name: str
    status: Status
    summary: str
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAIL

    @classmethod
    def passed(cls, name: str, summary: str, details: list[str] | None = None) -> "CheckResult":
        return cls(name=name, status=Status.PASS, summary=summary, details=details or [])

    @classmethod
    def warned(cls, name: str, summary: str, details: list[str] | None = None) -> "CheckResult":
        return cls(name=name, status=Status.WARN, summary=summary, details=details or [])

    @classmethod
    def failed(cls, name: str, summary: str, details: list[str] | None = None) -> "CheckResult":
        return cls(name=name, status=Status.FAIL, summary=summary, details=details or [])

    @classmethod
    def from_errors(
        cls, name: str, errors: list[str], ok_summary: str, fail_summary: str
    ) -> "CheckResult":
        if errors:
            return cls.failed(name, fail_summary, errors)
        return cls.passed(name, ok_summary)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "details": list(self.details),
        }
