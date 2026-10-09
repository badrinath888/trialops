#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T api python -m unittest discover -s tests -p 'test_*.py' -v
docker compose exec -T api python tests/integration.py
echo "All installation checks passed."
