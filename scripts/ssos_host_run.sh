#!/usr/bin/env bash
# Internal host orchestrator for: ea run ssos_eclss_loop (ros2 backend).
#
# Each ea run: stop headless → start fresh headless → poll graph → run job.
# This resets SSOS plant state (CO2/O2 tanks, EPS, etc.) between runs.
#
# Prerequisite: SSOS container with volume mounts:
#   -v "$REPO/src:/ea/src"
#   -v "$REPO/src/experiments/results:/ea/results"
#
# Usage (from ea run — not end-user facing):
#   ./scripts/ssos_host_run.sh /path/to/job.json
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-${SSOS_CONTAINER_NAME:-ssos}}"
MOUNT_SRC="${EA_MOUNT_SRC:-/ea/src}"
MOUNT_RESULTS="${EA_MOUNT_RESULTS:-/ea/results}"
HEADLESS_POLL_TIMEOUT_S="${EA_HEADLESS_POLL_TIMEOUT_S:-120}"
HEADLESS_STOP_TIMEOUT_S="${EA_HEADLESS_STOP_TIMEOUT_S:-20}"
LOCK_FILE="${EA_SSOS_LOCK_FILE:-/tmp/ea-ssos-${CONTAINER}.lock}"
LOCK_DIR="${LOCK_FILE}.d"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") JOB.json

Runs a RunSpec inside the SSOS Docker container (ros2).
Requires volume mounts on $MOUNT_SRC and $MOUNT_RESULTS.
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

JOB_JSON_HOST="$1"
if [[ ! -f "$JOB_JSON_HOST" ]]; then
  echo "RunSpec not found: $JOB_JSON_HOST" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker Desktop and start the SSOS container." >&2
  exit 3
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "SSOS container '$CONTAINER' is not running." >&2
  echo >&2
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Container exists but is stopped. Start it in the background:" >&2
    echo "  docker start $CONTAINER" >&2
    echo >&2
    echo "Then run from the Mac host (not inside the container):" >&2
    echo "  ea run ssos_eclss_loop --agents-mode labeled_rule_base" >&2
  else
    echo "Create the SSOS container with helper scripts mounted:" >&2
    echo "  ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    echo >&2
    echo "See scripts/ssos/README.md (Windows/Linux: manual mounts for now)." >&2
  fi
  exit 3
fi

_acquire_run_lock() {
  # Linux: flock(1). macOS: no flock — use atomic mkdir + pid file instead.
  if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
      echo "Another ea run is already in progress for container '$CONTAINER' (lock: $LOCK_FILE)." >&2
      exit 4
    fi
    return 0
  fi

  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$LOCK_DIR/pid"
    trap '_release_run_lock' EXIT INT TERM
    return 0
  fi

  if [[ -d "$LOCK_DIR" ]]; then
    local holder_pid=""
    if [[ -f "$LOCK_DIR/pid" ]]; then
      holder_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    fi
    if [[ -n "$holder_pid" ]] && kill -0 "$holder_pid" 2>/dev/null; then
      echo "Another ea run is already in progress for container '$CONTAINER' (lock: $LOCK_DIR, pid=$holder_pid)." >&2
      exit 4
    fi
    echo "WARN: Removing stale SSOS run lock (pid ${holder_pid:-unknown} not running)." >&2
    rm -rf "$LOCK_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo $$ > "$LOCK_DIR/pid"
      trap '_release_run_lock' EXIT INT TERM
      return 0
    fi
  fi

  echo "Another ea run is already in progress for container '$CONTAINER' (lock: $LOCK_DIR)." >&2
  exit 4
}

_release_run_lock() {
  rm -rf "$LOCK_DIR"
}

_acquire_run_lock

