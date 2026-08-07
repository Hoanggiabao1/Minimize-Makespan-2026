#!/usr/bin/env python3
"""Calculate power and cycle-time bounds for the SALBP-CT instances.

The output deliberately distinguishes the following quantities:

* ``power_lb``: maximum task power;
* ``power_ub``: sum of the ``m`` largest task powers;
* ``qmax``: the selected AVG-Peak or UB-LB-Peak threshold;
* ``cycle_lb``: the maximum of the task-duration, workload, and energy
  lower bounds;
* ``initial_horizon``: the first search horizon, which is not assumed to
  be feasible and therefore is not labelled as an upper bound;
* ``certified_cycle_ub``: the cycle time of a feasible sequential
  topological schedule.

By default, the script writes the 72 paper configurations under both Peak
definitions to ``../results/instance_bounds_by_peak.csv``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable, TextIO

from run_full_matrix import MAIN_FAMILIES, Instance, load_instances, read_instance_data
from search_support import (
    average_power_cap,
    initial_probe_horizon,
    topological_order,
    upper_lower_power_cap,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent / "results" / "instance_bounds_by_peak.csv"
PEAK_TYPES = ("avg_peak", "ub_lb_peak")
FIELDNAMES = [
    "instance",
    "n",
    "m",
    "peak_type",
    "power_lb",
    "power_average_numerator",
    "power_average_denominator",
    "power_ub",
    "qmax",
    "total_processing_time",
    "total_energy",
    "duration_lb",
    "workload_lb",
    "energy_lb",
    "cycle_lb",
    "initial_horizon",
    "certified_cycle_ub",
    "cycle_ub_construction",
]


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return (numerator + denominator - 1) // denominator


def read_precedence_edges(name: str) -> tuple[int, list[tuple[int, int]]]:
    """Read the one-based precedence pairs and return zero-based edges."""
    path = ROOT / "data" / f"{name}.IN2"
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_count = int(lines[0])
    edges: list[tuple[int, int]] = []
    for line in lines[task_count + 1 :]:
        source, target = (int(value) for value in line.split(","))
        if (source, target) == (-1, -1):
            break
        edges.append((source - 1, target - 1))
    return task_count, edges


def qmax_for_peak_type(
    peak_type: str, powers: list[int], stations: int
) -> int:
    if peak_type == "avg_peak":
        return average_power_cap(powers, stations)
    if peak_type == "ub_lb_peak":
        return upper_lower_power_cap(powers, stations)
    raise ValueError(f"unknown Peak type: {peak_type}")


def calculate_row(
    instance: Instance, peak_type: str
) -> dict[str, int | str]:
    times, powers = read_instance_data(instance.name)
    task_count, edges = read_precedence_edges(instance.name)
    if task_count != len(times) or len(times) != len(powers):
        raise ValueError(
            f"{instance.name}: inconsistent task, duration, and power counts"
        )
    if not 1 <= instance.m <= task_count:
        raise ValueError(
            f"{instance.name}: station count {instance.m} is outside 1..{task_count}"
        )

    # A topological sequential schedule is feasible whenever one active task
    # fits under Qmax. Checking the graph here certifies the reported UB.
    topological_order(task_count, edges)

    ordered_powers = sorted(powers, reverse=True)
    power_lb = ordered_powers[0]
    power_ub = sum(ordered_powers[: instance.m])
    power_average_numerator = instance.m * sum(powers)
    power_average_denominator = task_count
    qmax = qmax_for_peak_type(peak_type, powers, instance.m)
    if qmax < power_lb:
        raise ValueError(
            f"{instance.name}, m={instance.m}, {peak_type}: "
            "Qmax cannot accommodate the largest task power"
        )

    total_processing_time = sum(times)
    total_energy = sum(time * power for time, power in zip(times, powers))
    duration_lb = max(times)
    workload_lb = ceil_div(total_processing_time, instance.m)
    energy_lb = ceil_div(total_energy, qmax)
    cycle_lb = max(duration_lb, workload_lb, energy_lb)
    initial_horizon = initial_probe_horizon(times, cycle_lb, instance.m)

    # Assign every task to one station and process tasks in topological order.
    # Only one task is active, so power never exceeds max_i w_i <= Qmax.
    certified_cycle_ub = total_processing_time
    if cycle_lb > certified_cycle_ub:
        raise AssertionError("lower bound exceeds the certified sequential UB")

    return {
        "instance": instance.name,
        "n": task_count,
        "m": instance.m,
        "peak_type": peak_type,
        "power_lb": power_lb,
        "power_average_numerator": power_average_numerator,
        "power_average_denominator": power_average_denominator,
        "power_ub": power_ub,
        "qmax": qmax,
        "total_processing_time": total_processing_time,
        "total_energy": total_energy,
        "duration_lb": duration_lb,
        "workload_lb": workload_lb,
        "energy_lb": energy_lb,
        "cycle_lb": cycle_lb,
        "initial_horizon": initial_horizon,
        "certified_cycle_ub": certified_cycle_ub,
        "cycle_ub_construction": "sequential_topological_schedule",
    }


def select_instances(specification: str) -> list[Instance]:
    instances = load_instances()
    if specification == "main":
        return [item for item in instances if item.name in MAIN_FAMILIES]
    if specification == "all":
        return instances

    selectors = {
        item.strip().upper()
        for item in specification.split(",")
        if item.strip()
    }
    selected: list[Instance] = []
    matched: set[str] = set()
    for instance in instances:
        name_selector = instance.name.upper()
        exact_selector = f"{name_selector}:{instance.m}"
        if name_selector in selectors or exact_selector in selectors:
            selected.append(instance)
            if name_selector in selectors:
                matched.add(name_selector)
            if exact_selector in selectors:
                matched.add(exact_selector)
    missing = selectors.difference(matched)
    if missing:
        raise ValueError(f"unknown instance selectors: {', '.join(sorted(missing))}")
    return selected


def parse_peak_types(specification: str) -> list[str]:
    selected = [
        item.strip().lower()
        for item in specification.split(",")
        if item.strip()
    ]
    unknown = set(selected).difference(PEAK_TYPES)
    if not selected or unknown:
        raise ValueError(
            "Peak types must be avg_peak and/or ub_lb_peak; "
            f"unknown: {', '.join(sorted(unknown)) or '(none selected)'}"
        )
    return selected


def calculate_rows(
    instances: Iterable[Instance], peak_types: Iterable[str]
) -> list[dict[str, int | str]]:
    return [
        calculate_row(instance, peak_type)
        for instance in instances
        for peak_type in peak_types
    ]


def write_csv(rows: Iterable[dict[str, int | str]], stream: TextIO) -> None:
    writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instances",
        default="main",
        help="'main', 'all', or comma-separated NAME and NAME:m selectors",
    )
    parser.add_argument(
        "--peak-types",
        default="avg_peak,ub_lb_peak",
        help="comma-separated avg_peak and/or ub_lb_peak",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="output CSV path, or '-' for standard output",
    )
    args = parser.parse_args()

    try:
        instances = select_instances(args.instances)
        peak_types = parse_peak_types(args.peak_types)
    except ValueError as exc:
        parser.error(str(exc))

    rows = calculate_rows(instances, peak_types)
    if args.output == "-":
        write_csv(rows, sys.stdout)
        return 0

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        write_csv(rows, stream)
    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
