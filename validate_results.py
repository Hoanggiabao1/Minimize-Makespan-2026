"""Validate normalized result rows and, optionally, schedule witnesses.

A witness is a JSON object (or an item in a JSON list) with the keys
``instance``, ``m``, ``threshold``, ``solver``, ``edge_set`` and
``assignments``.  Each assignment has one-based ``task`` and ``station``
identifiers and an integer ``start`` time.  Optional ``reported_cycle_time``
and ``qmax`` values are checked against the result row and the instance data.
For backward compatibility, a missing ``edge_set`` is interpreted as ``E``.

For an Optimal row, ``--require-optimal-proof`` additionally requires either
``{"status": "UNSAT", "bound": C - 1}``, a matching MIP/CP objective bound,
or, when the cycle equals the direct processing-time lower bound,
``{"status": "LOWER_BOUND", "bound": C}``.
This checks that the proof record is present and internally consistent;
validating the solver proof itself still requires the native proof/log checker.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

REQUIRED = {
    "instance",
    "n",
    "m",
    "threshold",
    "solver",
    "status",
    "best_cycle_time",
    "elapsed_seconds",
}


def is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def integer(value: Any, label: str) -> int:
    """Return an exact integer and reject booleans and fractional values."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, str) and not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise ValueError(f"{label} must be an integer")
    return parsed


def normalized_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def normalized_edge_set(value: Any) -> str:
    raw = str(value).strip().upper().replace("_", "")
    if raw == "E":
        return "e"
    if raw in {"E*", "ESTAR"}:
        return "estar"
    return normalized_token(value)


def result_key(record: dict[str, Any]) -> tuple[str, int, str, str, str]:
    return (
        str(record.get("instance", "")).strip().upper(),
        integer(record.get("m"), "m"),
        normalized_token(record.get("threshold", "")),
        normalized_token(record.get("solver", "")),
        normalized_edge_set(record.get("edge_set", "E")),
    )


