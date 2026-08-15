"""Several projects, the links between them, and one resource pool underneath.

Every construction programme above a certain size is not one schedule. It is a
handful of them -- enabling works, main contract, fit-out, a separate
infrastructure package -- with real logic crossing between, and one set of
tower cranes and one labour pool serving all of it. Scheduled alone, each is
individually correct and collectively fiction.

How this works, and why not by merging
--------------------------------------
The naive approach is to concatenate everything into one big network and
schedule that. It gives the right dates and loses the thing the caller needed:
which project each activity belongs to, what each project's own finish is, and
which delays crossed a boundary. Merging is easy to write and throws away the
question.

So activities keep their identity. Ids are **namespaced** as `project::activity`
for the duration of the pass and unpacked on the way out, which is what makes
an external link expressible at all: two projects can both have an `A1010`, and
in a merged network the second silently inherits the first's logic.

The rule this module is built to keep
-------------------------------------
**A project with no external links keeps exactly the dates it has alone.**
Every start and every finish, asserted row by row. A portfolio feature that
quietly moved a standalone date would be unusable: every existing number
shifts and nothing says why.

**Float is a different matter, and it moves on purpose.** One merged network
has one backward pass and therefore one deadline -- the programme's -- so a
project finishing three weeks before the programme is reported with three
weeks of float, where alone it had none. That is not a leak, it is the answer:
a package with slack against the completion it actually feeds genuinely has
that slack, and reporting its standalone zero would be the fiction.

The distinction was found by probing rather than reasoning. The first version
of this docstring claimed *every* number was unchanged, and 56 of 150 random
portfolios disagreed -- always on `late_start`, `late_finish`,
`total_float_days`, `is_critical` and `is_longest_path`, never on `start` or
`finish`. The behaviour was right and the promise was too broad.

So callers get both: `rows_for` carries programme float, and
`standalone_rows_for` re-runs a project on its own for anybody who wants the
package's own float instead. Naming them separately is what stops one being
mistaken for the other.

That is also why the resource pool is opt-in. Levelling across projects moves
dates by design; doing it because a second project was loaded would change a
programme nobody touched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from .issues import IssueLog
from .network import Link, RelationType, SchedulerOptions, Task
from .resources import Demand
from .schedule import ActivityDates, ScheduleOutcome, schedule_network
from .timeaxis import WorkCalendar

#: Separates the project from the activity inside the pass. Two colons because
#: a single one appears in real activity codes and a collision here would merge
#: two activities into one without a word.
SEPARATOR = "::"


class PortfolioError(ValueError):
    """The portfolio cannot be scheduled as described."""


@dataclass(frozen=True)
class Project:
    """One schedule in the portfolio, with its own identity kept."""

    id: str
    tasks: Sequence[Task]
    links: Sequence[Link] = ()
    name: str = ""

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise PortfolioError("every project needs an id")
        if SEPARATOR in self.id:
            raise PortfolioError(
                f"project id {self.id!r} contains {SEPARATOR!r}, which this module uses to "
                "separate a project from an activity"
            )


@dataclass(frozen=True)
class ExternalLink:
    """A relationship whose ends are in different projects.

    The thing that makes a portfolio a portfolio. Named as a separate type from
    `Link` because an external link is a commitment between two parties, and a
    report that cannot tell one from an internal sequencing decision cannot say
    which delays crossed a boundary.
    """

    predecessor_project: str
    predecessor_id: str
    successor_project: str
    successor_id: str
    type: RelationType = RelationType.FS
    lag_days: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "predecessor": f"{self.predecessor_project}{SEPARATOR}{self.predecessor_id}",
            "successor": f"{self.successor_project}{SEPARATOR}{self.successor_id}",
            "type": self.type.value,
            "lag_days": self.lag_days,
        }


@dataclass(frozen=True)
class PortfolioResult:
    """The whole programme, and each project still recognisable inside it."""

    outcome: ScheduleOutcome
    project_finishes: Mapping[str, date]
    project_starts: Mapping[str, date]
    dates: Mapping[str, Mapping[str, ActivityDates]]
    external_links: tuple[ExternalLink, ...]
    crossing_activities: tuple[str, ...]
    issues: IssueLog = field(default_factory=IssueLog)
    #: Kept so a project can be re-run alone for its own float.
    _projects: Mapping[str, Project] = field(default_factory=dict)

    @property
    def programme_finish(self) -> date:
        return self.outcome.project_finish

    def rows_for(self, project_id: str) -> list[dict[str, str | int | bool | None]]:
        """One project's rows, with its own activity ids restored."""
        if project_id not in self.dates:
            raise PortfolioError(f"no project {project_id!r} in this portfolio")
        return [d.to_row() for d in self.dates[project_id].values()]

    def standalone_rows_for(
        self,
        project_id: str,
        calendars: Mapping[str, WorkCalendar] | None = None,
        *,
        data_date: date | None = None,
        options: SchedulerOptions | None = None,
    ) -> list[dict[str, str | int | bool | None]]:
        """One project scheduled **alone**, for its own float rather than the
        programme's.

        A package manager wants to know the slack inside their own package; a
        programme manager wants the slack against the completion date. Both are
        real questions and they have different answers, so they get different
        methods rather than a flag somebody has to remember the meaning of.

        Only meaningful for a project with no external links -- with them, the
        standalone dates are a different schedule, not a different float.
        """
        project = self._projects.get(project_id)
        if project is None:
            raise PortfolioError(f"no project {project_id!r} in this portfolio")
        return schedule_network(
            list(project.tasks),
            list(project.links),
            calendars,
            data_date=data_date,
            options=options,
        ).to_rows()

    def summary(self) -> dict[str, object]:
        return {
            "programme_finish": self.programme_finish.isoformat(),
            "project_count": len(self.dates),
            "project_finishes": {k: v.isoformat() for k, v in self.project_finishes.items()},
            "project_starts": {k: v.isoformat() for k, v in self.project_starts.items()},
            "external_link_count": len(self.external_links),
            "external_links": [link.to_dict() for link in self.external_links],
            "crossing_activities": list(self.crossing_activities),
            "issues": [i.to_dict() for i in self.issues.entries],
        }


