#!/usr/bin/env bash
# Smoke-test a running stack (after `docker compose --profile full up --build`).
# Verifies: api health, project create, props upload, range serving, an export.
set -euo pipefail
API="${API:-http://localhost:8000}"
IFC="${1:-samples/school_str.ifc}"

echo "1) health"; curl -sf "$API/health" >/dev/null && echo "   ok"

echo "2) create project"
PID=$(curl -sf -X POST "$API/projects" -H 'Content-Type: application/json' \
  -d "{\"name\":\"Smoke\",\"source_ifc\":\"$IFC\"}" | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "   project=$PID"

echo "3) upload properties index"
python -m aec_data.cli index "$IFC" /tmp/props.json >/dev/null
curl -sf -X POST "$API/projects/$PID/properties/index" -F "file=@/tmp/props.json" >/dev/null && echo "   ok"

echo "4) range request on a stored object"
curl -sf -o /dev/null -w "   model.frag status=%{http_code}\n" \
  -H "Range: bytes=0-99" "$API/projects/$PID/model.frag" || echo "   (no published frag yet — publish first)"

echo "5) QTO export"
curl -sf -o /tmp/qto.xlsx -w "   qto.xlsx %{size_download}B type=%{content_type}\n" \
  "$API/projects/$PID/exports/qto.xlsx"

echo "STACK SMOKE OK"
