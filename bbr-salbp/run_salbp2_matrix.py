#!/usr/bin/env python3
"""Run the direct BBR executable on the SALBP-2 rows in a manuscript CSV."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path


def read_cases(matrix: Path) -> list[tuple[str, int]]:
    cases: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    with matrix.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.reader(stream))
    if not rows:
        return cases

    normalized_header = [column.strip().lower() for column in rows[0]]
    if "instance" in normalized_header and "m" in normalized_header:
        name_index = normalized_header.index("instance")
        station_index = normalized_header.index("m")
        data_rows = rows[1:]
    else:
        # Backward-compatible reader for the two-row manuscript matrix.
        name_index = 0
        station_index = 2
        data_rows = rows[2:]

    for row in data_rows:
        if len(row) <= max(name_index, station_index):
            continue
        name = row[name_index].strip()
        try:
            stations = int(row[station_index].strip())
        except ValueError:
            continue
        key = (name.upper(), stations)
        if name and key not in seen:
            cases.append(key)
            seen.add(key)
    return cases


def completed_cases(output: Path) -> set[tuple[str, int]]:
    if not output.exists() or output.stat().st_size == 0:
        return set()
    done: set[tuple[str, int]] = set()
    with output.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            try:
                done.add((Path(row["instance"]).stem.upper(), int(row["m"])))
            except (KeyError, ValueError):
                pass
    return done


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_metadata(
    output: Path,
    matrix: Path,
    data_dir: Path,
    solver: Path,
    time_limit: float,
    memory_states: int,
    max_extensions: int,
    extra_arguments: list[str],
) -> None:
    repository_root = solver.parent.parent

    def portable_path(path: Path) -> str:
        try:
            return str(path.relative_to(repository_root))
        except ValueError:
            return str(path)

    try:
        compiler = subprocess.run(
            ["g++", "--version"], text=True, capture_output=True, check=True
        ).stdout.splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        compiler = "unavailable"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=solver.parent,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    metadata = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "Independent Direct BBR reimplementation for SALBP-2",
        "reference": "https://doi.org/10.1016/j.cor.2024.106597",
        "single_threaded": True,
        "matrix_file": portable_path(matrix),
        "matrix_sha256": sha256(matrix),
        "data_directory": portable_path(data_dir),
        "solver_source_sha256": sha256(solver.with_suffix(".cpp")),
        "solver_executable_sha256": sha256(solver),
        "runner_source_sha256": sha256(solver.parent / "run_salbp2_matrix.py"),
        "repository_git_commit": commit,
        "compiler": compiler,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "configuration": {
            "time_limit_seconds_per_instance": time_limit,
            "memory_state_limit": memory_states,
            "max_extensions_per_state_phase_1": max_extensions,
            "extra_solver_arguments": extra_arguments,
        },
    }
    metadata_file = output.with_suffix(".metadata.json")
    metadata_file.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    root = here.parent
    parser = argparse.ArgumentParser(
        description="Run Direct BBR on each (instance,m) row of a SALBP-2 CSV."
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=here / "benchmarks" / "salbp2_classical_73.csv",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=root / "data"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "results" / "direct_bbr_salbp2.csv",
    )
    parser.add_argument("--time-limit", type=float, default=600.0)
    parser.add_argument("--memory-states", type=int, default=60_000_000)
    parser.add_argument("--max-extensions", type=int, default=10_000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, help="run only the first N pending cases")
    parser.add_argument(
        "solver_args", nargs=argparse.REMAINDER, help="extra solver arguments after --"
    )
    args = parser.parse_args()
    # Solver processes run with the workspace root as their working directory.
    # Resolve user-supplied relative paths before changing that directory.
    args.matrix = args.matrix.expanduser().resolve()
    args.data_dir = args.data_dir.expanduser().resolve()
    args.output = args.output.expanduser().resolve()

    solver = here / "direct_bbr_salbp2"
    if not solver.exists():
        subprocess.run(["make", "direct_bbr_salbp2"], cwd=here, check=True)

    if args.output.exists() and args.output.stat().st_size > 0 and not args.resume:
        parser.error(
            f"{args.output} already exists; use --resume or choose another --output"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    extra = args.solver_args
    if extra and extra[0] == "--":
        extra = extra[1:]
    if not args.resume or not args.output.with_suffix(".metadata.json").exists():
        write_metadata(
            args.output,
            args.matrix,
            args.data_dir,
            solver,
            args.time_limit,
            args.memory_states,
            args.max_extensions,
            extra,
        )

    cases = read_cases(args.matrix)
    done = completed_cases(args.output) if args.resume else set()
    pending = [case for case in cases if case not in done]
    if args.limit is not None:
        pending = pending[: args.limit]
    if not pending:
        print("No pending cases.")
        return 0
    failures = 0
    for index, (name, stations) in enumerate(pending, start=1):
        instance = args.data_dir / f"{name}.IN2"
        if not instance.exists():
            print(f"[{index}/{len(pending)}] missing {instance}", file=sys.stderr)
            failures += 1
            continue
        command = [
            str(solver),
            str(instance),
            "--stations",
            str(stations),
            "--time-limit",
            str(args.time_limit),
            "--memory-states",
            str(args.memory_states),
            "--max-extensions",
            str(args.max_extensions),
            "--csv-output",
            str(args.output),
            "--quiet",
        ]
        command.extend(extra)
        print(f"[{index}/{len(pending)}] {name}, m={stations}", flush=True)
        completed = subprocess.run(command, cwd=root, text=True)
        # Exit 2 means a valid incumbent/bounds pair was returned at a resource
        # limit.  It is a completed experiment, not a runner failure.
        if completed.returncode not in (0, 2):
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
