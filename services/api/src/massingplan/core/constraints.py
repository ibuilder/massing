"""The ten constraint types, as a semantics table rather than an if-chain.

A constraint is a planner overriding the network on purpose. The engine's job is
to honour that override, and to make the consequence visible when the override
cannot be met -- which is the whole reason the constraint was set.

Two organising decisions:

**Soft versus mandatory is the split that matters**, mirroring Primavera's
``CS_MANDSTART`` / ``CS_MANDFIN``. A *soft* constraint never violates logic: if
it cannot be met, the activity shows negative float and a
:class:`ConstraintViolation` is recorded. A *mandatory* constraint does violate
logic, in both passes, and can push a predecessor negative. Modelling mandatory
as soft makes an imported P6 schedule's dates differ from P6's and hides the
negative float the planner is being warned about.

**The table is data, not branches.** Ten ``if/elif`` arms acquire a missing arm
during a refactor, one constraint type silently becomes a no-op, the dates still
look plausible, and nobody notices. ``EFFECTS`` can be asserted complete
(``set(EFFECTS) == set(ConstraintType)``) and exhaustively parameterised in a
test.

**Negative float is never clamped.** Not here, not in the CPM engine, not in the
presenter. It is the output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .timeaxis import Instant, WorkCalendar, day_of


class ConstraintType(str, Enum):
    """The ten constraint types, named as planners name them.

    The aliases in the comments are the Primavera and MS Project spellings, kept
    next to the members because that is what a reader has in front of them when
    they come here from an XER file.
    """

    NONE = "none"
    START_ON = "start_on"  # MSO -- Must Start On (soft)
    START_ON_OR_AFTER = "start_on_or_after"  # SNET -- Start No Earlier Than
    START_ON_OR_BEFORE = "start_on_or_before"  # SNLT -- Start No Later Than
    FINISH_ON = "finish_on"  # MFO -- Must Finish On (soft)
    FINISH_ON_OR_AFTER = "finish_on_or_after"  # FNET -- Finish No Earlier Than
    FINISH_ON_OR_BEFORE = "finish_on_or_before"  # FNLT -- Finish No Later Than
    AS_LATE_AS_POSSIBLE = "as_late_as_possible"  # ALAP
    MANDATORY_START = "mandatory_start"  # CS_MANDSTART
    MANDATORY_FINISH = "mandatory_finish"  # CS_MANDFIN

    @property
    def needs_date(self) -> bool:
        """True when the type is meaningless without a constraint date."""
        return self not in (ConstraintType.NONE, ConstraintType.AS_LATE_AS_POSSIBLE)


@dataclass(frozen=True)
class ConstraintEffect:
    """What a constraint type does to each pass. One row of the semantics table."""

    floors_early_start: bool
    floors_early_finish: bool
    caps_late_start: bool
    caps_late_finish: bool
    is_mandatory: bool
    is_alap: bool

    @property
    def is_hard(self) -> bool:
        """Counts against DCMA check 5.

        Mandatory constraints and the two "on exactly this date" types are hard:
        they pin a date rather than bounding one. ``SNET`` is soft -- it is how a
        planner says "material arrives then", which is a fact about the world,
        not an override of the network.
        """
        return (
            self.is_mandatory
            or (self.floors_early_start and self.caps_late_start)
            or (self.floors_early_finish and self.caps_late_finish)
        )


#: The whole semantics of constraints, in one place.
#:
#: | type                | fwd            | bwd            | float effect          |
#: |---------------------|----------------|----------------|-----------------------|
#: | NONE                | --             | --             | --                    |
#: | START_ON_OR_AFTER   | ES = max(ES,C) | --             | pushes float down     |
#: | START_ON_OR_BEFORE  | --             | LS = min(LS,C) | negative if ES > C    |
#: | FINISH_ON_OR_AFTER  | EF = max(EF,C) | --             | --                    |
#: | FINISH_ON_OR_BEFORE | --             | LF = min(LF,C) | negative if EF > C    |
#: | START_ON            | ES = max(ES,C) | LS = min(LS,C) | negative if ES > C    |
#: | FINISH_ON           | EF = max(EF,C) | LF = min(LF,C) | negative if EF > C    |
#: | MANDATORY_START     | ES = LS = C, overriding logic  | predecessors go -ve   |
#: | MANDATORY_FINISH    | EF = LF = C, overriding logic  | predecessors go -ve   |
#: | AS_LATE_AS_POSSIBLE | normal         | normal         | post-pass, free float |
EFFECTS: dict[ConstraintType, ConstraintEffect] = {
    ConstraintType.NONE: ConstraintEffect(False, False, False, False, False, False),
    ConstraintType.START_ON_OR_AFTER: ConstraintEffect(True, False, False, False, False, False),
    ConstraintType.START_ON_OR_BEFORE: ConstraintEffect(False, False, True, False, False, False),
    ConstraintType.FINISH_ON_OR_AFTER: ConstraintEffect(False, True, False, False, False, False),
    ConstraintType.FINISH_ON_OR_BEFORE: ConstraintEffect(False, False, False, True, False, False),
    ConstraintType.START_ON: ConstraintEffect(True, False, True, False, False, False),
    ConstraintType.FINISH_ON: ConstraintEffect(False, True, False, True, False, False),
    ConstraintType.MANDATORY_START: ConstraintEffect(True, False, True, False, True, False),
    ConstraintType.MANDATORY_FINISH: ConstraintEffect(False, True, False, True, True, False),
    ConstraintType.AS_LATE_AS_POSSIBLE: ConstraintEffect(False, False, False, False, False, True),
}


@dataclass(frozen=True)
class ConstraintViolation:
    """A constraint the schedule could not honour, and by how much.

    ``overridden_by`` names what beat the constraint. ``"data_date"`` means the
    constraint asked for work in the past; ``"actual_dates"`` means the activity
    already happened and history wins. Both are correct outcomes -- what would be
    wrong is absorbing them silently, so the planner sees a satisfied constraint
    that was in fact ignored.
    """

    activity_id: str
    constraint: ConstraintType
    required: date
    achieved: date
    slip_working_days: int
    overridden_by: str | None = None

    @property
    def is_late(self) -> bool:
        return self.slip_working_days > 0

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "activity_id": self.activity_id,
            "constraint": self.constraint.value,
            "required": self.required.isoformat(),
            "achieved": self.achieved.isoformat(),
            "slip_working_days": self.slip_working_days,
            "overridden_by": self.overridden_by,
        }


def early_floor(
    kind: ConstraintType,
    constraint_at: Instant,
    duration_days: int,
    cal: WorkCalendar,
) -> Instant | None:
    """The earliest *start* instant the constraint permits, or ``None``.

    Finish-side constraints are converted back to a start here, so the forward
    pass only ever reasons about starts. A ``FNET`` on a five-day activity is a
    start floor five working days earlier -- doing that conversion in the pass
    itself is where the duplicate-``±1`` bugs come from.
    """
    effect = EFFECTS[kind]
    if effect.floors_early_start:
        return cal.snap_start_forward(constraint_at)
    if effect.floors_early_finish:
        finish = cal.snap_finish_forward(constraint_at)
        return cal.start_from_finish(finish, duration_days)
    return None


def late_cap(
    kind: ConstraintType,
    constraint_at: Instant,
    duration_days: int,
    cal: WorkCalendar,
) -> Instant | None:
    """The latest *finish* boundary the constraint permits, or ``None``."""
    effect = EFFECTS[kind]
    if effect.caps_late_finish:
        return cal.snap_finish_back(constraint_at)
    if effect.caps_late_start:
        start = cal.snap_start_back(constraint_at)
        return cal.finish_from_start(start, duration_days)
    return None


def check(
    activity_id: str,
    kind: ConstraintType,
    constraint_at: Instant,
    *,
    early_start: Instant,
    early_finish: Instant,
    cal: WorkCalendar,
    overridden_by: str | None = None,
) -> ConstraintViolation | None:
    """Report whether the computed dates honoured the constraint.

    Measured against the *early* dates, because that is what the schedule says
    will happen. Measuring against late dates would report every constraint as
    satisfied, since the backward pass is what enforces them.
    """
    effect = EFFECTS[kind]
    if kind is ConstraintType.NONE or effect.is_alap:
        return None

    if effect.floors_early_start or effect.caps_late_start:
        achieved, required = early_start, cal.snap_start_forward(constraint_at)
    else:
        achieved, required = early_finish, cal.snap_finish_forward(constraint_at)

    if achieved == required:
        return None

    # A "no earlier than" constraint that lands late is satisfied, not violated:
    # the planner asked for a floor and got one. Only the capping side, and the
    # two "on exactly" types, can be violated by being late; and any type can be
    # violated by being overridden.
    late = achieved > required
    can_be_late = effect.caps_late_start or effect.caps_late_finish
    if late and not can_be_late and overridden_by is None:
        return None
    if not late and not (effect.floors_early_start or effect.floors_early_finish):
        return None

    slip = cal.count_working_days(required, achieved)
    return ConstraintViolation(
        activity_id=activity_id,
        constraint=kind,
        required=day_of(required),
        achieved=day_of(achieved),
        slip_working_days=slip,
        overridden_by=overridden_by,
    )


def parse(value: str | None) -> ConstraintType:
    """Tolerant read of a stored constraint name. Unknown values are ``NONE``.

    Callers that care -- the file readers do -- compare the result against
    ``NONE`` and emit an issue naming the raw value. Raising here would make a
    single unrecognised constraint in a five-thousand-activity file abort the
    whole import, which is a worse answer than importing it and saying so.
    """
    if not value:
        return ConstraintType.NONE
    normalised = value.strip().lower().replace("-", "_").replace(" ", "_")
    for kind in ConstraintType:
        if kind.value == normalised:
            return kind
    return ConstraintType.NONE
