#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Created .env from .env.example — add your STEEL_API_KEY and ANTHROPIC_API_KEY before running."
fi

echo ""
echo "Setup complete. Run the app with: ./run.sh"
