"""The scheduling engine. Pure standard library, by contract.

This package is copied verbatim into other products' source trees (SPEC.md 12),
so it may not import Flask, SQLAlchemy, pydantic, or anything else outside the
standard library. `pyproject.toml` turns that into a build failure via
import-linter rather than leaving it as a convention, and the `purity` CI job
proves it by importing every module on a bare interpreter.

`xer` and `mspdi` are deliberately NOT re-exported here: they pull in
`xml.etree`, and a caller that only ever schedules should not pay for an XML
parser at import time. Import them explicitly.
"""

from .constraints import ConstraintType, ConstraintViolation
from .cpm import NetworkResult, calculate
from .graph import ScheduleCycleError
from .health import HealthReport, assess
from .issues import Issue, IssueLog, Severity
from .model import (
    Calendar,
    CalendarException,
    ExchangeActivity,
    ExchangeAssignment,
    ExchangeRelationship,
    ExchangeResource,
    ExchangeSchedule,
    WBSNode,
)
from .network import (
    ActivityKind,
    LagCalendar,
    Link,
    ProgressMode,
    RelationType,
    SchedulerOptions,
    Status,
    Task,
)
from .schedule import ActivityDates, ScheduleOutcome, schedule, schedule_network
from .timeaxis import (
    SEVEN_DAY,
    SIX_DAY,
    STANDARD_5_DAY,
    Instant,
    TimeAxisError,
    WorkCalendar,
    WorkPattern,
    bind_window,
    day_of,
    instant_of,
    standard_calendar,
)
from .units import days_from_hours, hours_from_days

__all__ = [
    "SEVEN_DAY",
    "SIX_DAY",
    "STANDARD_5_DAY",
    "ActivityDates",
    "ActivityKind",
    "Calendar",
    "CalendarException",
    "ConstraintType",
    "ConstraintViolation",
    "ExchangeActivity",
    "ExchangeAssignment",
    "ExchangeRelationship",
    "ExchangeResource",
    "ExchangeSchedule",
    "HealthReport",
    "Instant",
    "Issue",
    "IssueLog",
    "LagCalendar",
    "Link",
    "NetworkResult",
    "ProgressMode",
    "RelationType",
    "ScheduleCycleError",
    "ScheduleOutcome",
    "SchedulerOptions",
    "Severity",
    "Status",
    "Task",
    "TimeAxisError",
    "WBSNode",
    "WorkCalendar",
    "WorkPattern",
    "assess",
    "bind_window",
    "calculate",
    "day_of",
    "days_from_hours",
    "hours_from_days",
    "instant_of",
    "schedule",
    "schedule_network",
    "standard_calendar",
]
