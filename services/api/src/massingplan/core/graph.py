"""Topological order, cycle naming, and driving-chain recovery.

Extracted into its own module rather than left inside the CPM engine because
levelling and comparison both need a topological order, and neither should have
to import the scheduler to get one.

Ported near-verbatim from ibuilder/AIHackScheduler ``core/cpm.py`` (MIT), whose
two good decisions are preserved deliberately:

* **Kahn's algorithm seeded in declaration order**, so a schedule with no logic
  at all comes back in the order the caller supplied it. Seeding from a set
  makes the output depend on hash ordering, which means the same file produces
  different activity orderings between runs.
* **``find_cycle`` recovers and names one concrete loop** rather than reporting
  "a cycle exists". On a two-thousand-activity network, "a cycle exists" is not
  actionable and the planner has no way to find it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence


class ScheduleCycleError(ValueError):
    """The logic contains a loop. Carries the loop itself, not just the fact of it."""

    def __init__(self, cycle: Sequence[str]) -> None:
        self.cycle = list(cycle)
        super().__init__("Circular logic: " + " -> ".join(self.cycle))


def build_successors(
    node_ids: Sequence[str], edges: Iterable[tuple[str, str]]
) -> dict[str, list[str]]:
    """Adjacency in declaration order. Edges are ``(predecessor, successor)``."""
    successors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for pred, succ in edges:
        successors[pred].append(succ)
    return successors


def topological_order(node_ids: Sequence[str], edges: Iterable[tuple[str, str]]) -> list[str]:
    """Kahn's algorithm. Raises :class:`ScheduleCycleError` naming one concrete loop."""
    edge_list = list(edges)
    successors = build_successors(node_ids, edge_list)
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for _pred, succ in edge_list:
        in_degree[succ] += 1

    # Declaration order, not set order: a logic-free schedule must round-trip.
    ready = [nid for nid in node_ids if in_degree[nid] == 0]
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for succ in successors[current]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)

    if len(order) != len(node_ids):
        placed = set(order)
        remaining = [nid for nid in node_ids if nid not in placed]
        raise ScheduleCycleError(find_cycle(remaining, successors))
    return order


def find_cycle(candidates: Sequence[str], successors: Mapping[str, list[str]]) -> list[str]:
    """Walk the un-orderable remainder to recover one concrete cycle.

    Takes candidates as an ordered sequence rather than a set so the loop
    reported for a given input is always the same one -- an error message that
    changes between runs is an error message nobody trusts.
    """
    if not candidates:
        return []
    pool = set(candidates)
    node = candidates[0]
    path: list[str] = []
    seen_on_path: set[str] = set()

    while node not in seen_on_path:
        path.append(node)
        seen_on_path.add(node)
        onward = [s for s in successors.get(node, ()) if s in pool]
        if not onward:
            return path
        node = onward[0]

    # Trim the tail that leads into the loop, so we report the loop itself and
    # not the path that happened to reach it.
    loop_start = path.index(node)
    return [*path[loop_start:], node]


def driving_chain(driving: Mapping[str, str | None], terminal: str | None) -> list[str]:
    """Walk ``driving_predecessor`` backwards from the terminal activity.

    This replaces the "collect every zero-float activity and greedily walk
    forward" approach in the source. That approach returns an arbitrary branch
    when two are equally critical, and the branch it picks changes when the input
    list is reordered. Walking the recorded driving links backwards from the
    activity that actually sets the project finish is exact and order-independent.

    The visited set is a guard, not a feature: driving links cannot loop in a
    network that passed the topological sort, so hitting one means an invariant
    broke and the walk should stop rather than hang.
    """
    if terminal is None:
        return []
    chain: list[str] = []
    seen: set[str] = set()
    node: str | None = terminal
    while node is not None and node not in seen:
        chain.append(node)
        seen.add(node)
        node = driving.get(node)
    chain.reverse()
    return chain


def validate_network(node_ids: Sequence[str], edges: Iterable[tuple[str, str]]) -> None:
    """Reject duplicate ids, dangling references and self-loops before scheduling.

    Self-loops are caught here rather than by the topological sort, because Kahn
    reports them as an ordinary cycle and the message is then less specific than
    it could be.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for nid in node_ids:
        if nid in seen:
            duplicates.add(nid)
        seen.add(nid)
    if duplicates:
        raise ValueError(f"Duplicate activity ids: {sorted(duplicates)}")

    for pred, succ in edges:
        if pred not in seen:
            raise ValueError(f"Relationship references unknown predecessor {pred!r}")
        if succ not in seen:
            raise ValueError(f"Relationship references unknown successor {succ!r}")
        if pred == succ:
            raise ValueError(f"Activity {pred!r} depends on itself")
