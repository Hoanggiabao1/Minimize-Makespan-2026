# SALBP-CT minimize-makespan experiments

This directory is the current source snapshot for the revised SALBP-CT
experiments.  The objective is to minimize the cycle time (makespan) subject
to station assignment, precedence, non-overlap, and a global power cap.

## Experimental variants

- `Peak_UB_LB/`: `Qmax = floor((sum of the m largest powers + max power) / 2)`.
- `AVG_Peak/`: `Qmax = floor((m * average power + max power) / 2)`.
- `Minimize_makespan_origin.py`: baseline incremental SAT encoding.
- `Minimize_makespan_SM.py`: sequential-merger encoding.
- `Minimize_makespan_SM_Ti,j.py`: task-pair-specific sequential-merger encoding.
- `Minimize_makespan_cplex.py`: IBM CP Optimizer model (CPO).
- `Minimize_makespan_cplex_mp.py`: CPLEX-MIP model.
- `*gurobi.py`: Gurobi MIP model.

The SAT entrypoints use the direct precedence arcs `E` by default.  Pass `E*`
as the third argument to run the explicitly reported transitive-closure
variant.  CPO and Gurobi use the direct arcs and are run once per configuration.

The revised source and matrix runner:

- compute duration, workload, and power-energy lower bounds;
- print a deterministic sequential incumbent before any SAT call;
- run conflict-bounded feasible-first probes and distinguish UNKNOWN from UNSAT;
- retain the first successful SAT solver state for the exact incremental phase;
- enforce valid start-time indices at both ends of the horizon;
- print one assignment line per task for schedule validation;
- emit machine-readable search events and append a normalized result row.

The default Phase-I budget is 50,000 conflicts per horizon.  Override it with
`SALBP_PRIMAL_CONFLICT_BUDGET`; changing it defines a different experimental
configuration and must be recorded with the results.

CSE-17 is available through `SALBP_ENABLE_CSE17=1` but is disabled in the
locked paper matrix.  Its value is recorded in every new SAT result row.

## Dependencies

- Python 3;
- PySAT 1.8.dev20 for the SAT encodings (pinned in `requirements-sat.txt`);
- `docplex` and a licensed CP Optimizer executable for CPO;
- `gurobipy`, `python-dotenv`, and valid `WLSACCESSID`, `WLSSECRET`, and
  `LICENSEID` environment values for Gurobi.

Set `CPO_EXECFILE` when CP Optimizer is not discoverable through the default
DOcplex configuration.  License values must remain outside version control.

## Run one configuration

From this directory:

```bash
python3 Peak_UB_LB/Minimize_makespan_origin.py MERTENS 6 E
python3 Peak_UB_LB/Minimize_makespan_SM.py MERTENS 6 E
python3 'Peak_UB_LB/Minimize_makespan_SM_Ti,j.py' MERTENS 6 E
python3 Peak_UB_LB/Minimize_makespan_cplex.py MERTENS 6 10
python3 Peak_UB_LB/Minimize_makespan_cplex_mp.py MERTENS 6
python3 Peak_UB_LB/Minimize_makespan_gurobi.py MERTENS 6 10
```

For CPO and Gurobi, the final argument is the initial horizon; the current
CPLEX-MIP entrypoint computes it internally.  The full-matrix runner computes
the analytical lower bound first and then uses
`max(LB0, ceil(2 * total processing time / m))`.

## Run the normalized matrix

Inspect commands without creating output:

```bash
python3 run_full_matrix.py --dry-run --instances MERTENS:6 \
  --edge-sets 'E,E*'
```

Run a smoke matrix:

```bash
python3 run_full_matrix.py --instances smoke --edge-sets 'E,E*' \
  --results ../results/full_matrix_runs.csv \
  --event-log ../results/full_matrix_events.jsonl \
  --witness-dir ../results/schedule_witnesses
```

