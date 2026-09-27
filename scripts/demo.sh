#!/usr/bin/env bash
# Submit the three required queries, poll until each job finishes, download the videos.
# Usage: scripts/demo.sh [base_url] [output_dir]
set -euo pipefail
BASE=${1:-http://localhost:8000}
OUT=${2:-samples}
mkdir -p "$OUT"

QUERIES=(
  "How does the pH scale work?"
  "Why do atoms form covalent bonds?"
  "What is the difference between ionic and covalent bonding?"
)

json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }

ids=()
for q in "${QUERIES[@]}"; do
  id=$(curl -sf -X POST "$BASE/videos" -H 'content-type: application/json' \
        -d "{\"query\": \"$q\"}" | json 'd["id"]')
  echo "submitted $id  <- $q"
  ids+=("$id")
done

for id in "${ids[@]}"; do
  while true; do
    read -r status stage topic <<<"$(curl -sf "$BASE/videos/$id" | json 'd["status"], d["stage"], d["topic_id"]' | tr -d "(),'")"
    printf '\r%-14s %-10s %-10s' "$id" "$status" "$stage"
    [[ "$status" == succeeded || "$status" == failed ]] && break
    sleep 3
  done
  echo
  if [[ "$status" == succeeded ]]; then
    curl -sf "$BASE/videos/$id/file" -o "$OUT/$topic.mp4"
    curl -sf "$BASE/videos/$id/captions" -o "$OUT/$topic.srt"
    echo "  saved $OUT/$topic.mp4"
  else
    curl -sf "$BASE/videos/$id" | json 'd["error_code"], d["error_stage"], d["error_message"]'
  fi
done
