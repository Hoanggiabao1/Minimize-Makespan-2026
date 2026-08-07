# Direct BBR for SALBP-2

This directory contains a standalone, independent reimplementation of the
direct SALBP-2 method described in:

> E. Alvarez-Miranda, J. Pereira, and M. Vila (2024), "A branch, bound and
> remember algorithm for maximizing the production rate in the simple assembly
> line balancing problem", *Computers & Operations Research* 166, 106597.

It is not the authors' unpublished source code. See
`DIRECT_BBR_IMPLEMENTATION.md` for the implemented components and the
differences that must be disclosed in a runtime comparison.

## Build and test

```sh
make
make test
```

The build requires a C++17 compiler. The solver is single-threaded.

## Solve one instance

An `.IN2` file does not contain the number of stations, so provide it with
`--stations`:

```sh
./direct_bbr_salbp2 ../data/BUXEY.IN2 \
  --stations 7 \
  --time-limit 600 \
  --csv-output ../results/direct_bbr_salbp2.csv \
  --solution-output buxey-m7.sol
```

The reader also accepts tagged `.alb` SALBP-2 files containing
`<number of tasks>`, `<number of stations>`, `<task times>`, and
`<precedence relations>`. `--stations` overrides an embedded station count.

All reported incumbents are validated before output. A resource-limited run
reports a valid lower bound and feasible upper bound; only `status=OPTIMAL`
means that `LB=UB` was proved.

## Run the bundled benchmark

The repository includes 73 classical configurations in
`benchmarks/salbp2_classical_73.csv`:

```sh
python3 run_salbp2_matrix.py --time-limit 600
```

The runner writes:

- `../results/direct_bbr_salbp2.csv`, one row per configuration;
- `../results/direct_bbr_salbp2.metadata.json`, containing configuration,
  compiler/platform information, Git commit, and file checksums.

Use `--resume` to skip configurations already present in the result CSV. The
runner refuses to append to an existing result file unless `--resume` is
specified.
