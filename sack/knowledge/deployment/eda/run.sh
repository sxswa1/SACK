#!/bin/sh
# Run on the test server. No auto-start, no public ports, no Docker socket mount.
set -eu
EDA_ROOT=/opt/sack-eda-20260928
case "${1:---check}" in
  --check|--run|--validate-results) MODE=${1:---check} ;;
  *) echo "Use --check, --run, or --validate-results" >&2; exit 2 ;;
esac
NETWORK=none
if [ "$MODE" = --run ]; then NETWORK=bridge; fi
IMAGE=$(docker image inspect sack-eda-runtime:20260928 --format '{{.Id}}')
exec docker run --rm --pull never --name sack-eda-titanic \
  --network "$NETWORK" \
  --user 10001:10001 --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 4g --memory-swap 4g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m --env MPLCONFIGDIR=/tmp/matplotlib \
  --env PYTHONPYCACHEPREFIX=/tmp/pycache \
  --tmpfs /home/sackeda/.cache:rw,nosuid,nodev,size=256m \
  --env SACK_CHROMA_DB_PATH=/app/data/eda_competitions/.runtime/chroma \
  --env ANONYMIZED_TELEMETRY=False \
  --mount "type=bind,src=$EDA_ROOT/workspace,dst=/app/data/eda_competitions" \
  --mount "type=bind,src=$EDA_ROOT/workspace/titanic/rawdata,dst=/app/data/eda_competitions/titanic/rawdata,readonly" \
  --mount "type=bind,src=$EDA_ROOT/secrets/api_key.txt,dst=/app/sack/api_key.txt,readonly" \
  --mount "type=bind,src=$EDA_ROOT/code/sack/knowledge/deployment/eda/run_eda.py,dst=/app/sack/knowledge/deployment/eda/run_eda.py,readonly" \
  "$IMAGE" "$MODE" --competition titanic
