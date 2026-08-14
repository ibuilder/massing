"""Monte Carlo schedule risk: how likely is this finish date, really?

Ported from ibuilder/AIHackScheduler ``core/risk.py`` (MIT). The statistics port
verbatim -- the PERT closed form, the Pearson correlation, the round-up rule on
percentiles, the fixed default seed. Three changes for this engine:

* ``simulate`` binds every calendar's lattice **once, before the loop**.
  Rebuilding a five-year lattice inside two thousand iterations is two thousand
  times slower than it needs to be, and nothing in the output would say why.
* Results are dates, not offsets.
* **Lags and constraint dates are never sampled.** Only durations. A lag is a
  decision and a constraint is a commitment; sampling them makes the criticality
  index incomparable between iterations, because each run is then a different
  plan rather than the same plan under different luck.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum

from .cpm import calculate
from .network import Link, SchedulerOptions, Task
from .schedule import presented_finish
from .timeaxis import WorkCalendar, day_of


class Distribution(str, Enum):
    TRIANGULAR = "triangular"
    PERT = "pert"


#: Default three-point spread, right-skewed: work more often runs over than
#: under, and a symmetric estimate quietly assumes otherwise.
DEFAULT_OPTIMISTIC_FACTOR = 0.90
DEFAULT_PESSIMISTIC_FACTOR = 1.45


@dataclass(frozen=True)
class DurationEstimate:
    activity_id: str
    optimistic: float
    most_likely: float
    pessimistic: float

    def __post_init__(self) -> None:
        if not (self.optimistic <= self.most_likely <= self.pessimistic):
            raise ValueError(
                f"{self.activity_id}: estimates must be ordered "
                f"optimistic <= most likely <= pessimistic, got "
                f"{self.optimistic}, {self.most_likely}, {self.pessimistic}"
            )

    @property
    def spread(self) -> float:
        return self.pessimistic - self.optimistic


@dataclass(frozen=True)
class ActivityRisk:
    id: str
    name: str
    criticality_index: float
    mean_duration: float
    duration_sensitivity: float

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "criticality_index": round(self.criticality_index, 3),
            "mean_duration": round(self.mean_duration, 2),
            "duration_sensitivity": round(self.duration_sensitivity, 3),
        }


@dataclass
class RiskResult:
    iterations: int
    deterministic_finish: date | None
    finishes: list[date] = field(default_factory=list)
    activities: list[ActivityRisk] = field(default_factory=list)
    distribution: Distribution = Distribution.PERT
    seed: int | None = None

    def percentile(self, p: float) -> date | None:
        """The finish date met in ``p`` percent of runs.

        Interpolates between samples, then **rounds up to the next whole day**.
        A P80 that lands at 271.2 days is not met on day 271; a commitment is
        either kept by the end of a day or it is not.
        """
        if not self.finishes:
            return None
        if not 0 <= p <= 100:
            raise ValueError(f"percentile must be between 0 and 100, got {p}")
        ordinals = sorted(f.toordinal() for f in self.finishes)
        if len(ordinals) == 1:
            return date.fromordinal(ordinals[0])
        position = (p / 100) * (len(ordinals) - 1)
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return date.fromordinal(ordinals[low])
        interpolated = ordinals[low] + (ordinals[high] - ordinals[low]) * (position - low)
        return date.fromordinal(math.ceil(interpolated))

    @property
    def confidence_in_deterministic(self) -> float | None:
        """Measured proportion of runs that met the deterministic date.

        Measured, not assumed. Most schedules land far below 50%, and saying so
        is the single most useful output of a risk run.
        """
        if not self.finishes or self.deterministic_finish is None:
            return None
        met = sum(1 for f in self.finishes if f <= self.deterministic_finish)
        return met / len(self.finishes)

    @property
    def most_critical(self) -> list[ActivityRisk]:
        return sorted(
            self.activities,
            key=lambda a: (-a.criticality_index, -a.duration_sensitivity, a.id),
        )

    def to_dict(self) -> dict[str, object]:
        confidence = self.confidence_in_deterministic
        return {
            "iterations": self.iterations,
            "distribution": self.distribution.value,
            "seed": self.seed,
            "deterministic_finish": (
                self.deterministic_finish.isoformat() if self.deterministic_finish else None
            ),
            "confidence_in_deterministic": (None if confidence is None else round(confidence, 3)),
            "p10": self._iso(self.percentile(10)),
            "p50": self._iso(self.percentile(50)),
            "p80": self._iso(self.percentile(80)),
            "p90": self._iso(self.percentile(90)),
            "activities": [a.to_dict() for a in self.most_critical[:50]],
        }

    @staticmethod
    def _iso(value: date | None) -> str | None:
        return value.isoformat() if value else None


def default_estimates(
    tasks: Sequence[Task],
    optimistic_factor: float = DEFAULT_OPTIMISTIC_FACTOR,
    pessimistic_factor: float = DEFAULT_PESSIMISTIC_FACTOR,
) -> list[DurationEstimate]:
    """Three-point estimates derived from planned durations, right-skewed."""
    return [
        DurationEstimate(
            activity_id=t.id,
            optimistic=t.duration_days * optimistic_factor,
            most_likely=float(t.duration_days),
            pessimistic=t.duration_days * pessimistic_factor,
        )
        for t in tasks
    ]


def _sample(estimate: DurationEstimate, rng: random.Random, distribution: Distribution) -> int:
    """Draw one duration, rounded to whole working days."""
    if estimate.spread == 0:
        return round(estimate.most_likely)

    if distribution is Distribution.TRIANGULAR:
        value = rng.triangular(estimate.optimistic, estimate.pessimistic, estimate.most_likely)
    else:
        # PERT: a beta distribution shaped by the three points. With the
        # conventional lambda of 4 the shape parameters reduce to a closed form,
        # and a symmetric estimate yields beta(3, 3), as it should.
        mean = (estimate.optimistic + 4 * estimate.most_likely + estimate.pessimistic) / 6
        alpha = 6 * (mean - estimate.optimistic) / estimate.spread
        beta = 6 * (estimate.pessimistic - mean) / estimate.spread
        value = estimate.optimistic + rng.betavariate(alpha, beta) * estimate.spread

    return max(0, round(value))


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Correlation coefficient, returning 0.0 when either series is constant."""
    if len(xs) < 2:
        return 0.0
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def simulate(
    tasks: Sequence[Task],
    links: Sequence[Link] = (),
    calendars: Mapping[str, WorkCalendar] | None = None,
    *,
    estimates: Sequence[DurationEstimate] | None = None,
    iterations: int = 2000,
    distribution: Distribution = Distribution.PERT,
    seed: int | None = 12345,
    data_date: date | None = None,
    options: SchedulerOptions | None = None,
) -> RiskResult:
    """Run the network ``iterations`` times with sampled durations.

    ``seed`` defaults to a fixed value so the same plan produces the same
    figures on every run. A forecast that changes when nobody changed the plan is
    not a forecast anyone can act on. Pass ``seed=None`` for genuinely random
    draws.
    """
    tasks = list(tasks)
    links = list(links)
    if not tasks:
        return RiskResult(iterations=0, deterministic_finish=None, seed=seed)
    if iterations < 1:
        raise ValueError(f"iterations must be at least 1, got {iterations}")

    # Raises on a bad network before we spend two thousand iterations on it.
    baseline = calculate(tasks, links, calendars, data_date=data_date, options=options)

    estimate_map = {
        e.activity_id: e for e in (estimates if estimates is not None else default_estimates(tasks))
    }
    missing = [t.id for t in tasks if t.id not in estimate_map]
    if missing:
        raise ValueError(f"No duration estimate for: {', '.join(sorted(missing))}")

    # Bind the lattices once. The longest sampled duration bounds how far the
    # window needs to reach; without this every iteration rebuilds them.
    if calendars:
        longest = max((e.pessimistic for e in estimate_map.values()), default=0.0)
        horizon_days = int(sum(e.pessimistic for e in estimate_map.values()) + longest + 730)
        from datetime import timedelta

        first = day_of(baseline.project_start) - timedelta(days=365)
        last = day_of(baseline.project_finish) + timedelta(days=min(horizon_days, 40 * 365))
        for cal in calendars.values():
            cal.bind(first, last)

    # Not a cryptographic RNG, deliberately: a risk forecast has to be
    # reproducible from its seed, which is the opposite of what a CSPRNG offers.
    rng = random.Random(seed)  # noqa: S311
    finishes: list[date] = []
    finish_ordinals: list[float] = []
    critical_counts = dict.fromkeys((t.id for t in tasks), 0)
    sampled_durations: dict[str, list[float]] = {t.id: [] for t in tasks}

    for _ in range(iterations):
        sampled: list[Task] = []
        for t in tasks:
            drawn = _sample(estimate_map[t.id], rng, distribution)
            sampled_durations[t.id].append(float(drawn))
            sampled.append(replace(t, duration_days=drawn))

        run = calculate(sampled, links, calendars, data_date=data_date, options=options)
        # Presented, not converted here. `day_of(run.project_finish)` names the
        # day after the last one worked, and on a Mon-Fri calendar it lands on
        # a Saturday -- so every percentile in the forecast came out later than
        # the finish the activity table shows, and sometimes on a day nobody
        # works. A P80 is read straight off this against a contract date.
        finish = presented_finish(run, sampled, calendars) or day_of(run.project_finish)
        finishes.append(finish)
        finish_ordinals.append(float(run.project_finish))
        # Criticality counts driving-path membership rather than zero float:
        # with constraints in play those differ, and it is the driving path that
        # governs the date.
        for aid in run.longest_path():
            critical_counts[aid] += 1

    activity_risks = [
        ActivityRisk(
            id=t.id,
            name=t.name,
            criticality_index=critical_counts[t.id] / iterations,
            mean_duration=statistics.fmean(sampled_durations[t.id]),
            # How strongly this activity's duration drove the project's. High
            # sensitivity with low criticality is an activity that only
            # sometimes matters -- and matters a great deal when it does.
            duration_sensitivity=_pearson(sampled_durations[t.id], finish_ordinals),
        )
        for t in tasks
    ]

    return RiskResult(
        iterations=iterations,
        deterministic_finish=presented_finish(baseline, tasks, calendars)
        or day_of(baseline.project_finish),
        finishes=finishes,
        activities=activity_risks,
        distribution=distribution,
        seed=seed,
    )
