#!/usr/bin/env bash
set -Eeuo pipefail

umask 022

: "${SALBP_RUN_ID:?SALBP_RUN_ID is required}"
: "${SALBP_RUN_ROOT:?SALBP_RUN_ROOT is required}"
: "${SALBP_SOURCE_DIR:?SALBP_SOURCE_DIR is required}"

INSTANCES="${SALBP_INSTANCES:-main}"
SOLVERS="${SALBP_SOLVERS:-origin,sm,sm_tij}"
THRESHOLDS="${SALBP_THRESHOLDS:-peak_ub_lb,avg_peak}"
EDGE_SETS="${SALBP_EDGE_SETS:-E}"
TIMEOUT_SECONDS="${SALBP_TIMEOUT_SECONDS:-3600}"
PRIMAL_CONFLICT_BUDGET="${SALBP_PRIMAL_CONFLICT_BUDGET:-50000}"
ENABLE_CSE17="${SALBP_ENABLE_CSE17:-0}"
SOURCE_COMMIT="${SALBP_SOURCE_COMMIT:-unknown}"
SOURCE_ARCHIVE_SHA256="${SALBP_SOURCE_ARCHIVE_SHA256:-unknown}"
SKIP_SYSTEM_SETUP="${SALBP_SKIP_SYSTEM_SETUP:-0}"

ARTIFACT_DIR="${SALBP_RUN_ROOT}/artifacts"
RESULT_CSV="${ARTIFACT_DIR}/full_matrix_runs.csv"
EVENT_LOG="${ARTIFACT_DIR}/full_matrix_events.jsonl"
WITNESS_DIR="${ARTIFACT_DIR}/schedule_witnesses"
ARCHIVE_NAME="salbp-results-${SALBP_RUN_ID}.tar.gz"
ARCHIVE_PATH="${SALBP_RUN_ROOT}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

mkdir -p "${ARTIFACT_DIR}" "${WITNESS_DIR}"
exec > >(tee -a "${ARTIFACT_DIR}/experiment.log") 2>&1

RUNNER_EXIT_CODE=125
VALIDATOR_EXIT_CODE=125

