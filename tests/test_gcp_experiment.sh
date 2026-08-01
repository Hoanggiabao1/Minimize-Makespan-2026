#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/salbp-gcp-test.XXXXXX")"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${TMP_DIR}/bin" "${TMP_DIR}/state"

cat > "${TMP_DIR}/bin/gcloud" <<'FAKE_GCLOUD'
#!/usr/bin/env bash
set -u
printf '%s\n' "$*" >> "${FAKE_GCLOUD_LOG}"

case " $* " in
    *" auth list "*)
        printf 'test-account@example.com\n'
        ;;
    *" compute instances describe "*)
        exit 1
        ;;
esac
exit 0
FAKE_GCLOUD
chmod +x "${TMP_DIR}/bin/gcloud"

plan_output="$(RUN_ID=test-plan "${ROOT_DIR}/scripts/gcp_experiment.sh" plan)"
grep -q 'Runs:                432 (sequential)' <<< "${plan_output}"
grep -q 'CSE-17 enabled:      0' <<< "${plan_output}"

FAKE_GCLOUD_LOG="${TMP_DIR}/gcloud.log" \
PATH="${TMP_DIR}/bin:${PATH}" \
PROJECT_ID=test-project \
ZONE=us-west4-a \
INSTANCE_NAME=salbp-test-vm \
RUN_ID=test-submit \
ALLOW_DIRTY=1 \
STATE_DIR="${TMP_DIR}/state" \
"${ROOT_DIR}/scripts/gcp_experiment.sh" submit

test -s "${TMP_DIR}/state/salbp-test-vm.env"
grep -q 'compute instances create salbp-test-vm' "${TMP_DIR}/gcloud.log"
grep -q -- '--machine-type c4-highcpu-8' "${TMP_DIR}/gcloud.log"
grep -q -- '--network-interface nic-type=GVNIC' "${TMP_DIR}/gcloud.log"
grep -q 'systemd-run' "${TMP_DIR}/gcloud.log"
grep -q 'SALBP_ENABLE_CSE17=0' "${TMP_DIR}/gcloud.log"

printf 'GCP automation tests passed.\n'
