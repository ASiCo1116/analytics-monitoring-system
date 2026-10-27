#!/bin/bash
# Container start-up. The runtime image has no pixi, so run the same commands as the pixi tasks directly.
set -e

source /shell-hook.sh

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
