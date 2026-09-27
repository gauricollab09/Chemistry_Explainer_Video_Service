#!/usr/bin/env bash
# Show every failure path the API exposes, in ~30 s. Starts its own throwaway server with fault
# injection on port 8001, so a normal server on 8000 is unaffected.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT=8001
BASE=http://localhost:$PORT
DATA=$(mktemp -d)

CHEMVID_DATA_DIR=$DATA CHEMVID_FAULTS=plan_invalid_once,tts_silent_always \
  uv run uvicorn app.main:app --port $PORT --log-level warning >"$DATA/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; rm -rf "$DATA"' EXIT
until curl -sf "$BASE/health" >/dev/null; do sleep 0.3; done

show() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
pretty() { python3 -m json.tool; }
post() { curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/videos" -H 'content-type: application/json' -d "$1"; }

show "1. Out-of-scope question -> 422 UNSUPPORTED_TOPIC, no job created"
post '{"query": "What is photosynthesis?"}'

show "2. Empty query -> 422 validation error"
post '{"query": "   "}'

show "3. Unknown job id -> 404"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/videos/does-not-exist"

show "4. Supported question, submitted while faults are injected"
ID=$(curl -s -X POST "$BASE/videos" -H 'content-type: application/json' \
      -d '{"query": "How does the pH scale work?"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "job $ID"

show "5. Download before the video is ready -> 409 VIDEO_NOT_READY"
curl -s -w '\nHTTP %{http_code}\n' "$BASE/videos/$ID/file"

show "6. Job outcome: bad plan retried and recovered, then TTS fails its quality gate 3 times"
until curl -s "$BASE/videos/$ID" | python3 -c 'import sys,json; sys.exit(json.load(sys.stdin)["status"] not in ("succeeded","failed"))'; do sleep 1; done
curl -s "$BASE/videos/$ID" | python3 -c '
import sys, json
d = json.load(sys.stdin)
print({k: d[k] for k in ("status", "stage", "error_code", "error_stage", "error_message")})
for e in d["events"]:
    print("  {:<10} {:<15} {}".format(e["stage"], e["kind"], e["message"][:100]))'

show "7. Jobs list shows the failed job; no job exists for the rejected queries"
curl -s "$BASE/videos" | python3 -c 'import sys,json; [print(j["id"], j["status"], j["error_code"], "<-", j["query"]) for j in json.load(sys.stdin)]'
