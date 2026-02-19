#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "Error: virtualenv .venv not found in $SCRIPT_DIR"
  echo "Run setup first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

base_url="${OUROBOROS_BASE_URL:-}"
if [ -z "$base_url" ] && [ -f ".env" ]; then
  base_url="$(sed -n -E 's/^OUROBOROS_BASE_URL=(.*)$/\1/p' .env | tail -n 1)"
fi
if [ -z "$base_url" ]; then
  base_url="https://openrouter.ai/api/v1"
fi

if [[ "$base_url" == *"openrouter.ai"* ]]; then
  if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    if [ ! -f ".env" ] || ! grep -Eq '^OPENROUTER_API_KEY=.+$' ".env"; then
      echo "Error: OPENROUTER_API_KEY is required when OUROBOROS_BASE_URL points to OpenRouter."
      exit 1
    fi
  fi
fi

exec .venv/bin/python colab_launcher.py
