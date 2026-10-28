#!/bin/bash
# Container start-up. The runtime image has no pixi, so run the same
# commands as the pixi tasks directly.
set -e

source /shell-hook.sh

# Bring the schema up to date before serving; set -e stops the container
# if this fails
alembic upgrade head
# Create the test accounts if missing (safe on every start)
python -m app.seed

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
