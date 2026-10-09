#!/usr/bin/env bash
# Separate Docker project/volume; never resets an existing installation.
set -euo pipefail
cd "$(dirname "$0")/.."
release_compose=(docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml)
"${release_compose[@]}" build api worker web
"${release_compose[@]}" up -d --wait
"${release_compose[@]}" exec -T api python migrate.py
"${release_compose[@]}" exec -T api python -m unittest discover -s tests -p 'test_*.py'
"${release_compose[@]}" exec -T api python tests/integration.py
"${release_compose[@]}" exec -T api python tests/release_integration.py
"${release_compose[@]}" exec -T api python tests/release_boundaries.py
npm ci --prefix tests/browser
TEST_WEB_URL=http://localhost:3002 TEST_SCREENSHOT_DIR="$PWD/artifacts/release/baseline" npm test --prefix tests/browser
TEST_WEB_URL=http://localhost:3002 TEST_SCREENSHOT_DIR="$PWD/artifacts/release/journey" npm run test:release --prefix tests/browser
TEST_WEB_URL=http://localhost:3002 TEST_SCREENSHOT_DIR="$PWD/artifacts/release/visual" npm run test:visual --prefix tests/browser
printf 'PASS: isolated release checks. Test stack remains at localhost:3002.\n'
