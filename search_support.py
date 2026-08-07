"""Shared search utilities for the two-phase SAT entrypoints.

Phase I uses bounded feasibility probes to avoid spending the whole run on a
hard, overly small horizon.  Phase II removes the probe budget and tightens a
feasible incumbent incrementally.  A deterministic sequential schedule is
available from the outset whenever the power cap can accommodate every single
task; it guarantees that a timed run always has a valid incumbent.
"""

from __future__ import annotations

import heapq
import json
import math
import time
from typing import Iterable


EVENT_PREFIX = "SALBP_EVENT "


def average_power_cap(powers: list[int], stations: int) -> int:
    """Return floor((m * average power + maximum task power) / 2)."""
    if not powers or stations <= 0 or stations > len(powers):
        raise ValueError("powers must be non-empty and stations must be in 1..n")
    return (stations * sum(powers) + len(powers) * max(powers)) // (2 * len(powers))


def upper_lower_power_cap(powers: list[int], stations: int) -> int:
    """Return floor((sum of the m largest powers + maximum power) / 2)."""
    if not powers or stations <= 0 or stations > len(powers):
        raise ValueError("powers must be non-empty and stations must be in 1..n")
    ordered = sorted(powers, reverse=True)
    return (sum(ordered[:stations]) + ordered[0]) // 2


def emit_event(start_time: float, event: str, **payload: object) -> None:
    """Emit a machine-readable event while keeping stdout human-readable."""
    record = {"elapsed": time.time() - start_time, "event": event, **payload}
    print(EVENT_PREFIX + json.dumps(record, sort_keys=True), flush=True)


def analytical_cycle_lower_bound(
    times: list[int], powers: list[int], stations: int, power_cap: int
) -> int:
    """Return the maximum of duration, workload, and energy lower bounds."""
    if stations <= 0 or power_cap <= 0:
        raise ValueError("stations and power_cap must be positive")
    workload = math.ceil(sum(times) / stations)
    energy = math.ceil(sum(t * w for t, w in zip(times, powers)) / power_cap)
    return max(max(times), workload, energy)


def initial_probe_horizon(times: list[int], lower_bound: int, stations: int) -> int:
    """Retain the legacy initialization rule without treating it as a bound."""
    legacy = max(max(times), math.ceil(2 * sum(times) / stations))
    return max(lower_bound, legacy)


def next_probe_horizon(current: int, safe_horizon: int) -> int:
    """Expand geometrically while guaranteeing strict progress."""
    return min(safe_horizon, max(current + 1, math.ceil(1.5 * current)))


def topological_order(task_count: int, edges: Iterable[tuple[int, int] | list[int]]) -> list[int]:
    """Compute a deterministic topological order, raising on malformed input."""
    successors: list[list[int]] = [[] for _ in range(task_count)]
    indegree = [0] * task_count
    for source, target in edges:
        if not (0 <= source < task_count and 0 <= target < task_count):
            raise ValueError("precedence endpoint outside the task set")
        successors[source].append(target)
        indegree[target] += 1

    ready = [task for task, degree in enumerate(indegree) if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        task = heapq.heappop(ready)
        order.append(task)
        for successor in successors[task]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(ready, successor)
    if len(order) != task_count:
        raise ValueError("precedence graph is not acyclic")
    return order


def print_safe_sequential_incumbent(
    times: list[int], powers: list[int], edges: Iterable[tuple[int, int] | list[int]], stations: int
) -> tuple[int, list[list[int]]]:
    """Print and return the all-on-station-1 constructive schedule."""
    order = topological_order(len(times), edges)
    cycle = sum(times)
    table = [[0 for _ in range(cycle)] for _ in range(stations)]
    start = 0
    starts: dict[int, int] = {}
    for task in order:
        starts[task] = start
        for slot in range(start, start + times[task]):
            table[0][slot] = powers[task]
        start += times[task]
    # Print in task order so the matrix runner obtains one deterministic
    # assignment for every task even if the subsequent exact phase times out.
    for task in range(len(times)):
        print(f"Task {task + 1} assigned to machine 1 at time {starts[task]}")
    print(f"New makespan: {cycle}")
    return cycle, table
