# Direct BBR SALBP-2 implementation notes

## Scope

`direct_bbr_salbp2` is an independent implementation from the algorithmic
description in Alvarez-Miranda, Pereira, and Vila (2024), DOI
`10.1016/j.cor.2024.106597`. It is not the authors' unpublished source code and
must not be described as a byte-for-byte or timing-equivalent reproduction of
their executable.

This directory intentionally contains only the independent SALBP-2
implementation; the external SALBP-1 source tree is not vendored.

## Paper components implemented

- direct station-oriented states `(T,k)` with the state's cycle-time lower bound
  as its value;
- cyclic queue selection and idle-time priority within each station-level
  queue;
- replacement and reopening when an equivalent state is reached with a better
  value;
- the preliminary phase capped at 10,000 station-load extensions per state,
  followed by an unrestricted phase when needed;
- parallel-machine lower bound LB1 and the task-counting lower bound LB2;
- SALBP-1-derived LM2, LM3, Dell'Amico--Martello L3, and root LM4 bounds;
- Fibonacci-guided construction of an initial feasible solution;
- solitary-task, maximum-load, successor, Jackson, memory, and generalized
  Jackson tests;
- valid frontier lower bounds on timeout or state-memory exhaustion;
- validation of every reported incumbent against assignment, station-load, and
  precedence constraints.

## Deliberate implementation differences

- The initial solution routine is a deterministic multi-rule,
  station-oriented constructive heuristic. It follows the role of the
  Hoffmann-based initial phase but does not claim identical coefficient sets or
  tie-breaking to the authors' program.
- State memory uses `std::unordered_map`; the paper reports STL `map`.
- Pending-predecessor counts use signed 16-bit values rather than the
  one-byte encoding used in the paper's memory estimate.
- The default cyclic selector is the original selector, not the Li et al.
  next-queue throttling variant.
- LM4 is enabled at the root and disabled inside enumeration by default,
  matching the best configuration reported for the classical experiments.
- Timing is single-process wall-clock time and includes parsing, preprocessing,
  the initial solution, and both search phases. The authors report experiments
  on a different hardware/software platform; raw runtimes are therefore not
  directly comparable.

## Reproducibility

`run_salbp2_matrix.py` writes:

- one flat result CSV with a stable instance identifier, bounds, gap, resource
  limits, enabled rules, and search counters;
- a sibling `.metadata.json` with timestamps, hashes of the matrix/source/
  executable and runner, compiler and platform information, the repository commit,
  and the complete run configuration.

Only rows with `status=OPTIMAL` and `LB=UB` are proof-complete. A `TIME_LIMIT`
or `MEMORY_LIMIT` row still contains a validated feasible `UB` and a valid
search `LB`.
