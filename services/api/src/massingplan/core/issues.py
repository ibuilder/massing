"""The vocabulary for "I could not represent this."

The code this was ported from carried a ``warnings: list[str]``. A list of prose
cannot be filtered by severity, counted, or asserted on -- and a test that
asserts on message text breaks every time somebody improves the wording, so the
test gets deleted, and then nobody is checking the warnings at all.

An ``Issue`` therefore carries a stable, greppable ``code``, the ``action``
actually taken, and where the problem was found. Tests assert on
``"XER.TASKPRED.UNKNOWN_TYPE" in log.codes()``, which survives rewording; the
API maps codes to UI copy; and an operator can grep the logs for one.

The rule the rest of the engine follows: **every coercion, drop or fallback
emits one of these.** A silent default produces a plausible schedule that is
wrong, with nothing in the output to look at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """How much the reader should care.

    ``INFO``    -- recognised and deliberately not used (an OBS table we skip).
    ``WARNING`` -- a default was taken or a value coerced; the schedule computes,
                   but it may not match what the source tool would say.
    ``ERROR``   -- data was dropped or is self-contradictory. The schedule still
                   computes, because a partial answer with a named hole is more
                   useful than a traceback, but somebody has to look.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Issue:
    """One thing the engine could not do exactly as asked, and what it did instead."""

    severity: Severity
    code: str
    message: str
    action: str
    table: str | None = None
    row_key: str | None = None
    field: str | None = None
    raw_value: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "action": self.action,
            "table": self.table,
            "row_key": self.row_key,
            "field": self.field,
            "raw_value": self.raw_value,
        }

    def __str__(self) -> str:
        where = f" [{self.table}:{self.row_key}]" if self.table else ""
        return f"{self.severity.value.upper()} {self.code}{where}: {self.message} -- {self.action}"


@dataclass
class IssueLog:
    """An ordered, filterable collection of issues.

    Ordered because import order is diagnostic: the first issue is usually the
    cause and the rest are consequences.
    """

    entries: list[Issue] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        action: str,
        *,
        table: str | None = None,
        row_key: str | None = None,
        field_name: str | None = None,
        raw_value: object = None,
    ) -> Issue:
        issue = Issue(
            severity=severity,
            code=code,
            message=message,
            action=action,
            table=table,
            row_key=row_key,
            field=field_name,
            raw_value=None if raw_value is None else str(raw_value),
        )
        self.entries.append(issue)
        return issue

    def info(self, code: str, message: str, action: str, **kw: object) -> Issue:
        return self.add(Severity.INFO, code, message, action, **kw)  # type: ignore[arg-type]

    def warn(self, code: str, message: str, action: str, **kw: object) -> Issue:
        return self.add(Severity.WARNING, code, message, action, **kw)  # type: ignore[arg-type]

    def error(self, code: str, message: str, action: str, **kw: object) -> Issue:
        return self.add(Severity.ERROR, code, message, action, **kw)  # type: ignore[arg-type]

    def extend(self, other: IssueLog) -> None:
        self.entries.extend(other.entries)

    def by_severity(self, severity: Severity) -> list[Issue]:
        return [e for e in self.entries if e.severity is severity]

    def codes(self) -> set[str]:
        return {e.code for e in self.entries}

    def has(self, code: str) -> bool:
        return any(e.code == code for e in self.entries)

    def count(self, severity: Severity | None = None) -> int:
        if severity is None:
            return len(self.entries)
        return len(self.by_severity(severity))

    def to_list(self) -> list[dict[str, str | None]]:
        return [e.to_dict() for e in self.entries]

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.entries)

    def __bool__(self) -> bool:
        # Deliberately: an empty log is falsy, so `if issues:` reads as
        # "if anything went wrong". Do not change this to always-true.
        return bool(self.entries)