def load_problem(instance: str) -> tuple[list[int], list[tuple[int, int]], list[int]]:
    data_path = ROOT / "data" / f"{instance.upper()}.IN2"
    power_path = ROOT / "task_power" / f"{instance.upper()}.txt"
    if not data_path.exists():
        raise ValueError(f"missing instance file {data_path}")
    if not power_path.exists():
        raise ValueError(f"missing power file {power_path}")

    lines = [line.strip() for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    n = integer(lines[0], "instance task count")
    if len(lines) < n + 2:
        raise ValueError(f"truncated instance file {data_path}")
    times = [integer(value, "processing time") for value in lines[1 : n + 1]]
    edges: list[tuple[int, int]] = []
    for value in lines[n + 1 :]:
        try:
            left, right = value.split(",", maxsplit=1)
        except ValueError as exc:
            raise ValueError(f"invalid precedence row {value!r} in {data_path}") from exc
        i, j = integer(left, "predecessor"), integer(right, "successor")
        if (i, j) == (-1, -1):
            break
        edges.append((i, j))

    powers = [
        integer(line.strip(), "task power")
        for line in power_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(times) != len(powers):
        raise ValueError(
            f"{instance}: {len(times)} processing times but {len(powers)} power values"
        )
    return times, edges, powers


def expected_qmax(threshold: Any, powers: list[int], m: int) -> int:
    token = normalized_token(threshold)
    ordered = sorted(powers, reverse=True)
    upper = sum(ordered[:m])
    lower = max(ordered)
    if token in {"peakublb", "ublb", "qmaxub", "ubpeak"}:
        return (upper + lower) // 2
    if token in {"avgpeak", "peakavg", "qmaxavg", "avg"}:
        return (m * sum(powers) + len(powers) * lower) // (2 * len(powers))
    raise ValueError(f"unrecognized threshold {threshold!r}")


def load_result_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing_columns = REQUIRED.difference(reader.fieldnames or [])
        if missing_columns:
            return [], [f"missing columns: {', '.join(sorted(missing_columns))}"]

        for line_no, row in enumerate(reader, start=2):
            rows.append(row)
            for column in REQUIRED - {"best_cycle_time"}:
                if not row.get(column, "").strip():
                    errors.append(f"line {line_no}: empty {column}")
            if row.get("status", "").strip().lower() == "optimal" and not is_number(
                row.get("best_cycle_time", "")
            ):
                errors.append(f"line {line_no}: optimal row has non-numeric best_cycle_time")
            if row.get("elapsed_seconds") and not is_number(row["elapsed_seconds"]):
                errors.append(f"line {line_no}: elapsed_seconds is not numeric")
            try:
                if integer(row.get("n"), "n") <= 0 or integer(row.get("m"), "m") <= 0:
                    errors.append(f"line {line_no}: n and m must be positive")
            except ValueError as exc:
                errors.append(f"line {line_no}: {exc}")
    return rows, errors


def load_witnesses(directory: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    errors: list[str] = []
    for path in sorted(directory.glob("**/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: cannot read JSON: {exc}")
            continue
        items = payload if isinstance(payload, list) else [payload]
        for index, item in enumerate(items):
            label = f"{path}[{index}]" if isinstance(payload, list) else str(path)
            if not isinstance(item, dict):
                errors.append(f"{label}: witness must be a JSON object")
            else:
                records.append((Path(label), item))
    return records, errors


def validate_witness(
    label: Path,
    witness: dict[str, Any],
    row: dict[str, str],
    require_optimal_proof: bool,
) -> list[str]:
    prefix = str(label)
    errors: list[str] = []
    try:
        key = result_key(witness)
        row_key = result_key(row)
    except ValueError as exc:
        return [f"{prefix}: {exc}"]
    if key != row_key:
        return [f"{prefix}: witness key {key} does not match result key {row_key}"]

    try:
        times, edges, powers = load_problem(key[0])
        m = key[1]
        row_n = integer(row.get("n"), "result n")
        if row_n != len(times):
            errors.append(f"{prefix}: result n={row_n}, instance n={len(times)}")
        qmax = expected_qmax(witness.get("threshold"), powers, m)
    except ValueError as exc:
        return [f"{prefix}: {exc}"]

    if row.get("qmax", "").strip():
        try:
            if integer(row["qmax"], "result qmax") != qmax:
                errors.append(f"{prefix}: result qmax does not equal recomputed qmax={qmax}")
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")
    if "qmax" in witness:
        try:
            if integer(witness["qmax"], "witness qmax") != qmax:
                errors.append(f"{prefix}: witness qmax does not equal recomputed qmax={qmax}")
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")

    assignments = witness.get("assignments")
    if not isinstance(assignments, list):
        return errors + [f"{prefix}: assignments must be a JSON list"]

    schedule: dict[int, tuple[int, int]] = {}
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, dict):
            errors.append(f"{prefix}: assignment {index} is not an object")
            continue
        try:
            task = integer(assignment.get("task"), f"assignment {index} task")
            station = integer(assignment.get("station"), f"assignment {index} station")
            start = integer(assignment.get("start"), f"assignment {index} start")
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        if task in schedule:
            errors.append(f"{prefix}: task {task} appears more than once")
        elif not 1 <= task <= len(times):
            errors.append(f"{prefix}: task {task} is outside 1..{len(times)}")
        else:
            schedule[task] = (station, start)
        if not 1 <= station <= m:
            errors.append(f"{prefix}: task {task} has station {station} outside 1..{m}")
        if start < 0:
            errors.append(f"{prefix}: task {task} has negative start {start}")

    missing = sorted(set(range(1, len(times) + 1)).difference(schedule))
    if missing:
        errors.append(f"{prefix}: missing tasks {missing}")
    if errors:
        return errors

    completion = {task: start + times[task - 1] for task, (_, start) in schedule.items()}
    makespan = max(completion.values(), default=0)
    try:
        reported = integer(row.get("best_cycle_time"), "result best_cycle_time")
    except ValueError as exc:
        return [f"{prefix}: {exc}"]
    if makespan != reported:
        errors.append(f"{prefix}: schedule makespan {makespan} != result {reported}")
    if "reported_cycle_time" in witness:
        try:
            if integer(witness["reported_cycle_time"], "witness reported_cycle_time") != reported:
                errors.append(f"{prefix}: witness and result cycle times differ")
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")

    for i, j in edges:
        station_i, _ = schedule[i]
        station_j, start_j = schedule[j]
        if station_i > station_j:
            errors.append(f"{prefix}: precedence {i}->{j} violates station order")
        elif station_i == station_j and completion[i] > start_j:
            errors.append(f"{prefix}: same-station precedence {i}->{j} overlaps")

    by_station: dict[int, list[int]] = defaultdict(list)
    for task, (station, _) in schedule.items():
        by_station[station].append(task)
    for station, tasks in by_station.items():
        ordered = sorted(tasks, key=lambda task: (schedule[task][1], task))
        for previous, current in zip(ordered, ordered[1:]):
            if completion[previous] > schedule[current][1]:
                errors.append(
                    f"{prefix}: tasks {previous} and {current} overlap at station {station}"
                )

    for slot in range(makespan):
        active = [
            task
            for task, (_, start) in schedule.items()
            if start <= slot < completion[task]
        ]
        load = sum(powers[task - 1] for task in active)
        if load > qmax:
            errors.append(
                f"{prefix}: slot {slot} has power {load} > qmax {qmax}; active tasks {active}"
            )

    if require_optimal_proof and row.get("status", "").strip().lower() == "optimal":
        proof = witness.get("proof")
        if not isinstance(proof, dict):
            errors.append(f"{prefix}: Optimal row lacks a proof object")
        else:
            status = str(proof.get("status", "")).strip().upper()
            try:
                bound = integer(proof.get("bound"), "proof bound")
            except ValueError as exc:
                errors.append(f"{prefix}: {exc}")
            else:
                unsat_certificate = status == "UNSAT" and bound == reported - 1
                direct_lower_bound = (
                    status == "LOWER_BOUND"
                    and bound == reported
                    and reported == max(times)
                )
                bound_match = status == "BOUND_MATCH" and bound == reported
                if not (unsat_certificate or direct_lower_bound or bound_match):
                    errors.append(
                        f"{prefix}: proof must record UNSAT at {reported - 1} "
                        f"or a matching verified bound at {reported}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="normalized full_matrix_runs.csv")
    parser.add_argument("--witness-dir", type=Path, help="directory containing JSON schedule witnesses")
    parser.add_argument(
        "--require-optimal-witness",
        action="store_true",
        help="fail when an Optimal result row has no matching witness",
    )
    parser.add_argument(
        "--require-optimal-proof",
        action="store_true",
        help="require each witnessed Optimal row to record UNSAT at C-1",
    )
    args = parser.parse_args()

    if not args.results.exists():
        print(f"missing file: {args.results}")
        return 1
    if args.require_optimal_witness and args.witness_dir is None:
        parser.error("--require-optimal-witness requires --witness-dir")
    if args.require_optimal_proof and args.witness_dir is None:
        parser.error("--require-optimal-proof requires --witness-dir")

    rows, errors = load_result_rows(args.results)
    witness_count = 0
    if args.witness_dir is not None:
        if not args.witness_dir.is_dir():
            errors.append(f"missing witness directory: {args.witness_dir}")
        else:
            row_index: dict[tuple[str, int, str, str, str], dict[str, str]] = {}
            for row in rows:
                try:
                    key = result_key(row)
                except ValueError as exc:
                    errors.append(f"invalid result key: {exc}")
                    continue
                if key in row_index:
                    errors.append(f"duplicate result key {key}; witnesses would be ambiguous")
                row_index[key] = row

            witnessed_keys: set[tuple[str, int, str, str, str]] = set()
            witnesses, witness_errors = load_witnesses(args.witness_dir)
            errors.extend(witness_errors)
            for label, witness in witnesses:
                try:
                    key = result_key(witness)
                except ValueError as exc:
                    errors.append(f"{label}: invalid witness key: {exc}")
                    continue
                row = row_index.get(key)
                if row is None:
                    errors.append(f"{label}: no matching result row for {key}")
                    continue
                if key in witnessed_keys:
                    errors.append(f"{label}: duplicate witness for {key}")
                    continue
                witnessed_keys.add(key)
                witness_count += 1
                errors.extend(validate_witness(label, witness, row, args.require_optimal_proof))

            if args.require_optimal_witness:
                for key, row in row_index.items():
                    if row.get("status", "").strip().lower() == "optimal" and key not in witnessed_keys:
                        errors.append(f"Optimal row {key} has no schedule witness")

    if errors:
        for error in errors[:100]:
            print(error)
        if len(errors) > 100:
            print(f"... {len(errors) - 100} more errors")
        return 1

    message = f"validated {len(rows)} result rows"
    if args.witness_dir is not None:
        message += f" and {witness_count} schedule witnesses"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
