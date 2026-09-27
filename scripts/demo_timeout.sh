#!/usr/bin/env bash
# Timeout demo: a job that runs too long is failed cleanly, nothing is published, the API stays
# responsive, and the queue moves on to the next job. Own server on :8002 with a 25 s job limit.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=8002
BASE=http://localhost:$PORT
DATA=$(mktemp -d)

CHEMVID_DATA_DIR=$DATA CHEMVID_JOB_TIMEOUT_S=25 \
  uv run uvicorn app.main:app --port $PORT --log-level warning >"$DATA/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$DATA"' EXIT
until curl -sf "$BASE/health" >/dev/null; do sleep 0.3; done

submit() {
  curl -s -X POST "$BASE/videos" -H 'content-type: application/json' -d "{\"query\": \"$1\"}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])'
}
state() { curl -s "$BASE/videos/$1" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], d["stage"], d["error_code"] or "")'; }

echo "== Server limit: 25 s per job (a video needs ~100+ s)"
A=$(submit "How does the pH scale work?")
B=$(submit "Why do atoms form covalent bonds?")
echo "submitted A=$A (pH)   B=$B (covalent, queued behind A)"

echo
echo "== Polling every 3 s; /health is called each time to show the API is not blocked"
for i in $(seq 1 14); do
  health=$(curl -s -o /dev/null -w '%{http_code} in %{time_total}s' "$BASE/health")
  a=$(state "$A"); b=$(state "$B")
  printf '%3ss  A: %-28s B: %-28s health: %s\n' $((i * 3)) "$a" "$b" "$health"
  [[ "$a" == failed* && "$b" == running* ]] && break
  sleep 3
done

echo
echo "== Job A detail"
curl -s "$BASE/videos/$A" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print({k: d[k] for k in ("status", "error_code", "error_stage", "error_message")})
for e in d["events"]:
    print("  {:<10} {:<14} {}".format(e["stage"], e["kind"], e["message"][:90]))'

echo
echo "== Download A -> must be refused, nothing was published"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/videos/$A/file"

echo
echo "== The timed-out job's worker thread stops at its next checkpoint (server log)"
for i in $(seq 1 60); do grep -q "abandoned after timeout" "$DATA/server.log" && break; sleep 1; done
grep "abandoned after timeout" "$DATA/server.log" | sed 's/^/  /' || echo "  (thread still finishing its current step)"
echo "  published files for A: $(ls "$DATA/artifacts/published" | grep -c "$A" || true)"