finish() {
    local exit_code=$?
    local status="FAILED"
    trap - EXIT
    set +e

    if [[ ${exit_code} -eq 0 ]]; then
        status="SUCCESS"
    fi

    {
        printf 'STATUS=%s\n' "${status}"
        printf 'RUN_ID=%s\n' "${SALBP_RUN_ID}"
        printf 'RUNNER_EXIT_CODE=%s\n' "${RUNNER_EXIT_CODE}"
        printf 'VALIDATOR_EXIT_CODE=%s\n' "${VALIDATOR_EXIT_CODE}"
        printf 'ARTIFACT=%s\n' "${ARCHIVE_NAME}"
        printf 'FINISHED_AT_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${ARTIFACT_DIR}/completion.env"

    sync
    tar -czf "${ARCHIVE_PATH}" -C "${ARTIFACT_DIR}" .
    (cd "${SALBP_RUN_ROOT}" && sha256sum "${ARCHIVE_NAME}" > "${ARCHIVE_NAME}.sha256")
    chmod -R a+rX "${ARTIFACT_DIR}"
    chmod a+r "${ARCHIVE_PATH}" "${CHECKSUM_PATH}"
    exit "${exit_code}"
}
trap finish EXIT

printf 'Starting SALBP-CT experiment %s at %s\n' "${SALBP_RUN_ID}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

export DEBIAN_FRONTEND=noninteractive
if [[ "${SKIP_SYSTEM_SETUP}" == "1" ]]; then
    PYTHON_BIN="${SALBP_PYTHON_BIN:-python3}"
else
    apt-get update
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        python3-dev \
        python3-pip \
        python3-venv

    python3 -m venv "${SALBP_RUN_ROOT}/venv"
    "${SALBP_RUN_ROOT}/venv/bin/python" -m pip install --upgrade pip setuptools wheel
    "${SALBP_RUN_ROOT}/venv/bin/python" -m pip install -r "${SALBP_SOURCE_DIR}/requirements-sat.txt"
    PYTHON_BIN="${SALBP_RUN_ROOT}/venv/bin/python"
fi

"${PYTHON_BIN}" - <<'PY'
import pysat
from pysat.solvers import Cadical195

solver = Cadical195()
solver.delete()
print(f"python-sat={pysat.__version__}; Cadical195 binding available")
PY

mkdir -p \
    "${SALBP_SOURCE_DIR}/AVG_Peak/Output" \
    "${SALBP_SOURCE_DIR}/Peak_UB_LB/Output"

{
    printf 'run_id=%s\n' "${SALBP_RUN_ID}"
    printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'source_commit=%s\n' "${SOURCE_COMMIT}"
    printf 'source_archive_sha256=%s\n' "${SOURCE_ARCHIVE_SHA256}"
    printf 'instances=%s\n' "${INSTANCES}"
    printf 'solvers=%s\n' "${SOLVERS}"
    printf 'thresholds=%s\n' "${THRESHOLDS}"
    printf 'edge_sets=%s\n' "${EDGE_SETS}"
    printf 'timeout_seconds=%s\n' "${TIMEOUT_SECONDS}"
    printf 'primal_conflict_budget=%s\n' "${PRIMAL_CONFLICT_BUDGET}"
    printf 'cse17_enabled=%s\n' "${ENABLE_CSE17}"
    printf 'thread_policy=SAT:1\n'
    printf 'seed_policy=solver_default\n'
} > "${ARTIFACT_DIR}/run_manifest.txt"

uname -a > "${ARTIFACT_DIR}/uname.txt"
if command -v lscpu >/dev/null 2>&1; then
    lscpu > "${ARTIFACT_DIR}/lscpu.txt"
else
    printf 'lscpu is unavailable on this host.\n' > "${ARTIFACT_DIR}/lscpu.txt"
fi
if [[ -f /etc/os-release ]]; then
    cp /etc/os-release "${ARTIFACT_DIR}/os-release.txt"
else
    printf 'os-release is unavailable on this host.\n' > "${ARTIFACT_DIR}/os-release.txt"
fi
"${PYTHON_BIN}" -m pip freeze > "${ARTIFACT_DIR}/pip-freeze.txt"
"${PYTHON_BIN}" - "${SALBP_SOURCE_DIR}" > "${ARTIFACT_DIR}/input-files.sha256" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
for directory in (root / "data", root / "task_power"):
    for path in sorted(directory.iterdir()):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"{digest}  {path.relative_to(root)}")
PY

cd "${SALBP_SOURCE_DIR}"
set +e
PYTHONUNBUFFERED=1 \
SALBP_PRIMAL_CONFLICT_BUDGET="${PRIMAL_CONFLICT_BUDGET}" \
SALBP_ENABLE_CSE17="${ENABLE_CSE17}" \
"${PYTHON_BIN}" run_full_matrix.py \
    --instances "${INSTANCES}" \
    --solvers "${SOLVERS}" \
    --thresholds "${THRESHOLDS}" \
    --edge-sets "${EDGE_SETS}" \
    --timeout "${TIMEOUT_SECONDS}" \
    --results "${RESULT_CSV}" \
    --event-log "${EVENT_LOG}" \
    --witness-dir "${WITNESS_DIR}"
RUNNER_EXIT_CODE=$?
set -e

if [[ -s "${RESULT_CSV}" ]]; then
    set +e
    "${PYTHON_BIN}" validate_results.py \
        "${RESULT_CSV}" \
        --witness-dir "${WITNESS_DIR}" \
        --require-optimal-witness \
        --require-optimal-proof \
        > "${ARTIFACT_DIR}/validation.log" 2>&1
    VALIDATOR_EXIT_CODE=$?
    set -e
else
    printf 'Result CSV was not created.\n' > "${ARTIFACT_DIR}/validation.log"
    VALIDATOR_EXIT_CODE=1
fi

cat "${ARTIFACT_DIR}/validation.log"
if [[ ${RUNNER_EXIT_CODE} -ne 0 || ${VALIDATOR_EXIT_CODE} -ne 0 ]]; then
    exit 1
fi

printf 'Experiment and validation completed successfully.\n'