The runner defaults to the three SAT encodings on the 72 paper configurations
and direct arcs `E`.  `--instances` accepts `main`, `all`, `smoke`, family names
such as `MERTENS`, and exact `NAME:m` selectors such as `MERTENS:6`.  `main`
selects the locked 72-configuration inventory.  `all` additionally includes
13 diagnostic WEEMAG configurations.  Duplicate legacy rows are removed
because their old cycle-time field is not an input to the revised problem.

Commercial solvers are opt-in because they require separate installations and
licenses:

```bash
python3 run_full_matrix.py --instances main \
  --solvers cplex_cp,cplex_mip,gurobi --edge-sets E
```

Use a new result path for a fresh campaign.  The normalized CSV records the
threshold, solver, edge set, search policy, resource policy, initial and final
bounds, certified gap, incumbent milestones, hashes, witness path, model size,
elapsed time, and a short stdout tail.  The JSONL event file records every
bounded feasibility result, incumbent, and exact improvement result.  The matrix runner
enforces a 3,600-second cutoff for SAT processes and labels an externally
terminated run `TIMEOUT`; unbuffered solver output preserves the latest printed
incumbent for the normalized record.  CPO and Gurobi stop internally at 3,600
seconds and receive a 60-second serialization grace period.  Gurobi uses a 4
GB `SoftMemLimit`, allowing a graceful exit with incumbent and bound
information when the limit is reached.

## Validate results and schedules

```bash
python3 validate_results.py ../results/full_matrix_runs.csv \
  --witness-dir ../results/schedule_witnesses \
  --require-optimal-witness --require-optimal-proof
```

The validator recomputes the power cap and checks every witnessed assignment,
precedence relation, same-station non-overlap, makespan, and per-slot power
load.  For an `Optimal` row it can additionally require an UNSAT record at
`C-1`, a direct lower-bound record, or a matching CPO/MIP objective bound.

CP Optimizer and CPLEX-MIP remain separate solver identifiers and output files;
do not merge their result columns.

## Run the SAT campaign in the existing VM environment

The campaign runner deliberately does not provision a VM, install packages, or
create a virtual environment.  Run it from the repository checkout that uses
the already validated solver and license environment.  It records the Python
environment and host metadata, validates all witnessed schedules and optimality
records, then produces a checksummed result archive.

For the locked primary matrix (72 configurations, two caps, three SAT
encodings, direct arcs), run on the VM:

```bash
cd /path/to/Minimize-Makespan-2026
PYTHON_BIN=/path/to/existing/environment/bin/python \
RESULT_DIR=/path/to/results/two-phase-$(date -u +%Y%m%dT%H%M%SZ) \
./scripts/run_existing_vm.sh
```

`PYTHON_BIN` defaults to `python3`.  `RESULT_DIR` defaults to
`../results/gcp/<run-id>/` relative to the repository.  The run directory
contains the normalized CSV, event log, witness files, validation log, manifest,
input hashes, host/Python metadata, and `completion.env`.  Its parent directory
receives `salbp-results-<run-id>.tar.gz` and a SHA-256 checksum.

First verify the setup with one small configuration:

```bash
PYTHON_BIN=/path/to/existing/environment/bin/python \
RUN_ID=smoke-$(date -u +%Y%m%dT%H%M%SZ) \
RESULT_DIR=/path/to/results/smoke \
INSTANCES=MERTENS:6 SOLVERS=sm THRESHOLDS=peak_ub_lb EDGE_SETS=E \
TIMEOUT_SECONDS=30 PRIMAL_CONFLICT_BUDGET=5000 \
./scripts/run_existing_vm.sh
```

The scientific campaign must retain `TIMEOUT_SECONDS=3600`,
`PRIMAL_CONFLICT_BUDGET=50000`, default SAT threading, and the solver-default
seed policy.  Keep `ENABLE_CSE17=0` for the locked paper matrix.  To cover the
reported closure sensitivity, set `EDGE_SETS='E,E*'`; this doubles the primary
SAT matrix to 864 sequential runs.
