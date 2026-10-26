#!/usr/bin/env bash
set -euo pipefail

base_url="${MINIPAY_API_URL:-http://localhost:5000}"
api_key="${MINIPAY_API_KEY:-changeme}"

curl --fail --silent --show-error \
  -H "X-Api-Key: ${api_key}" \
  "${base_url%/}/health" >/dev/null
printf 'MiniPay API is healthy at %s\n' "${base_url}"
