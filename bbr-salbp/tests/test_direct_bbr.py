#!/usr/bin/env python3
"""Correctness regression tests for direct_bbr_salbp2.

The randomized cases are deliberately tiny so their optimum can be obtained by
an independent exhaustive dynamic program.  This is a correctness test, not a
performance benchmark.
"""

from __future__ import annotations

import argparse
import random
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def brute_force_optimum(
    times: list[int], edges: list[tuple[int, int]], stations: int
) -> int:
    n = len(times)
    all_tasks = (1 << n) - 1
    predecessors = [0] * n
    for source, target in edges:
        predecessors[target] |= 1 << source
    subset_time = [0] * (1 << n)
    for mask in range(1, 1 << n):
        bit = mask & -mask
        subset_time[mask] = subset_time[mask ^ bit] + times[bit.bit_length() - 1]

    current = {0: 0}
    answer = sum(times)
    for _ in range(stations):
        following: dict[int, int] = {}
        for assigned, value in current.items():
            remaining = all_tasks ^ assigned
            station = remaining
            while station:
                feasible = True
                bits = station
                while bits:
                    bit = bits & -bits
                    task = bit.bit_length() - 1
                    if predecessors[task] & ~(assigned | station):
                        feasible = False
                        break
                    bits ^= bit
                if feasible:
                    new_assigned = assigned | station
                    new_value = max(value, subset_time[station])
                    old = following.get(new_assigned)
                    if old is None or new_value < old:
                        following[new_assigned] = new_value
                station = (station - 1) & remaining
            # Empty trailing stations are permitted.
            old = following.get(assigned)
            if old is None or value < old:
                following[assigned] = value
        current = following
        if all_tasks in current:
            answer = min(answer, current[all_tasks])
    return answer


def write_in2(
    path: Path, times: list[int], edges: list[tuple[int, int]]
) -> None:
    rows = [str(len(times)), *(str(value) for value in times)]
    rows.extend(f"{source + 1},{target + 1}" for source, target in edges)
    rows.append("-1,-1")
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def write_tagged_alb(
    path: Path,
    times: list[int],
    edges: list[tuple[int, int]],
    stations: int,
) -> None:
    rows = [
        "<number of tasks>",
        str(len(times)),
        "<number of stations>",
        str(stations),
        "<task times>",
        *(f"{task + 1} {value}" for task, value in enumerate(times)),
        "<precedence relations>",
        *(f"{source + 1},{target + 1}" for source, target in edges),
        "-1,-1",
        "<end>",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def run_solver(
    executable: Path,
    instance: Path,
    stations: Optional[int],
    disable_dominance: bool,
) -> tuple[str, int, int]:
    command = [
        str(executable),
        str(instance),
        "--time-limit",
        "10",
        "--memory-states",
        "1000000",
        "--quiet",
    ]
    if stations is not None:
        command.extend(["--stations", str(stations)])
    if disable_dominance:
        command.append("--no-dominance")
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    match = re.search(
        r"RESULT status=(\S+) LB=(\d+) UB=(\d+)", completed.stdout
    )
    if not match:
        raise AssertionError(f"missing RESULT line:\n{completed.stdout}\n{completed.stderr}")
    return match.group(1), int(match.group(2)), int(match.group(3))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20240807)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    executable = root / "direct_bbr_salbp2"
    if not executable.exists():
        subprocess.run(["make", "direct_bbr_salbp2"], cwd=root, check=True)

    generator = random.Random(args.seed)
    with tempfile.TemporaryDirectory(prefix="direct-bbr-test-") as directory:
        temporary = Path(directory)
        for case in range(args.cases):
            n = generator.randint(5, 9)
            stations = generator.randint(2, min(5, n))
            times = [generator.randint(1, 12) for _ in range(n)]
            edges = [
                (i, j)
                for i in range(n)
                for j in range(i + 1, n)
                if generator.random() < 0.18
            ]
            optimum = brute_force_optimum(times, edges, stations)
            instance = temporary / f"case-{case}.IN2"
            write_in2(instance, times, edges)
            for disable_dominance in (False, True):
                status, lower_bound, upper_bound = run_solver(
                    executable, instance, stations, disable_dominance
                )
                assert status == "OPTIMAL", (case, status)
                assert lower_bound == optimum, (
                    case,
                    "LB",
                    lower_bound,
                    optimum,
                    disable_dominance,
                )
                assert upper_bound == optimum, (
                    case,
                    "UB",
                    upper_bound,
                    optimum,
                    disable_dominance,
                )
        # Exercise the tagged SALBP-2 reader, including its embedded m value.
        tagged_times = [4, 7, 3, 6, 2, 5]
        tagged_edges = [(0, 2), (1, 3), (2, 4), (3, 5)]
        tagged_stations = 3
        tagged_optimum = brute_force_optimum(
            tagged_times, tagged_edges, tagged_stations
        )
        tagged = temporary / "tagged.alb"
        write_tagged_alb(tagged, tagged_times, tagged_edges, tagged_stations)
        status, lower_bound, upper_bound = run_solver(
            executable, tagged, None, False
        )
        assert (status, lower_bound, upper_bound) == (
            "OPTIMAL",
            tagged_optimum,
            tagged_optimum,
        )
    print(f"PASS: {args.cases} randomized cases, seed={args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
