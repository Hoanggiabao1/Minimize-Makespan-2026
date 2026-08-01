#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-plan}"

PROJECT_ID="${PROJECT_ID:-}"
ZONE="${ZONE:-us-west4-a}"
INSTANCE_NAME="${INSTANCE_NAME:-salbp-ct-two-phase}"
MACHINE_TYPE="${MACHINE_TYPE:-c4-highcpu-8}"
IMAGE_PROJECT="${IMAGE_PROJECT:-ubuntu-os-pro-cloud}"
IMAGE_FAMILY="${IMAGE_FAMILY:-ubuntu-pro-2004-lts}"
BOOT_DISK_SIZE="${BOOT_DISK_SIZE:-50GB}"
BOOT_DISK_TYPE="${BOOT_DISK_TYPE:-hyperdisk-balanced}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
INSTANCES="${INSTANCES:-main}"
SOLVERS="${SOLVERS:-origin,sm,sm_tij}"
THRESHOLDS="${THRESHOLDS:-peak_ub_lb,avg_peak}"
EDGE_SETS="${EDGE_SETS:-E}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-3600}"
PRIMAL_CONFLICT_BUDGET="${PRIMAL_CONFLICT_BUDGET:-50000}"
ENABLE_CSE17="${ENABLE_CSE17:-0}"
POLL_SECONDS="${POLL_SECONDS:-60}"
KEEP_VM="${KEEP_VM:-0}"
KEEP_VM_ON_ERROR="${KEEP_VM_ON_ERROR:-0}"
USE_IAP="${USE_IAP:-0}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"
STATE_DIR="${STATE_DIR:-${ROOT_DIR}/.gcp-experiment}"
LOCAL_RESULTS_DIR="${LOCAL_RESULTS_DIR:-${ROOT_DIR}/../results/gcp}"

REMOTE_DIR="/opt/salbp-ct/${RUN_ID}"
REMOTE_SOURCE_DIR="${REMOTE_DIR}/source"
UNIT_NAME="$(printf 'salbp-experiment-%s' "${RUN_ID}" | tr '[:upper:]' '[:lower:]')"
UNIT_NAME="${UNIT_NAME//[^a-z0-9-]/-}"
STATE_FILE="${STATE_DIR}/${INSTANCE_NAME}.env"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

