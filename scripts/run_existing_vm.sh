#!/usr/bin/env bash
set -Eeuo pipefail

# Execute the reproducible SAT matrix in an already prepared VM environment.
# This script never installs software, creates a virtual environment, or
# provisions cloud resources.  PYTHON_BIN must point to the environment that
# was used to validate the solver installation on the VM.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RESULT_DIR="${RESULT_DIR:-${ROOT_DIR}/../results/gcp/${RUN_ID}}"
INSTANCES="${INSTANCES:-main}"
SOLVERS="${SOLVERS:-origin,sm,sm_tij}"
THRESHOLDS="${THRESHOLDS:-peak_ub_lb,avg_peak}"
EDGE_SETS="${EDGE_SETS:-E}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-3600}"
PRIMAL_CONFLICT_BUDGET="${PRIMAL_CONFLICT_BUDGET:-50000}"
ENABLE_CSE17="${ENABLE_CSE17:-0}"
PACKAGE_RESULTS="${PACKAGE_RESULTS:-1}"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

[[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid RUN_ID: ${RUN_ID}"
[[ "${TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "TIMEOUT_SECONDS must be positive"
[[ "${PRIMAL_CONFLICT_BUDGET}" =~ ^[1-9][0-9]*$ ]] || die "PRIMAL_CONFLICT_BUDGET must be positive"
[[ "${ENABLE_CSE17}" == "0" || "${ENABLE_CSE17}" == "1" ]] || die "ENABLE_CSE17 must be 0 or 1"
[[ "${PACKAGE_RESULTS}" == "0" || "${PACKAGE_RESULTS}" == "1" ]] || die "PACKAGE_RESULTS must be 0 or 1"
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "PYTHON_BIN is not executable: ${PYTHON_BIN}"

ARTIFACT_DIR="${RESULT_DIR}"
RESULT_CSV="${ARTIFACT_DIR}/full_matrix_runs.csv"
EVENT_LOG="${ARTIFACT_DIR}/full_matrix_events.jsonl"
WITNESS_DIR="${ARTIFACT_DIR}/schedule_witnesses"
if [[ -d "${ARTIFACT_DIR}" ]] && [[ -n "$(find "${ARTIFACT_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    die "RESULT_DIR already contains files; choose a new run directory: ${ARTIFACT_DIR}"
fi
mkdir -p "${ARTIFACT_DIR}" "${WITNESS_DIR}"
ARCHIVE_DIR="$(cd "$(dirname "${RESULT_DIR}")" && pwd)"
ARCHIVE_NAME="salbp-results-${RUN_ID}.tar.gz"
ARCHIVE_PATH="${ARCHIVE_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"
if [[ "${PACKAGE_RESULTS}" == "1" ]] && [[ -e "${ARCHIVE_PATH}" || -e "${CHECKSUM_PATH}" ]]; then
    die "result archive already exists; choose a new RUN_ID or RESULT_DIR: ${ARCHIVE_PATH}"
fi

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
        printf 'RUN_ID=%s\n' "${RUN_ID}"
        printf 'RUNNER_EXIT_CODE=%s\n' "${RUNNER_EXIT_CODE}"
        printf 'VALIDATOR_EXIT_CODE=%s\n' "${VALIDATOR_EXIT_CODE}"
        printf 'FINISHED_AT_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${ARTIFACT_DIR}/completion.env"

    if [[ "${PACKAGE_RESULTS}" == "1" ]]; then
        tar -czf "${ARCHIVE_PATH}" -C "${ARTIFACT_DIR}" .
        printf '%s  %s\n' "$(sha256_file "${ARCHIVE_PATH}")" "${ARCHIVE_NAME}" > "${CHECKSUM_PATH}"
        printf 'Result archive: %s\nChecksum: %s\n' "${ARCHIVE_PATH}" "${CHECKSUM_PATH}"
    fi
    exit "${exit_code}"
}
trap finish EXIT

printf 'Starting SALBP-CT experiment %s at %s\n' "${RUN_ID}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'Repository: %s\nPython: %s\nResult directory: %s\n' "${ROOT_DIR}" "${PYTHON_BIN}" "${ARTIFACT_DIR}"

"${PYTHON_BIN}" - <<'PY'
import pysat
from pysat.solvers import Cadical195

solver = Cadical195()
solver.delete()
print(f"python-sat={pysat.__version__}; Cadical195 binding available")
PY

mkdir -p "${ROOT_DIR}/AVG_Peak/Output" "${ROOT_DIR}/Peak_UB_LB/Output"

source_commit="$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || printf 'unknown')"
if [[ "${source_commit}" == "unknown" ]]; then
    source_tree_state="not-a-git-worktree"
elif [[ -z "$(git -C "${ROOT_DIR}" status --porcelain)" ]]; then
    source_tree_state="clean"
else
    source_tree_state="dirty"
fi
{
    printf 'run_id=%s\n' "${RUN_ID}"
    printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'source_commit=%s\n' "${source_commit}"
    printf 'source_tree_state=%s\n' "${source_tree_state}"
    printf 'python_bin=%s\n' "${PYTHON_BIN}"
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
"${PYTHON_BIN}" -m pip freeze > "${ARTIFACT_DIR}/pip-freeze.txt" 2>&1 || true
"${PYTHON_BIN}" - "${ROOT_DIR}" > "${ARTIFACT_DIR}/input-files.sha256" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
for directory in (root / "data", root / "task_power"):
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                print(f"{digest}  {path.relative_to(root)}")
PY

cd "${ROOT_DIR}"
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
