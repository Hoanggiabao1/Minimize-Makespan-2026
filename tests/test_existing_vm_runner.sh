#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/salbp-existing-vm-test.XXXXXX")"
trap 'rm -rf "${TMP_DIR}"' EXIT

run_experiment() {
    RUN_ID=existing-vm-smoke \
    RESULT_DIR="${TMP_DIR}/results" \
    INSTANCES=MERTENS:6 \
    SOLVERS=sm \
    THRESHOLDS=peak_ub_lb \
    EDGE_SETS=E \
    TIMEOUT_SECONDS=30 \
    PRIMAL_CONFLICT_BUDGET=5000 \
    ENABLE_CSE17=0 \
    RESUME="$1" \
    "${ROOT_DIR}/scripts/run_existing_vm.sh"
}

run_experiment 0

test -s "${TMP_DIR}/results/full_matrix_runs.csv"
test -s "${TMP_DIR}/results/full_matrix_events.jsonl"
test -s "${TMP_DIR}/results/validation.log"
grep -q '^STATUS=SUCCESS$' "${TMP_DIR}/results/completion.env"
grep -q 'MERTENS' "${TMP_DIR}/results/full_matrix_runs.csv"
test -s "${TMP_DIR}/salbp-results-existing-vm-smoke.tar.gz"
test -s "${TMP_DIR}/salbp-results-existing-vm-smoke.tar.gz.sha256"

run_experiment 1
test "$(wc -l < "${TMP_DIR}/results/full_matrix_runs.csv")" -eq 2

printf 'Existing-VM runner test passed.\n'