_check_mounts() {
  if ! docker exec "$CONTAINER" test -d "$MOUNT_SRC/scenario/ssos_eclss_loop"; then
    echo "Volume mount missing: $MOUNT_SRC/scenario not found in container." >&2
    echo "Recreate the container: ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 3
  fi
  if ! docker exec "$CONTAINER" test -f /root/ssos-eclss-headless.sh; then
    echo "SSOS headless helper missing: /root/ssos-eclss-headless.sh" >&2
    echo "Recreate the container so scripts/ssos/* is mounted: ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 3
  fi
  if ! docker exec "$CONTAINER" test -d "$MOUNT_RESULTS"; then
    echo "Volume mount missing: $MOUNT_RESULTS not found in container." >&2
    exit 3
  fi
}

_eclss_storage_topic_count() {
  docker exec "$CONTAINER" bash -lc '
    set +u
    source /opt/ros/jazzy/setup.bash 2>/dev/null
    source ~/ssos_ws/install/setup.bash 2>/dev/null
    set -u 2>/dev/null || true
    topics=$(ros2 topic list 2>/dev/null || true)
    count=0
    for pattern in co2_storage o2_storage wrs/product_water_reserve; do
      if printf "%s\n" "$topics" | grep -qE "(^|/)$pattern([[:space:]]|$)"; then
        count=$((count + 1))
      fi
    done
    echo "${count:-0}"
  '
}

_eclss_graph_probe() {
  docker exec "$CONTAINER" bash -lc '
    set +u
    source /opt/ros/jazzy/setup.bash 2>/dev/null
    source ~/ssos_ws/install/setup.bash 2>/dev/null
    set -u 2>/dev/null || true
    topics=$(ros2 topic list 2>/dev/null || true)
    actions=$(ros2 action list 2>/dev/null || true)
    has_co2=0
    has_ars_diag=0
    has_ars_action=0
    printf "%s\n" "$topics" | grep -qE "(^|/)co2_storage([[:space:]]|$)" && has_co2=1 || true
    printf "%s\n" "$topics" | grep -qE "(^|/)ars/diagnostics([[:space:]]|$)" && has_ars_diag=1 || true
    printf "%s\n" "$actions" | grep -qE "(^|/)air_revitalisation([[:space:]]|$)" && has_ars_action=1 || true
    printf "%s %s %s" "$has_co2" "$has_ars_diag" "$has_ars_action"
  '
}

_stop_headless() {
  echo "==> Stopping headless SSOS (reset plant state before this run)"
  docker exec "$CONTAINER" bash -lc '
    pkill -f "[s]sos-headless.launch" 2>/dev/null || true
    pkill -f "[s]sos-eclss-headless" 2>/dev/null || true
    pkill -f "[e]clss.launch" 2>/dev/null || true
    pkill -f "[e]ps.launch" 2>/dev/null || true
    pkill -f "[s]olar_power" 2>/dev/null || true
    pkill -f "[s]pace_station_eps" 2>/dev/null || true
    pkill -f "[s]pace_station.*eclss" 2>/dev/null || true
    sleep 1
  ' || true
  _wait_headless_stopped
}

_wait_headless_stopped() {
  local deadline=$((SECONDS + HEADLESS_STOP_TIMEOUT_S))
  echo "==> Waiting for ECLSS topics to clear (timeout ${HEADLESS_STOP_TIMEOUT_S}s)"
  while ((SECONDS < deadline)); do
    local eclss_topics
    eclss_topics="$(_eclss_storage_topic_count)"
    if [[ "${eclss_topics:-0}" -eq 0 ]]; then
      echo "==> Headless processes stopped"
      sleep 1
      return 0
    fi
    sleep 1
  done
  echo "ERROR: ECLSS storage topics still present after stop timeout; forcing kill." >&2
  docker exec "$CONTAINER" bash -lc '
    pkill -9 -f "[s]sos-headless.launch" 2>/dev/null || true
    pkill -9 -f "[s]sos-eclss-headless" 2>/dev/null || true
    pkill -9 -f "[e]clss.launch" 2>/dev/null || true
    pkill -9 -f "[e]ps.launch" 2>/dev/null || true
    pkill -9 -f "[s]olar_power" 2>/dev/null || true
    pkill -9 -f "[s]pace_station_eps" 2>/dev/null || true
    pkill -9 -f "[s]pace_station.*eclss" 2>/dev/null || true
    sleep 1
  ' || true
  local final_count
  final_count="$(_eclss_storage_topic_count)"
  if [[ "${final_count:-0}" -ne 0 ]]; then
    echo "ERROR: ECLSS storage topics still present after forced stop." >&2
    exit 3
  fi
  echo "==> Headless processes stopped (forced)"
}