validate_config() {
    [[ "${ZONE}" =~ ^[a-z0-9-]+$ ]] || die "invalid ZONE: ${ZONE}"
    [[ "${INSTANCE_NAME}" =~ ^[a-z]([-a-z0-9]*[a-z0-9])?$ ]] || die "invalid INSTANCE_NAME: ${INSTANCE_NAME}"
    [[ "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid RUN_ID: ${RUN_ID}"
    [[ "${TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "TIMEOUT_SECONDS must be positive"
    [[ "${PRIMAL_CONFLICT_BUDGET}" =~ ^[1-9][0-9]*$ ]] || die "PRIMAL_CONFLICT_BUDGET must be positive"
    [[ "${ENABLE_CSE17}" == "0" || "${ENABLE_CSE17}" == "1" ]] || die "ENABLE_CSE17 must be 0 or 1"
    [[ "${ALLOW_DIRTY}" == "0" || "${ALLOW_DIRTY}" == "1" ]] || die "ALLOW_DIRTY must be 0 or 1"
    [[ "${POLL_SECONDS}" =~ ^[1-9][0-9]*$ ]] || die "POLL_SECONDS must be positive"
}

gcloud_base() {
    gcloud "$@" --project "${PROJECT_ID}"
}

ssh_args() {
    SSH_ARGS=("${INSTANCE_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}")
    if [[ "${USE_IAP}" == "1" ]]; then
        SSH_ARGS+=(--tunnel-through-iap)
    fi
}

compute_scp() {
    if [[ "${USE_IAP}" == "1" ]]; then
        gcloud compute scp "$@" --zone "${ZONE}" --project "${PROJECT_ID}" --tunnel-through-iap
    else
        gcloud compute scp "$@" --zone "${ZONE}" --project "${PROJECT_ID}"
    fi
}

load_state() {
    [[ -f "${STATE_FILE}" ]] || die "state file not found: ${STATE_FILE}"
    # The state file is created locally by write_state and contains shell-quoted values.
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
    REMOTE_DIR="/opt/salbp-ct/${RUN_ID}"
    REMOTE_SOURCE_DIR="${REMOTE_DIR}/source"
    UNIT_NAME="$(printf 'salbp-experiment-%s' "${RUN_ID}" | tr '[:upper:]' '[:lower:]')"
    UNIT_NAME="${UNIT_NAME//[^a-z0-9-]/-}"
}

write_state() {
    mkdir -p "${STATE_DIR}"
    {
        printf 'PROJECT_ID=%q\n' "${PROJECT_ID}"
        printf 'ZONE=%q\n' "${ZONE}"
        printf 'INSTANCE_NAME=%q\n' "${INSTANCE_NAME}"
        printf 'RUN_ID=%q\n' "${RUN_ID}"
        printf 'USE_IAP=%q\n' "${USE_IAP}"
        printf 'LOCAL_RESULTS_DIR=%q\n' "${LOCAL_RESULTS_DIR}"
    } > "${STATE_FILE}"
}

resolve_project() {
    if [[ -z "${PROJECT_ID}" ]]; then
        PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
    fi
    [[ -n "${PROJECT_ID}" && "${PROJECT_ID}" != "(unset)" ]] || \
        die "set PROJECT_ID or configure a default gcloud project"
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

plan() {
    validate_config
    require_command python3
    local command_count
    command_count="$(python3 "${ROOT_DIR}/run_full_matrix.py" \
        --dry-run \
        --instances "${INSTANCES}" \
        --solvers "${SOLVERS}" \
        --thresholds "${THRESHOLDS}" \
        --edge-sets "${EDGE_SETS}" | wc -l | tr -d ' ')"
    printf 'Project:             %s\n' "${PROJECT_ID:-<set PROJECT_ID before submit>}"
    printf 'Zone:                %s\n' "${ZONE}"
    printf 'VM:                  %s (%s, standard provisioning)\n' "${INSTANCE_NAME}" "${MACHINE_TYPE}"
    printf 'OS image:            %s/%s\n' "${IMAGE_PROJECT}" "${IMAGE_FAMILY}"
    printf 'Run ID:              %s\n' "${RUN_ID}"
    printf 'Instances:           %s\n' "${INSTANCES}"
    printf 'Solvers:             %s\n' "${SOLVERS}"
    printf 'Caps:                %s\n' "${THRESHOLDS}"
    printf 'Edge sets:           %s\n' "${EDGE_SETS}"
    printf 'CSE-17 enabled:      %s\n' "${ENABLE_CSE17}"
    printf 'Runs:                %s (sequential)\n' "${command_count}"
    printf 'Per-run cutoff:      %ss\n' "${TIMEOUT_SECONDS}"
    awk -v runs="${command_count}" -v timeout="${TIMEOUT_SECONDS}" \
        'BEGIN {printf "Worst-case VM time:  %.1f hours\n", runs * timeout / 3600}'
    printf 'Results destination: %s/%s\n' "${LOCAL_RESULTS_DIR}" "${RUN_ID}"
}

preflight_gcloud() {
    require_command gcloud
    resolve_project
    [[ -n "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" ]] || \
        die "gcloud has no active account"
    gcloud_base compute machine-types describe "${MACHINE_TYPE}" --zone "${ZONE}" >/dev/null
    if gcloud_base compute instances describe "${INSTANCE_NAME}" --zone "${ZONE}" >/dev/null 2>&1; then
        die "VM already exists: ${INSTANCE_NAME}; choose another INSTANCE_NAME or delete it explicitly"
    fi
}

create_source_archive() {
    local archive_path=$1
    tar -czf "${archive_path}" \
        --exclude='.git' \
        --exclude='.gcp-experiment' \
        --exclude='*/Output' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env*' \
        --exclude='*.key' \
        --exclude='*.lic' \
        --exclude='*.pem' \
        --exclude='gcp_key' \
        --exclude='gcp_key.pub' \
        --exclude='logs' \
        -C "${ROOT_DIR}" .
}

wait_for_ssh() {
    ssh_args
    local attempt
    for attempt in $(seq 1 30); do
        if gcloud compute ssh "${SSH_ARGS[@]}" --command 'true' >/dev/null 2>&1; then
            return 0
        fi
        printf 'Waiting for SSH (%s/30)...\n' "${attempt}"
        sleep 10
    done
    return 1
}

submit() {
    validate_config
    preflight_gcloud
    require_command tar
    if [[ "${ALLOW_DIRTY}" != "1" && -n "$(git -C "${ROOT_DIR}" status --porcelain)" ]]; then
        die "working tree is not clean; commit the exact experiment source or set ALLOW_DIRTY=1 for a non-scientific test"
    fi
    local archive source_commit source_sha remote_upload remote_command
    archive="$(mktemp "${TMPDIR:-/tmp}/salbp-source.XXXXXX")"
    create_source_archive "${archive}"
    source_commit="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
    source_sha="$(sha256_file "${archive}")"
    remote_upload="salbp-source-${RUN_ID}.tar.gz"

    printf 'Creating %s in %s...\n' "${INSTANCE_NAME}" "${ZONE}"
    gcloud_base compute instances create "${INSTANCE_NAME}" \
        --zone "${ZONE}" \
        --machine-type "${MACHINE_TYPE}" \
        --provisioning-model STANDARD \
        --image-project "${IMAGE_PROJECT}" \
        --image-family "${IMAGE_FAMILY}" \
        --boot-disk-size "${BOOT_DISK_SIZE}" \
        --boot-disk-type "${BOOT_DISK_TYPE}" \
        --network-interface nic-type=GVNIC \
        --no-service-account \
        --no-scopes \
        --labels workload=salbp-ct,managed-by=gcp-experiment-script
    write_state

    if ! wait_for_ssh; then
        if [[ "${KEEP_VM_ON_ERROR}" != "1" ]]; then
            gcloud_base compute instances delete "${INSTANCE_NAME}" --zone "${ZONE}" --quiet || true
        fi
        die "VM was created but SSH did not become ready"
    fi
    ssh_args
    if ! compute_scp "${archive}" "${INSTANCE_NAME}:/tmp/${remote_upload}"; then
        if [[ "${KEEP_VM_ON_ERROR}" != "1" ]]; then
            gcloud_base compute instances delete "${INSTANCE_NAME}" --zone "${ZONE}" --quiet || true
        fi
        die "failed to upload the source archive"
    fi
    rm -f "${archive}"

    printf -v remote_command \
        'sudo mkdir -p %q && sudo tar -xzf %q -C %q && sudo systemd-run --unit=%q --property=Type=exec --property=WorkingDirectory=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q --setenv=%q %q' \
        "${REMOTE_SOURCE_DIR}" \
        "/tmp/${remote_upload}" \
        "${REMOTE_SOURCE_DIR}" \
        "${UNIT_NAME}" \
        "${REMOTE_SOURCE_DIR}" \
        "SALBP_RUN_ID=${RUN_ID}" \
        "SALBP_RUN_ROOT=${REMOTE_DIR}" \
        "SALBP_SOURCE_DIR=${REMOTE_SOURCE_DIR}" \
        "SALBP_INSTANCES=${INSTANCES}" \
        "SALBP_SOLVERS=${SOLVERS}" \
        "SALBP_THRESHOLDS=${THRESHOLDS}" \
        "SALBP_EDGE_SETS=${EDGE_SETS}" \
        "SALBP_TIMEOUT_SECONDS=${TIMEOUT_SECONDS}" \
        "SALBP_PRIMAL_CONFLICT_BUDGET=${PRIMAL_CONFLICT_BUDGET}" \
        "SALBP_ENABLE_CSE17=${ENABLE_CSE17}" \
        "SALBP_SOURCE_COMMIT=${source_commit}" \
        "SALBP_SOURCE_ARCHIVE_SHA256=${source_sha}" \
        "${REMOTE_SOURCE_DIR}/scripts/gcp/bootstrap_vm.sh"

    if ! gcloud compute ssh "${SSH_ARGS[@]}" --command "${remote_command}"; then
        if [[ "${KEEP_VM_ON_ERROR}" != "1" ]]; then
            gcloud_base compute instances delete "${INSTANCE_NAME}" --zone "${ZONE}" --quiet || true
        fi
        die "failed to start the remote experiment"
    fi

    printf 'Submitted %s. State: %s\n' "${UNIT_NAME}" "${STATE_FILE}"
    printf 'Use: %s status | logs | collect | delete\n' "$0"
}

remote_completion() {
    ssh_args
    gcloud compute ssh "${SSH_ARGS[@]}" --command \
        "sudo test -f '${REMOTE_DIR}/artifacts/completion.env' && sudo cat '${REMOTE_DIR}/artifacts/completion.env'"
}

status_job() {
    load_state
    resolve_project
    ssh_args
    if ! remote_completion; then
        gcloud compute ssh "${SSH_ARGS[@]}" --command \
            "sudo systemctl show '${UNIT_NAME}' --property=ActiveState,SubState,ExecMainStatus --no-pager"
    fi
}

logs_job() {
    load_state
    resolve_project
    ssh_args
    local journal_args="--no-pager -n 200"
    if [[ "${FOLLOW:-0}" == "1" ]]; then
        journal_args="-f -n 50"
    fi
    gcloud compute ssh "${SSH_ARGS[@]}" --command \
        "sudo journalctl -u '${UNIT_NAME}' ${journal_args}"
}

wait_job() {
    load_state
    resolve_project
    local completion
    while true; do
        completion="$(remote_completion 2>/dev/null || true)"
        if [[ -n "${completion}" ]]; then
            printf '%s\n' "${completion}"
            grep -q '^STATUS=SUCCESS$' <<< "${completion}"
            return
        fi
        printf '%s: experiment is still running; next check in %ss\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${POLL_SECONDS}"
        sleep "${POLL_SECONDS}"
    done
}

verify_checksum() {
    local directory=$1 checksum_file=$2
    if command -v sha256sum >/dev/null 2>&1; then
        (cd "${directory}" && sha256sum -c "${checksum_file}")
    else
        (cd "${directory}" && shasum -a 256 -c "${checksum_file}")
    fi
}

collect_job() {
    load_state
    resolve_project
    ssh_args
    local destination archive_name
    destination="${LOCAL_RESULTS_DIR}/${RUN_ID}"
    archive_name="salbp-results-${RUN_ID}.tar.gz"
    mkdir -p "${destination}/extracted"

    compute_scp "${INSTANCE_NAME}:${REMOTE_DIR}/${archive_name}" "${destination}/"
    compute_scp "${INSTANCE_NAME}:${REMOTE_DIR}/${archive_name}.sha256" "${destination}/"
    gcloud compute ssh "${SSH_ARGS[@]}" --command \
        "sudo journalctl -u '${UNIT_NAME}' --no-pager" > "${destination}/systemd-journal.log"
    verify_checksum "${destination}" "${archive_name}.sha256"
    tar -xzf "${destination}/${archive_name}" -C "${destination}/extracted"
    printf 'Results collected in %s\n' "${destination}"
}

delete_vm() {
    load_state
    resolve_project
    gcloud_base compute instances delete "${INSTANCE_NAME}" --zone "${ZONE}" --quiet
    printf 'Deleted VM %s. Local state retained at %s.\n' "${INSTANCE_NAME}" "${STATE_FILE}"
}

run_all() {
    submit
    local job_status=0
    set +e
    wait_job
    job_status=$?
    set -e
    collect_job
    if [[ ${job_status} -eq 0 && "${KEEP_VM}" != "1" ]]; then
        delete_vm
    elif [[ ${job_status} -ne 0 ]]; then
        printf 'The run failed validation; VM retained for inspection.\n' >&2
    fi
    return "${job_status}"
}

case "${ACTION}" in
    plan) plan ;;
    submit) submit ;;
    status) status_job ;;
    logs) logs_job ;;
    wait) wait_job ;;
    collect) collect_job ;;
    delete) delete_vm ;;
    run) run_all ;;
    *) die "unknown action '${ACTION}'; use plan, submit, status, logs, wait, collect, delete, or run" ;;
esac
