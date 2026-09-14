#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
poetry check --lock
poetry install --no-interaction