_start_headless() {
  echo "==> Starting ECLSS headless (solar + EPS + ECLSS)"
  docker exec -d "$CONTAINER" bash -lc '
    set +u
    source /opt/ros/jazzy/setup.bash
    source ~/ssos_ws/install/setup.bash
    set -u 2>/dev/null || true
    if [[ -f /root/ssos-eclss-headless.sh ]]; then
      exec bash /root/ssos-eclss-headless.sh
    fi
    if [[ -f /root/ssos-headless.launch.py ]]; then
      exec ros2 launch /root/ssos-headless.launch.py
    fi
    echo "ERROR: /root/ssos-eclss-headless.sh not mounted — recreate container with scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 1
  '
}

_poll_ros2_graph() {
  local deadline=$((SECONDS + HEADLESS_POLL_TIMEOUT_S))
  echo "==> Waiting for ECLSS ros2 graph (timeout ${HEADLESS_POLL_TIMEOUT_S}s)"
  while ((SECONDS < deadline)); do
    local has_co2 has_ars_diag has_ars_action
    read -r has_co2 has_ars_diag has_ars_action <<<"$(_eclss_graph_probe)"
    if [[ "${has_co2:-0}" == "1" && "${has_ars_diag:-0}" == "1" && "${has_ars_action:-0}" == "1" ]]; then
      echo "==> ECLSS ros2 graph ready (co2_storage=${has_co2} ars/diagnostics=${has_ars_diag} air_revitalisation=${has_ars_action})"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ECLSS ros2 graph not ready after ${HEADLESS_POLL_TIMEOUT_S}s." >&2
  echo "Expected co2_storage, ars/diagnostics, and air_revitalisation action." >&2
  echo "Inside container: ros2 topic list && ros2 action list" >&2
  exit 3
}

_run_job() {
  local job_in_container="/tmp/ea-job-$$.json"
  echo "==> Running job in '$CONTAINER'"
  docker cp "$JOB_JSON_HOST" "$CONTAINER:$job_in_container"
  docker exec \
    -e "LLM_PROVIDER=${LLM_PROVIDER-}" \
    -e "VLLM_BASE_URL=${VLLM_BASE_URL-}" \
    -e "VLLM_MODEL=${VLLM_MODEL-}" \
    -e "VLLM_API_KEY=${VLLM_API_KEY-}" \
    -e "VLLM_API_TIMEOUT=${VLLM_API_TIMEOUT-}" \
    "$CONTAINER" bash -lc "
    set -euo pipefail
    set +u
    source /opt/ros/jazzy/setup.bash
    source ~/ssos_ws/install/setup.bash
    set -u 2>/dev/null || true
    export SSOS_CONTAINER_REPO=/ea
    export EA_RESULTS_ROOT='$MOUNT_RESULTS'
    export PYTHONPATH='$MOUNT_SRC'\${PYTHONPATH:+:\$PYTHONPATH}
    export SSOS_ECLSS_BACKEND=ros2
    export OLLAMA_BASE_URL=\${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
    export EA_RUN_IN_CONTAINER=1
    cd /ea
    python3 -m scenario.jobs '$job_in_container'
    rm -f '$job_in_container'
  "
}

_check_mounts
_stop_headless
_start_headless
_poll_ros2_graph
_run_job