def _key(project_id: str, activity_id: str) -> str:
    return f"{project_id}{SEPARATOR}{activity_id}"


def _unkey(key: str) -> tuple[str, str]:
    project_id, _, activity_id = key.partition(SEPARATOR)
    return project_id, activity_id


def schedule_portfolio(
    projects: Sequence[Project],
    external: Sequence[ExternalLink] = (),
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> PortfolioResult:
    """Schedule every project together, with the links between them honoured.

    One pass over one network, because a delay crossing a boundary has to
    propagate and scheduling the projects in sequence would only propagate it
    in whichever order somebody happened to list them.
    """
    if not projects:
        raise PortfolioError("a portfolio needs at least one project")
    seen: set[str] = set()
    for project in projects:
        if project.id in seen:
            raise PortfolioError(f"project {project.id!r} appears twice")
        seen.add(project.id)

    by_project = {p.id: p for p in projects}
    issues = IssueLog()

    merged_tasks: list[Task] = []
    merged_links: list[Link] = []
    for project in projects:
        for task in project.tasks:
            merged_tasks.append(replace(task, id=_key(project.id, task.id)))
        for link in project.links:
            merged_links.append(
                replace(
                    link,
                    predecessor=_key(project.id, link.predecessor),
                    successor=_key(project.id, link.successor),
                )
            )

    known = {t.id for t in merged_tasks}
    crossing: set[str] = set()
    for external_link in external:
        ends = (external_link.predecessor_project, external_link.successor_project)
        for project_id in ends:
            if project_id not in by_project:
                raise PortfolioError(
                    f"external link names project {project_id!r}, which is not in this "
                    f"portfolio. It holds {sorted(by_project)}"
                )
        if external_link.predecessor_project == external_link.successor_project:
            raise PortfolioError(
                f"{external_link.predecessor_id} -> {external_link.successor_id} is inside "
                f"{external_link.predecessor_project!r}. An internal link belongs on the "
                "project, not in the external list, where it would be reported as a "
                "boundary crossing"
            )
        predecessor = _key(external_link.predecessor_project, external_link.predecessor_id)
        successor = _key(external_link.successor_project, external_link.successor_id)
        for end in (predecessor, successor):
            if end not in known:
                project_id, activity_id = _unkey(end)
                raise PortfolioError(
                    f"external link references {activity_id!r} in {project_id!r}, which has "
                    "no such activity"
                )
        merged_links.append(
            Link(predecessor, successor, external_link.type, external_link.lag_days)
        )
        crossing.update((predecessor, successor))

    outcome = schedule_network(
        merged_tasks, merged_links, calendars, data_date=data_date, options=options
    )

    dates: dict[str, dict[str, ActivityDates]] = {p.id: {} for p in projects}
    for key, computed in outcome.dates.items():
        project_id, activity_id = _unkey(key)
        # Restore the activity's own id. A caller persisting these rows against
        # their project's tables must not receive a namespaced id that exists
        # nowhere in their data.
        dates[project_id][activity_id] = replace(computed, activity_id=activity_id)

    finishes: dict[str, date] = {}
    starts: dict[str, date] = {}
    for project_id, rows in dates.items():
        if not rows:  # pragma: no cover - a project with no activities
            continue
        finishes[project_id] = max(d.finish for d in rows.values())
        starts[project_id] = min(d.start for d in rows.values())

    for project_id, finish in finishes.items():
        if finish == outcome.project_finish and len(finishes) > 1:
            issues.info(
                "PORTFOLIO.DRIVES_PROGRAMME",
                f"{project_id} finishes with the programme, on {finish.isoformat()}",
                "this project is setting the overall date; compressing any other moves nothing",
                row_key=project_id,
            )

    return PortfolioResult(
        outcome=outcome,
        project_finishes=finishes,
        project_starts=starts,
        dates=dates,
        external_links=tuple(external),
        crossing_activities=tuple(sorted(crossing)),
        issues=issues,
        _projects=by_project,
    )


def shared_resource_demand(
    result: PortfolioResult,
    demands: Mapping[str, Sequence[Demand]],
) -> dict[str, list[Demand]]:
    """Per-activity demands re-keyed to the portfolio's namespaced ids.

    Levelling a shared pool needs one set of demands over one network, and the
    demands arrive per project keyed by that project's own activity ids. This
    is the join, kept explicit rather than done inside `schedule_portfolio` --
    a portfolio that levelled itself would move dates on a project whose owner
    only wanted to see the link.
    """
    out: dict[str, list[Demand]] = {}
    for project_id, entries in demands.items():
        if project_id not in result.dates:
            raise PortfolioError(
                f"demands given for project {project_id!r}, which is not in this portfolio"
            )
        for demand in entries:
            activity_id = demand.activity_id
            if activity_id not in result.dates[project_id]:
                raise PortfolioError(
                    f"{project_id}: demand references activity {activity_id!r}, which is not "
                    "in that project"
                )
            out.setdefault(project_id, []).append(
                replace(demand, activity_id=_key(project_id, activity_id))
            )
    return out


__all__ = [
    "SEPARATOR",
    "ExternalLink",
    "PortfolioError",
    "PortfolioResult",
    "Project",
    "schedule_portfolio",
    "shared_resource_demand",
]
